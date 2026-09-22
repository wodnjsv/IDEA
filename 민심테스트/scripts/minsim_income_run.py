"""EXP-016: interleave matched persona blocks across five income conditions."""
import fcntl
import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

from minsim_luna_run import data_dir, resolve, retry_allowed


def main(concurrency=128, model="gpt-5.6-luna"):
    gpt55 = model == "gpt-5.5"
    out = data_dir() / ("minsim/gpt55_housework_income" if gpt55 else "minsim/luna_housework_income")
    out.mkdir(parents=True, exist_ok=True)
    lock = (out / "driver.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    people = list(map(json.loads, resolve("minsim_full_personas", verify=True).open()))
    ids = [people[w*300+i]["pid"] for i in range(300) for w in range(4)]
    conditions = list(json.loads(resolve("minsim_income_question", verify=True).read_text())["conditions"])
    assert conditions == ["E", "H10", "H30", "W10", "W30"]
    if gpt55:
        conditions = ["E", "H30", "W30"]
    assert (out / "mde_plan.json").exists(), "MDE preregistration required"
    targets = [64] + list(range(192, 1200, 128)) + [1200]
    for block, target in enumerate(targets):
        order = list(conditions)
        random.Random(f"minsim-income-block-v1:{block}").shuffle(order)
        for arm in order:
            path = out / arm / "raw.jsonl"
            rows = list(map(json.loads, path.open())) if path.exists() else []
            valid = {r["pid"] for r in rows if r["valid"]}
            if set(ids[:target]) <= valid:
                continue
            assert valid <= set(ids[:target]), "nonmatching persona block"
            assert all(retry_allowed([r for r in rows if r["pid"] == pid], "housework_income", model)
                       for pid in set(ids[:target])-valid), "retry budget exhausted in current block"
            started = time.time()
            print(json.dumps({"block": block, "arm": arm, "target": target, "remaining_in_block": target-len(valid)}), flush=True)
            # One full SDK process at a time; total concurrency never exceeds128.
            with (out / "run.log").open("a") as log:
                result = subprocess.run([sys.executable, str(Path(__file__).with_name("minsim_luna_run.py")),
                    "--model", model, "--question", "housework_income", "--condition", arm,
                    "--limit", str(target-len(valid)), "--concurrency", str(64 if block == 0 else concurrency)],
                    stdout=log, stderr=log)
            rows = list(map(json.loads, path.open())) if path.exists() else []
            valid = {r["pid"] for r in rows if r["valid"]}
            with (out / "blocks.jsonl").open("a") as f:
                f.write(json.dumps({"block": block, "arm": arm, "target": target,
                    "started": started, "elapsed": time.time()-started, "valid": len(valid),
                    "exit_code": result.returncode}) + "\n")
            if result.returncode or valid != set(ids[:target]):
                raise RuntimeError(f"incomplete block {block}/{arm}; inspect saved errors before resuming")
    print(json.dumps({"complete": True, "conditions": len(conditions), "personas_each": 1200}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", choices=[64, 128], type=int, default=128)
    parser.add_argument("--model", choices=["gpt-5.6-luna", "gpt-5.5"], default="gpt-5.6-luna")
    args = parser.parse_args()
    main(args.concurrency, args.model)
