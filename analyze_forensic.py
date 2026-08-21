"""Detailed turn-by-turn forensic analysis for Kaggriculture traces.

Usage:
  python analyze_forensic.py TRACE.jsonl [--out-dir logs/forensic]

This tool is diagnostic only. It does not change agent decisions.
It reconstructs, from the trace already emitted by v5.8:
  - state/resources/workers by turn;
  - planned vs scheduled vs executed work;
  - target distances and movement overhead;
  - productive vs movement actions;
  - market actions;
  - proposal/plan/rejection pressure;
  - observed state deltas between consecutive turns.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

MOVE = {"NORTH", "SOUTH", "EAST", "WEST"}
PASS = {"PASS"}
WORKERS = ("farmer", "hand_0", "hand_1", "hand_2", "hand_3", "hand_4", "hand_5", "hand_6", "hand_7", "hand_8", "hand_9")


def pos(v):
    if isinstance(v, (list, tuple)) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
        return (v[0], v[1])
    return None


def mdist(a, b):
    a, b = pos(a), pos(b)
    if a is None or b is None:
        return None
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def workers_from_state(state):
    out = {}
    w = state.get("workers", {}) if isinstance(state, dict) else {}
    f = w.get("farmer")
    if isinstance(f, dict):
        out["farmer"] = f
    for h in w.get("hands", []) or []:
        if isinstance(h, dict) and h.get("worker_id"):
            out[str(h["worker_id"])] = h
    return out


def action_name(a):
    return a[0] if isinstance(a, list) and a else None


def action_counts(final_actions):
    c = Counter()
    for key in ("farmer",):
        n = action_name(final_actions.get(key))
        if n:
            c[n] += 1
    for a in final_actions.get("hands", []) or []:
        n = action_name(a)
        if n:
            c[n] += 1
    return c


def numeric_delta(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return b - a
    return None


def state_delta(cur, nxt):
    if not cur or not nxt:
        return {}
    out = {}
    cres = cur.get("resources", {})
    nres = nxt.get("resources", {})
    out["money"] = numeric_delta(cres.get("money"), nres.get("money"))
    for bucket in ("seeds", "inventories"):
        c = cres.get(bucket, {}) or {}
        n = nres.get(bucket, {}) or {}
        if isinstance(c, dict) and isinstance(n, dict):
            keys = sorted(set(c) | set(n), key=str)
            out[bucket] = {str(k): numeric_delta(c.get(k, 0), n.get(k, 0)) for k in keys if numeric_delta(c.get(k, 0), n.get(k, 0)) not in (None, 0)}
        else:
            out[bucket] = {"changed": c != n}
    cc = cur.get("crops", {})
    nc = nxt.get("crops", {})
    for k in ("ready_to_harvest", "need_water", "at_risk", "empty_tiles", "weed_tiles"):
        if isinstance(cc.get(k), list) and isinstance(nc.get(k), list):
            out["crops_" + k + "_count_delta"] = len(nc[k]) - len(cc[k])
    out["num_crops_delta"] = len(nc.get("crops", []) or []) - len(cc.get("crops", []) or [])
    out["num_animals_delta"] = len(nxt.get("animals", {}).get("animals", []) or []) - len(cur.get("animals", {}).get("animals", []) or [])
    return out


def target_distance_by_execution(row):
    state_workers = workers_from_state(row.get("state", {}))
    result = []
    for e in (row.get("agents", {}).get("executor", {}) or {}).get("executed_steps", []) or []:
        wid = e.get("worker_id")
        target = e.get("target")
        if not wid or target is None:
            continue
        w = state_workers.get(wid)
        d = mdist(w.get("position") if w else None, target)
        result.append({
            "worker_id": wid,
            "plan_step_id": e.get("plan_step_id"),
            "action": e.get("action"),
            "target": target,
            "distance_before_action": d,
            "product": e.get("product"),
        })
    return result


def planned_selected(row):
    plan = row.get("agents", {}).get("planner") or {}
    return plan.get("steps", []) if isinstance(plan, dict) else []


def top_proposals(row, limit=5):
    economy = row.get("agents", {}).get("economy") or []
    if not isinstance(economy, list):
        return []
    ranked = sorted(economy, key=lambda x: (x.get("economic_score", 0), x.get("expected_profit", 0)), reverse=True)
    return [{
        "rank": i + 1,
        "step_id": f"{p.get('source_agent')}:{p.get('action')}:{p.get('target')}:{p.get('product')}",
        "action": p.get("action"),
        "source_agent": p.get("source_agent"),
        "target": p.get("target"),
        "product": p.get("product"),
        "cost": p.get("cost"),
        "expected_revenue": p.get("expected_revenue"),
        "expected_profit": p.get("expected_profit"),
        "economic_score": p.get("economic_score"),
        "urgency": p.get("urgency"),
        "confidence": p.get("confidence"),
        "reason": p.get("reason"),
    } for i, p in enumerate(ranked[:limit])]


def worker_actual_transitions(row, next_row):
    cur = workers_from_state(row.get("state", {}))
    nxt = workers_from_state(next_row.get("state", {})) if next_row else {}
    out = []
    for wid in sorted(set(cur) | set(nxt)):
        cp = cur.get(wid, {}).get("position")
        np = nxt.get(wid, {}).get("position")
        d = mdist(cp, np)
        out.append({"worker_id": wid, "from": cp, "to": np, "distance": d})
    return out


def row_diagnostic(row, next_row=None):
    fa = row.get("final_actions", {}) or {}
    counts = action_counts(fa)
    movement = sum(v for k, v in counts.items() if k in MOVE)
    productive = sum(v for k, v in counts.items() if k not in MOVE and k not in PASS)
    worker_count = len(workers_from_state(row.get("state", {})))
    ex = row.get("agents", {}).get("executor") or {}
    executed = ex.get("executed_steps", []) if isinstance(ex, dict) else []
    failed = ex.get("failed_steps", []) if isinstance(ex, dict) else []
    skipped = ex.get("skipped_steps", []) if isinstance(ex, dict) else []
    plan = row.get("agents", {}).get("planner") or {}
    schedule = row.get("agents", {}).get("coordinator") or {}
    rejections = plan.get("rejected", []) if isinstance(plan, dict) else []
    distances = target_distance_by_execution(row)
    target_distances = [x["distance_before_action"] for x in distances if x["distance_before_action"] is not None]
    actual_transitions = worker_actual_transitions(row, next_row)
    actual_move_distance = sum(x["distance"] or 0 for x in actual_transitions)
    selected = planned_selected(row)
    state = row.get("state", {})
    res = state.get("resources", {})
    time = state.get("time", {})
    return {
        "turn": row.get("turn"),
        "episode": row.get("episode"),
        "time": {k: time.get(k) for k in ("day", "hour", "remaining_turns", "remaining_days")},
        "resources": {
            "money": res.get("money"),
            "seeds": res.get("seeds", {}),
            "inventories": res.get("inventories", {}),
            "shed_used": res.get("shed_used"),
            "shed_capacity": res.get("shed_capacity"),
        },
        "workers": workers_from_state(state),
        "worker_count": worker_count,
        "crops": {
            "count": len(state.get("crops", {}).get("crops", []) or []),
            "ready": len(state.get("crops", {}).get("ready_to_harvest", []) or []),
            "need_water": len(state.get("crops", {}).get("need_water", []) or []),
            "at_risk": len(state.get("crops", {}).get("at_risk", []) or []),
            "empty_tiles": len(state.get("crops", {}).get("empty_tiles", []) or []),
            "weed_tiles": len(state.get("crops", {}).get("weed_tiles", []) or []),
        },
        "proposals": {
            "crop": len(row.get("agents", {}).get("crop") or []),
            "animal": len(row.get("agents", {}).get("animal") or []),
            "market": len(row.get("agents", {}).get("market") or []),
            "investment": len(row.get("agents", {}).get("investment") or []),
            "economy": len(row.get("agents", {}).get("economy") or []),
        },
        "top_economy_proposals": top_proposals(row),
        "plan": {
            "steps": len(selected),
            "total_cost": plan.get("total_cost") if isinstance(plan, dict) else None,
            "expected_profit": plan.get("expected_profit") if isinstance(plan, dict) else None,
            "total_score": plan.get("total_score") if isinstance(plan, dict) else None,
            "selected_steps": selected,
            "rejections": len(rejections),
            "rejection_reasons": Counter(x.get("reason", "unknown") for x in rejections).most_common(10),
        },
        "schedule": {
            "steps": len(schedule.get("steps", []) or []) if isinstance(schedule, dict) else 0,
            "status": schedule.get("status") if isinstance(schedule, dict) else None,
            "estimated_turns": schedule.get("estimated_turns") if isinstance(schedule, dict) else None,
            "blocked": len(schedule.get("blocked", []) or []) if isinstance(schedule, dict) else 0,
        },
        "execution": {
            "status": ex.get("status") if isinstance(ex, dict) else None,
            "actions_sent": ex.get("actions_sent") if isinstance(ex, dict) else None,
            "actions_succeeded": ex.get("actions_succeeded") if isinstance(ex, dict) else None,
            "actions_failed": ex.get("actions_failed") if isinstance(ex, dict) else None,
            "executed_steps": len(executed),
            "failed_steps": len(failed),
            "skipped_steps": len(skipped),
            "skipped_reasons": Counter(x.get("reason", "unknown") for x in skipped).most_common(),
            "target_distances": distances,
            "target_distance_sum": sum(target_distances),
            "target_distance_avg": (sum(target_distances) / len(target_distances)) if target_distances else 0,
        },
        "actions": {
            "counts": dict(counts),
            "movement_actions": movement,
            "productive_actions": productive,
            "movement_to_productive_ratio": (movement / productive) if productive else None,
            "worker_actions": movement + productive,
        },
        "actual_worker_transitions": actual_transitions,
        "actual_movement_distance": actual_move_distance,
        "state_delta_next_turn": state_delta(state, next_row.get("state", {})) if next_row else {},
        "market_orders": fa.get("market", []) or [],
        "error": row.get("error"),
    }


def render_markdown(diags, path):
    total = len(diags)
    movement = sum(d["actions"]["movement_actions"] for d in diags)
    productive = sum(d["actions"]["productive_actions"] for d in diags)
    crop_props = sum(d["proposals"]["crop"] for d in diags)
    economy_props = sum(d["proposals"]["economy"] for d in diags)
    rejects = sum(d["plan"]["rejections"] for d in diags)
    target_d = sum(d["execution"]["target_distance_sum"] for d in diags)
    lines = [
        "# Kaggriculture v5.8 — Forensic Diagnostic Report",
        "",
        f"Turns analyzed: **{total}**",
        "",
        "## Executive metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Crop proposals | {crop_props} |",
        f"| Economy proposals | {economy_props} |",
        f"| Planner rejections | {rejects} |",
        f"| Movement actions | {movement} |",
        f"| Productive/non-movement worker actions | {productive} |",
        f"| Movement / productive ratio | {(movement / productive) if productive else 0:.2f} |",
        f"| Sum of pre-action target distances | {target_d:.1f} |",
        "",
        "## Interpretation boundaries",
        "",
        "This report is **diagnostic only**. It does not change Crop, Economy, Planner, Critic, Coordinator or Executor behavior.",
        "Distances are reconstructed from the recorded worker positions and execution targets. State deltas are observed between consecutive snapshots; they are not claimed to be a causal accounting of a single action when several orders occur in one turn.",
        "",
        "## Highest-pressure turns",
        "",
        "| Turn | Crop props | Economy props | Rejections | Moves | Productive | Move/Productive | Target distance |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    ranked = sorted(diags, key=lambda d: (d["actions"]["movement_actions"], d["plan"]["rejections"], d["execution"]["target_distance_sum"]), reverse=True)
    for d in ranked[:20]:
        ratio = d["actions"]["movement_to_productive_ratio"]
        lines.append(f"| {d['turn']} | {d['proposals']['crop']} | {d['proposals']['economy']} | {d['plan']['rejections']} | {d['actions']['movement_actions']} | {d['actions']['productive_actions']} | {ratio if ratio is not None else 0:.2f} | {d['execution']['target_distance_sum']:.1f} |")
    lines += ["", "## Turn-by-turn detail", ""]
    for d in diags:
        lines += [
            f"### Turn {d['turn']} — day {d['time'].get('day')} hour {d['time'].get('hour')}",
            "",
            f"- Money: `{d['resources']['money']}`; workers: `{d['worker_count']}`; crops: `{d['crops']['count']}`; ready: `{d['crops']['ready']}`; need water: `{d['crops']['need_water']}`.",
            f"- Proposals: crop `{d['proposals']['crop']}`, animal `{d['proposals']['animal']}`, market `{d['proposals']['market']}`, investment `{d['proposals']['investment']}`, economy `{d['proposals']['economy']}`.",
            f"- Plan: `{d['plan']['steps']}` steps, cost `{d['plan']['total_cost']}`, expected profit `{d['plan']['expected_profit']}`, rejected `{d['plan']['rejections']}`.",
            f"- Execution: `{d['execution']['status']}`, executed `{d['execution']['executed_steps']}`, failed `{d['execution']['failed_steps']}`, skipped `{d['execution']['skipped_steps']}`.",
            f"- Worker actions: `{d['actions']['counts']}`; movement `{d['actions']['movement_actions']}`, productive `{d['actions']['productive_actions']}`.",
            f"- Target distance before scheduled work: `{d['execution']['target_distance_sum']}` total / `{d['execution']['target_distance_avg']:.2f}` average.",
            f"- Actual movement distance between snapshots: `{d['actual_movement_distance']}`.",
        ]
        if d["market_orders"]:
            lines.append(f"- Market orders: `{d['market_orders']}`.")
        if d["plan"]["rejection_reasons"]:
            lines.append(f"- Main rejection reasons: `{d['plan']['rejection_reasons']}`.")
        if d["state_delta_next_turn"]:
            lines.append(f"- Next-state delta: `{d['state_delta_next_turn']}`.")
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    rows = [json.loads(x) for x in Path(args.trace).read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        raise SystemExit("No trace records.")
    out_dir = Path(args.out_dir) if args.out_dir else Path(args.trace).parent / "forensic"
    out_dir.mkdir(parents=True, exist_ok=True)
    diags = [row_diagnostic(r, rows[i + 1] if i + 1 < len(rows) else None) for i, r in enumerate(rows)]
    out_jsonl = out_dir / (Path(args.trace).stem + ".forensic.jsonl")
    with out_jsonl.open("w", encoding="utf-8") as f:
        for d in diags:
            f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
    out_md = out_dir / (Path(args.trace).stem + ".forensic.md")
    render_markdown(diags, out_md)
    print(f"FORENSIC TURNS: {len(diags)}")
    print(f"FORENSIC JSONL: {out_jsonl}")
    print(f"FORENSIC REPORT: {out_md}")
    print(f"MOVEMENT ACTIONS: {sum(d['actions']['movement_actions'] for d in diags)}")
    print(f"PRODUCTIVE ACTIONS: {sum(d['actions']['productive_actions'] for d in diags)}")
    print(f"PLANNER REJECTIONS: {sum(d['plan']['rejections'] for d in diags)}")
    print(f"TARGET DISTANCE SUM: {sum(d['execution']['target_distance_sum'] for d in diags):.1f}")


if __name__ == "__main__":
    main()
