"""T2 뱅크 빌더 CLI.

예) 프로토타입:  python scripts/build_bank.py --track national --n 500 --tag v0
    본뱅크:      python scripts/build_bank.py --track national --n 5000 --floor 200 --tag v1
                python scripts/build_bank.py --track gwangmyeong --full-pool --tag v1
집계 시 가중치는 weight_bank 사용 (인구가중값 재가중 금지 — AUDIT-2026-07-23 H).
"""
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
    ap.add_argument("--floor", type=int, default=0, help="시도별 최소 표본 (T2 게이트: 본뱅크 200)")
    ap.add_argument("--full-pool", action="store_true", help="표집 없이 풀 전수 사용 (광명 트랙)")
    ap.add_argument("--ideology", choices=["dev", "off"], default="dev",
                    help="ISS-010 게이트: dev=개발용 포함(기본), off=미포함(프로덕션 안전)")
    ap.add_argument("--verify", action="store_true", help="로드 시 registry sha256 검증")
    ap.add_argument("--tag", default="v0")
    args = ap.parse_args()

    pool = load_pool(verify=args.verify)
    W, I, K = load_tables(verify=args.verify)
    personas, picked, fb = build_bank(args.track, args.n, args.seed, pool, W, I, K,
                                      floor=args.floor, full_pool=args.full_pool,
                                      ideology=args.ideology, tag=args.tag)

    out = data_dir() / "banks" / f"persona_bank_{args.track}_{args.tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for p in personas:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"[{args.track}/{args.tag}] {len(personas)}명 → {out}")
    print("폴백 사용:", json.dumps(fb, ensure_ascii=False))


if __name__ == "__main__":
    main()
