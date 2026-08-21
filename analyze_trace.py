"""Summarize a Kaggriculture forensic JSONL trace.

Usage:
  python analyze_trace.py logs/kaggriculture_trace.jsonl
"""
from __future__ import annotations
import json, sys
from collections import Counter


def main(path):
    rows=[json.loads(x) for x in open(path, encoding='utf-8') if x.strip()]
    if not rows:
        print('No trace records.')
        return
    turns=len(rows)
    print(f'TURNS: {turns}')
    print(f'RANGE: {rows[0]["turn"]} -> {rows[-1]["turn"]}')
    actions=Counter()
    market=Counter()
    status=Counter()
    rejects=Counter()
    failures=Counter()
    skips=Counter()
    proposals=Counter()
    for r in rows:
        fa=r.get('final_actions',{})
        if fa.get('farmer'): actions[fa['farmer'][0]] += 1
        for a in fa.get('hands',[]):
            if a: actions[a[0]] += 1
        for o in fa.get('market',[]):
            if o: market[o[0]] += 1
        ex=r.get('agents',{}).get('executor') or {}
        if isinstance(ex,dict): status[str(ex.get('status'))]+=1
        pl=r.get('agents',{}).get('planner') or {}
        for x in (pl.get('rejected',[]) if isinstance(pl,dict) else []):
            rejects[str(x.get('reason','unknown'))]+=1
        cr=r.get('agents',{}).get('critic') or {}
        if isinstance(cr,dict):
            status['critic:'+str(cr.get('status'))]+=1
        for x in (ex.get('failed_steps',[]) if isinstance(ex,dict) else []):
            failures[str(x.get('code','unknown'))]+=1
        for x in (ex.get('skipped_steps',[]) if isinstance(ex,dict) else []):
            skips[str(x.get('reason','unknown'))]+=1
        for name in ('crop','animal','market','investment','economy'):
            vals=r.get('agents',{}).get(name) or []
            if isinstance(vals,list): proposals[name]+=len(vals)
    print('\nFINAL WORKER ACTIONS:')
    print(actions.most_common())
    print('\nMARKET ORDERS:')
    print(market.most_common())
    print('\nPROPOSAL COUNTS:')
    print(dict(proposals))
    print('\nCRITIC/EXECUTOR STATUS:')
    print(status.most_common())
    print('\nEXECUTION FAILURES:')
    print(failures.most_common() or 'none')
    print('\nSKIPPED STEPS:')
    print(skips.most_common() or 'none')
    print('\nPLANNER REJECTIONS:')
    print(rejects.most_common(10) or 'none')

if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: python analyze_trace.py TRACE.jsonl')
    main(sys.argv[1])
