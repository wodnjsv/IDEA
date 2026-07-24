"""EXP-005 러너 — D암(생각 카드)·E암(후보 프로필). EXP-004와 같은 1,000명(paired).

    export OPENAI_API_KEY=sk-...
    python scripts/run_ab_cards.py --smoke        # 10명×2암 (~$0.01)
    python scripts/run_ab_cards.py --full         # 1,000명×2암 (~$0.55 추정)
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
from engine.prompts_ab import build_prompt_ab  # noqa: E402

MODEL = "gpt-4o-mini-2024-07-18"
assert "2023-10" < "2025-06", "MEMORIZATION_RISK (ISS-012)"
TEMPERATURE, K, CONCURRENCY = 1.0, 5, 8
ARMS = ["D", "E"]
OUT = ROOT / "data" / "t3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY 환경변수 필요")
    from openai import OpenAI
    client = OpenAI()

    bank = {json.loads(l)["persona_id"]: json.loads(l)
            for l in open(ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl", encoding="utf-8")}
    beliefs = json.load(open(OUT / "belief_cards.json", encoding="utf-8"))
    ids = json.load(open(OUT / "subsample_ids_1000.json"))  # EXP-004와 동일 표본 (paired)
    if args.smoke:
        ids = ids[:10]
    calls = len(ids) * len(ARMS)
    est = calls * (1000 * 0.15 + 400 * 0.60) / 1e6
    print(f"[EXP-005] {len(ids)}명 × {len(ARMS)}암 = {calls}콜 | 예상 ~${est:.2f}")
    if not args.yes and input("진행? [y/N] ").strip().lower() != "y":
        sys.exit("중단")

    def call_one(arm, pid):
        p = bank[pid]
        system, user, options = build_prompt_ab(arm, p, beliefs.get(pid))
        for attempt in range(3):
            try:
                r = client.chat.completions.create(
                    model=MODEL, temperature=TEMPERATURE, max_tokens=300, n=K,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}])
                return {"persona_id": pid, "arm": arm, "weight_bank": p["weight_bank"],
                        "sido": p["skeleton"]["sido"], "sido_name": p["skeleton"]["sido_name"],
                        "card_ideology": p["drawn"]["ideology_label"],
                        "donor_partylr": beliefs.get(pid, {}).get("donor_partylr"),
                        "options": options,
                        "samples": [c.message.content for c in r.choices],
                        "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens}}
            except Exception as e:
                if attempt == 2:
                    return {"persona_id": pid, "arm": arm, "error": str(e)}
                time.sleep(2 * (attempt + 1))

    tot = {"in": 0, "out": 0}
    for arm in ARMS:
        path = OUT / f"raw_{arm}{'_smoke' if args.smoke else ''}.jsonl"
        done = set()
        if path.exists():
            for l in open(path, encoding="utf-8"):
                try:
                    done.add(json.loads(l)["persona_id"])
                except Exception:
                    pass
        todo = [i for i in ids if i not in done]
        print(f"[{arm}암] {len(todo)}명 (스킵 {len(done)})")
        with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(CONCURRENCY) as ex:
            futs = {ex.submit(call_one, arm, i): i for i in todo}
            for n, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if "usage" in rec:
                    tot["in"] += rec["usage"]["in"]
                    tot["out"] += rec["usage"]["out"]
                if n % 100 == 0:
                    print(f"  {n}/{len(todo)}")
    print(f"완료. 실비용 ~${tot['in']/1e6*0.15 + tot['out']/1e6*0.60:.2f}")
    print("다음: python scripts/score_ab.py" + (" --smoke" if args.smoke else ""))


if __name__ == "__main__":
    main()
