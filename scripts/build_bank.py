"""T2 프로토타입 뱅크 빌더 CLI. 사용: python scripts/build_bank.py --track national|gwangmyeong --n 500"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.bank import build_bank, load_pool, load_tables  # noqa: E402
from engine.registry import data_dir  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", choices=["national", "gwangmyeong"], required=True)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    pool = load_pool()
    W, I, K = load_tables()
    personas, picked, fb = build_bank(args.track, args.n, args.seed, pool, W, I, K)

    out = data_dir() / "banks" / f"persona_bank_{args.track}_v0.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for p in personas:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"[{args.track}] {len(personas)}명 → {out}")
    print("폴백 사용:", json.dumps(fb, ensure_ascii=False))
    return personas, picked, pool


if __name__ == "__main__":
    main()
