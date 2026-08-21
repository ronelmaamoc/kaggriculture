"""Run Kaggriculture locally with the real kaggle-environments engine.

Examples:
  python local_kaggle_batch.py --opponent pass --seed 0
  python local_kaggle_batch.py --opponent starter --seed 0 --steps 720
  python local_kaggle_batch.py --opponent pass --seeds 0 1 2 3 4
"""
from __future__ import annotations
import argparse
from kaggle_environments import make
import main as kaggriculture_main


def run_one(opponent: str, seed: int, steps: int, trace_file: str | None = None) -> None:
    if trace_file:
        kaggriculture_main.configure_trace(trace_file)
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": steps, "seed": seed},
        debug=True,
    )
    env.run([kaggriculture_main.agent, opponent])
    final = env.steps[-1]
    print(
        f"opponent={opponent:7s} seed={seed:3d} "
        f"agent_player=0 reward_agent={final[0].reward} status_agent={final[0].status} "
        f"opponent_reward={final[1].reward} status_opponent={final[1].status}"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--opponent", choices=("pass", "random", "starter"), default="pass")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--seeds", type=int, nargs="+", default=None)
    p.add_argument("--steps", type=int, default=720)
    p.add_argument("--trace-file", type=str, default=None, help="JSONL forensic trace, one complete multi-agent decision per turn")
    args = p.parse_args()
    seeds = args.seeds if args.seeds is not None else ([args.seed] if args.seed is not None else [0, 1, 2])
    for seed in seeds:
        run_one(args.opponent, seed, args.steps, args.trace_file)


if __name__ == "__main__":
    main()
