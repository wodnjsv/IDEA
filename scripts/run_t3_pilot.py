"""EXP-004 T3 위생 실험 러너 (A/B/C 3암). 백엔드 교체 가능 — 재원 맥 로컬 실행용.

    # NVIDIA NIM 무료 백엔드 (기본)
    python scripts/run_t3_pilot.py --smoke
    python scripts/run_t3_pilot.py --full

    # EXP-004 원본 규격 재현 (유료)
    python scripts/run_t3_pilot.py --full --provider openai --model gpt-4o-mini

- 컷오프 게이트(ISS-012)는 engine.llm_client.assert_cutoff가 코드로 강제한다.
- k는 n=K 1콜 우선, 미지원 백엔드면 K콜로 자동 강등(요청 수 K배 — 진행 로그의 'n모드' 확인).
- 캐시: data/t3/raw_{arm}[_smoke][_{tag}].jsonl append + 재개(resume) 지원 (T1 원칙)
- 집계는 반드시 weight_bank (ISS-016) — scripts/score_t3.py 사용
"""
import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC          # noqa: E402
from engine.prompts_t3 import build_prompt   # noqa: E402

TEMPERATURE = 1.0          # 오차축소 0단 규격 (phase0의 0.7에서 변경 — EXP-004 기록)
SEED = 42
ARMS = ["A", "B", "C"]
BANK = ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl"
OUT = ROOT / "data" / "t3"
EST_IN_TOK, EST_OUT_TOK = 1000, 400
PRICE = {"gpt-4o-mini": (0.15, 0.60)}


def load_subsample(n):
    personas = [json.loads(l) for l in open(BANK, encoding="utf-8")]
    rng = random.Random(SEED)
    return rng.sample(personas, n) if n < len(personas) else personas


def done_ids(path):
    if not path.exists():
        return set()
    ids = set()
    for l in open(path, encoding="utf-8"):
        try:
            r = json.loads(l)
            if "error" not in r:
                ids.add(r["persona_id"])
        except Exception:
            pass
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--arms", nargs="+", default=ARMS, choices=ARMS)
    ap.add_argument("--yes", action="store_true", help="확인 프롬프트 생략")
    LC.add_backend_args(ap)
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")
    n = 10 if args.smoke else 1000

    sampler, mkey, spec, gate, tag, fp, rpm = LC.resolve_backend(args)
    sampler.temperature = TEMPERATURE
    print(f"[백엔드] {LC.describe(mkey, gate, fp)} | RPM {rpm} | K {args.k}")

    personas = n * len(args.arms)
    worst = personas * args.k
    print(f"[EXP-004] {n}명 × {len(args.arms)}암 = {personas} 페르소나-콜")
    print(f"  요청 수: n=K 지원 시 {personas:,} / 미지원 시 {worst:,}")
    print(f"  벽시계 추정: {personas/rpm/60:.1f}h ~ {worst/rpm/60:.1f}h ({rpm} RPM 상한)")
    if spec.provider == "openai":
        pi, po = PRICE.get(mkey, (0.15, 0.60))
        est = personas * (EST_IN_TOK * pi + EST_OUT_TOK * po) / 1e6
        print(f"  예상 비용 ~${est:.2f} (상한 게이트 $500 — ISS-014)")
    else:
        print("  예상 비용 $0 (무료 티어) — 비용 대신 RPM이 병목")
    if not args.yes and input("진행? [y/N] ").strip().lower() != "y":
        sys.exit("중단")

    OUT.mkdir(parents=True, exist_ok=True)
    sub = load_subsample(n)
    json.dump([p["persona_id"] for p in sub], open(OUT / f"subsample_ids_{n}.json", "w"))

    def call_one(arm, persona):
        system, user, options = build_prompt(arm, persona)
        try:
            samples, usage = sampler.sample(system, user)
        except Exception as e:                    # noqa: BLE001
            return {"persona_id": persona["persona_id"], "arm": arm, "error": LC.scrub(e)[:300]}
        return {"persona_id": persona["persona_id"], "arm": arm,
                "weight_bank": persona["weight_bank"],
                "sido": persona["skeleton"]["sido"], "sido_name": persona["skeleton"]["sido_name"],
                "model": spec.id, "gate": gate, "options": options, "samples": samples, "usage": usage}

    tot, errs, t0 = {"in": 0, "out": 0}, 0, time.monotonic()
    for arm in args.arms:
        path = OUT / f"raw_{arm}{'_smoke' if args.smoke else ''}{'_' + tag if tag else ''}.jsonl"
        todo = [p for p in sub if p["persona_id"] not in done_ids(path)]
        print(f"[{arm}암] {len(todo)}명 → {path.name}")
        with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(args.concurrency) as ex:
            futs = {ex.submit(call_one, arm, p): p for p in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                if "usage" in rec:
                    tot["in"] += rec["usage"]["in"]
                    tot["out"] += rec["usage"]["out"]
                else:
                    errs += 1
                if i % 50 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)} | {(time.monotonic()-t0)/60:.1f}분 | 실패 {errs} | "
                          f"n모드 {sampler.n_mode} | 429 {sampler.stats['429']}")
    print(f"\n완료. 요청 {sampler.stats['requests']:,} | 토큰 in={tot['in']:,} out={tot['out']:,} | 실패 {errs}")
    if spec.provider == "openai":
        pi, po = PRICE.get(mkey, (0.15, 0.60))
        print(f"실비용 ~${tot['in']/1e6*pi + tot['out']/1e6*po:.2f}")
    print("다음: python scripts/score_t3.py" + (" --smoke" if args.smoke else ""))


if __name__ == "__main__":
    main()
