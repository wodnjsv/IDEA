"""T2 뱅크 빌더 CLI.

예) 프로토타입:  python scripts/build_bank.py --track national --n 500 --tag v0
    본뱅크:      python scripts/build_bank.py --track national --n 5000 --floor 200 --tag v1
                python scripts/build_bank.py --track gwangmyeong --full-pool --tag v1
    통근 A2 재빌드(ISS-033 — 원자료 필요, 41번 타시도 목적지 포함, v1과 paired 비교용으로 ID 태그 고정):
                python scripts/build_bank.py --track national --n 5000 --floor 200 --tag v3 --id-tag v1
                python scripts/build_bank.py --track gwangmyeong --full-pool --tag v3 --id-tag v1
                python scripts/compare_bank_versions.py national v1 v3
    (통근 A1 = 원자료 없이 v1 역변환 재라벨 → scripts/relabel_bank_commute.py, 결과 tag v2)
집계 시 가중치는 weight_bank 사용 (인구가중값 재가중 금지 — AUDIT-2026-07-23 H).
기존 파일은 덮어쓰지 않는다(배타 생성. --overwrite 명시 시에만 덮어쓰기).
재빌드 뱅크의 마진 검증(validate_bank.py)은 지표 산출이므로 EXP 카드 선행(AGENTS 규칙 6, EXP-002/003 선례).
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
    ap.add_argument("--id-tag", default=None,
                    help="persona_id에 넣을 태그(기본=--tag). 기존 뱅크와 paired 비교할 재빌드는 원 태그로 고정 "
                         "— persona_id가 선택지 순서 난수 키이기 때문(ISS-033)")
    ap.add_argument("--overwrite", action="store_true",
                    help="기존 뱅크 파일 덮어쓰기 허용 (기본 거부 — paired 기준선 보존, ISS-033)")
    args = ap.parse_args()

    out = data_dir() / "banks" / f"persona_bank_{args.track}_{args.tag}.jsonl"
    if out.exists() and not args.overwrite:  # 조기 안내용. 실제 보호는 아래 배타 생성("x")
        sys.exit(f"거부: {out} 이미 존재. 기존 뱅크는 paired 기준선이다 — 새 --tag를 쓰거나 --overwrite를 명시할 것.")

    pool = load_pool(verify=args.verify)
    W, I, K = load_tables(verify=args.verify)
    personas, picked, fb = build_bank(args.track, args.n, args.seed, pool, W, I, K,
                                      floor=args.floor, full_pool=args.full_pool,
                                      ideology=args.ideology, tag=args.tag, id_tag=args.id_tag)

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        f = open(out, "w" if args.overwrite else "x", encoding="utf-8")
    except FileExistsError:
        sys.exit(f"거부: {out}이 생성 도중 나타남(동시 실행?) — 덮어쓰지 않음.")
    with f:
        for p in personas:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"[{args.track}/{args.tag}] {len(personas)}명 → {out}")
    print("폴백 사용:", json.dumps(fb, ensure_ascii=False))


if __name__ == "__main__":
    main()
