"""Run the real Kaggriculture engine locally.

Usage:
    python local_kaggle_test.py --steps 720 --seed 42 --opponent starter
    python local_kaggle_test.py --steps 720 --seed 7 --opponent random
    python local_kaggle_test.py --steps 20 --seed 1 --opponent pass

This file is for local validation only. It is not imported by main.py.
"""
from __future__ import annotations

import argparse
import json

from kaggle_environments import make
from main import agent


def run(steps: int, seed: int, opponent: str, replay: str) -> None:
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": steps, "seed": seed},
        debug=True,
    )
    env.run([agent, opponent])

    with open(replay, "w", encoding="utf-8") as fh:
        json.dump(env.toJSON(), fh)

    print(f"steps={steps} seed={seed} opponent={opponent}")
    print(f"replay={replay}")
    for i, state in enumerate(env.steps[-1]):
        print(
            f"player={i} reward={state.reward} "
            f"status={state.status}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=720)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--opponent", choices=("pass", "random", "starter"), default="starter")
    parser.add_argument("--replay", default="replay.json")
    args = parser.parse_args()
    run(args.steps, args.seed, args.opponent, args.replay)
