"""EXP-005 러너 — B암(대조)·D암(생각 카드)·E암(후보 프로필). 백엔드 교체 가능.

    # NVIDIA NIM 무료 백엔드 (기본)
    python scripts/run_ab_cards.py --smoke --arms B D E
    python scripts/run_ab_cards.py --full  --arms B D E

    # 기존 OpenAI 규격 재현
    python scripts/run_ab_cards.py --full --provider openai --model gpt-4o-mini

원자료는 모델별로 분리 저장된다: raw_{arm}[_smoke][_{tag}].jsonl
  tag는 모델 키(예: llama-3.3-70b). gpt-4o-mini는 tag 없음 → EXP-004/005 기존 파일과 호환.
모델을 바꾸면 B암도 함께 돌려야 paired 비교가 성립한다(교차모델 비교는 EXP-006).
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC              # noqa: E402
from engine.prompts_ab import build_prompt_ab    # noqa: E402
from engine.prompts_t3 import build_prompt       # noqa: E402

OUT = ROOT / "data" / "t3"
PRICE = {"gpt-4o-mini": (0.15, 0.60)}            # $/1M tok — NVIDIA 무료 티어는 0


def raw_path(arm, smoke, tag):
    return OUT / f"raw_{arm}{'_smoke' if smoke else ''}{'_' + tag if tag else ''}.jsonl"


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
    ap.add_argument("--arms", nargs="+", default=["D", "E"], choices=["B", "D", "E", "D2A", "D2B"])
    ap.add_argument("--yes", action="store_true")
    LC.add_backend_args(ap)
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")

    sampler, mkey, spec, gate, tag, fp, rpm = LC.resolve_backend(args)
    print(f"[백엔드] {LC.describe(mkey, gate, fp)} | RPM {rpm} | K {args.k}")

    bank = {json.loads(l)["persona_id"]: json.loads(l)
            for l in open(ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl", encoding="utf-8")}
    beliefs = json.load(open(OUT / "belief_cards.json", encoding="utf-8"))
    beliefs_v2 = (json.load(open(OUT / "belief_cards_v2.json", encoding="utf-8"))
                  if any(a in ("D2A", "D2B") for a in args.arms) else {})
    ids = json.load(open(OUT / "subsample_ids_1000.json"))   # EXP-004와 동일 표본 (paired)
    if args.smoke:
        ids = ids[:10]

    personas = len(ids) * len(args.arms)
    worst = personas * args.k          # n=K 미지원 시 요청 수
    print(f"[EXP-005] {len(ids)}명 × {len(args.arms)}암({''.join(args.arms)}) = {personas} 페르소나-콜")
    print(f"  요청 수: n=K 지원 시 {personas:,} / 미지원 시 {worst:,}")
    print(f"  벽시계 추정: {personas/rpm/60:.1f}h ~ {worst/rpm/60:.1f}h ({rpm} RPM 상한)")
    if spec.provider == "openai":
        pi, po = PRICE.get(mkey, (0.15, 0.60))
        print(f"  예상 비용 ~${personas * (1000 * pi + 400 * po) / 1e6:.2f} (ISS-014 상한 $500)")
    else:
        print("  예상 비용 $0 (무료 티어) — 비용 대신 RPM이 병목")
    if not args.yes and input("진행? [y/N] ").strip().lower() != "y":
        sys.exit("중단")

    def call_one(arm, pid):
        p = bank[pid]
        if arm == "B":
            system, user, options = build_prompt("B", p)
            bc = None
        elif arm in ("D2A", "D2B"):
            v2 = beliefs_v2[pid]
            bc = {"sentences": v2[arm]["sentences"], "donor_partylr": v2["donor_partylr"]}
            system, user, options = build_prompt_ab("D", p, bc)  # D암 골격 재사용 — 카드 내용만 상이 (EXP-007)
        else:
            bc = beliefs.get(pid)
            system, user, options = build_prompt_ab(arm, p, bc)
        try:
            samples, usage = sampler.sample(system, user)
        except Exception as e:                    # noqa: BLE001
            return {"persona_id": pid, "arm": arm, "error": LC.scrub(e)[:300]}
        return {"persona_id": pid, "arm": arm, "weight_bank": p["weight_bank"],
                "sido": p["skeleton"]["sido"], "sido_name": p["skeleton"]["sido_name"],
                "card_ideology": p["drawn"]["ideology_label"],
                "donor_partylr": (bc or {}).get("donor_partylr"),
                "model": spec.id, "gate": gate, "options": options, "samples": samples, "usage": usage}

    OUT.mkdir(parents=True, exist_ok=True)
    tot, errs, t0 = {"in": 0, "out": 0}, 0, time.monotonic()
    for arm in args.arms:
        path = raw_path(arm, args.smoke, tag)
        todo = [i for i in ids if i not in done_ids(path)]
        print(f"[{arm}암] {len(todo)}명 → {path.name}")
        with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(args.concurrency) as ex:
            futs = {ex.submit(call_one, arm, i): i for i in todo}
            for n, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                if "usage" in rec:
                    tot["in"] += rec["usage"]["in"]
                    tot["out"] += rec["usage"]["out"]
                else:
                    errs += 1
                if n % 50 == 0 or n == len(todo):
                    el = time.monotonic() - t0
                    print(f"  {n}/{len(todo)} | {el/60:.1f}분 | 실패 {errs} | "
                          f"n모드 {sampler.n_mode} | 429 {sampler.stats['429']}")
    print(f"\n완료. 요청 {sampler.stats['requests']:,} (재시도 {sampler.stats['retry']}, "
          f"429 {sampler.stats['429']}) | 토큰 in={tot['in']:,} out={tot['out']:,} | 실패 {errs}")
    if spec.provider == "openai":
        pi, po = PRICE.get(mkey, (0.15, 0.60))
        print(f"실비용 ~${tot['in']/1e6*pi + tot['out']/1e6*po:.2f}")
    print("다음: python scripts/score_ab.py" + (" --smoke" if args.smoke else "")
          + (f" --tag {tag}" if tag else ""))
    if os.environ.get("IDEA_DEBUG"):
        print(sampler.stats)


if __name__ == "__main__":
    main()
