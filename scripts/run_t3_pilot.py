"""EXP-004 T3 위생 실험 러너 (재원 맥 로컬 실행용).

사용:
    export OPENAI_API_KEY=sk-...   # 키는 환경변수로만 (코드·채팅 노출 금지)
    python scripts/run_t3_pilot.py --smoke          # 10명 × 3암 (~$0.04) — 품질 확인
    python scripts/run_t3_pilot.py --full           # 1,000명 × 3암 (~$1.2 추정)

- 모델 고정: gpt-4o-mini-2024-07-18 (컷오프 2023-10 < 선거일 — ISS-012 어서션)
- k=5는 n=5 파라미터로 1콜에 수집 (입력 토큰 1회 과금 — 비용 절감)
- 캐시: data/t3/raw_{arm}.jsonl append + 재개(resume) 지원 — 중단돼도 이어감 (T1 원칙)
- 집계는 반드시 weight_bank (ISS-016) — scripts/score_t3.py 사용
"""
import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine.prompts_t3 import build_prompt  # noqa: E402

MODEL = "gpt-4o-mini-2024-07-18"
MODEL_CUTOFF, ELECTION_DATE = "2023-10", "2025-06"
assert MODEL_CUTOFF < ELECTION_DATE, "MEMORIZATION_RISK: 컷오프가 선거일 이후 (ISS-012)"
TEMPERATURE = 1.0          # 오차축소 0단 규격 (phase0의 0.7에서 변경 — EXP-004 기록)
K = 5
CONCURRENCY = 8
SEED = 42
ARMS = ["A", "B", "C"]
BANK = ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl"
OUT = ROOT / "data" / "t3"
EST_IN_TOK, EST_OUT_TOK = 1000, 400   # 콜당 추정 (in: sys+카드+선택지 / out: 5샘플 JSON)
PRICE_IN, PRICE_OUT = 0.15, 0.60      # $/1M tokens (gpt-4o-mini)


def load_subsample(n):
    personas = [json.loads(l) for l in open(BANK, encoding="utf-8")]
    rng = random.Random(SEED)
    sub = rng.sample(personas, n) if n < len(personas) else personas
    return sub


def done_ids(path):
    if not path.exists():
        return set()
    ids = set()
    for l in open(path, encoding="utf-8"):
        try:
            ids.add(json.loads(l)["persona_id"])
        except Exception:
            pass
    return ids


def call_one(client, arm, persona):
    system, user, options = build_prompt(arm, persona)
    for attempt in range(3):
        try:
            r = client.chat.completions.create(
                model=MODEL, temperature=TEMPERATURE, max_tokens=300, n=K,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            return {"persona_id": persona["persona_id"], "arm": arm,
                    "weight_bank": persona["weight_bank"],
                    "sido": persona["skeleton"]["sido"], "sido_name": persona["skeleton"]["sido_name"],
                    "options": options,
                    "samples": [c.message.content for c in r.choices],
                    "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens}}
        except Exception as e:
            if attempt == 2:
                return {"persona_id": persona["persona_id"], "arm": arm, "error": str(e)}
            time.sleep(2 * (attempt + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--yes", action="store_true", help="비용 확인 프롬프트 생략")
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")
    n = 10 if args.smoke else 1000

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY 환경변수를 설정하세요 (키를 파일·채팅에 넣지 말 것)")
    from openai import OpenAI
    client = OpenAI()

    calls = n * len(ARMS)
    est = (calls * EST_IN_TOK / 1e6) * PRICE_IN + (calls * EST_OUT_TOK / 1e6) * PRICE_OUT
    print(f"[EXP-004] {n}명 × {len(ARMS)}암 = {calls}콜 | 예상 비용 ~${est:.2f} (상한 게이트 $500 — ISS-014)")
    if not args.yes:
        if input("진행? [y/N] ").strip().lower() != "y":
            sys.exit("중단")

    OUT.mkdir(parents=True, exist_ok=True)
    sub = load_subsample(n)
    json.dump([p["persona_id"] for p in sub], open(OUT / f"subsample_ids_{n}.json", "w"))

    total_usage = {"in": 0, "out": 0}
    for arm in ARMS:
        path = OUT / f"raw_{arm}{'_smoke' if args.smoke else ''}.jsonl"
        skip = done_ids(path)
        todo = [p for p in sub if p["persona_id"] not in skip]
        print(f"[{arm}암] {len(todo)}명 (재개 스킵 {len(skip)})")
        with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(CONCURRENCY) as ex:
            futs = {ex.submit(call_one, client, arm, p): p for p in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if "usage" in rec:
                    total_usage["in"] += rec["usage"]["in"]
                    total_usage["out"] += rec["usage"]["out"]
                if i % 50 == 0:
                    print(f"  {i}/{len(todo)}")
    cost = total_usage["in"] / 1e6 * PRICE_IN + total_usage["out"] / 1e6 * PRICE_OUT
    print(f"완료. 실사용 토큰 in={total_usage['in']:,} out={total_usage['out']:,} → 실비용 ~${cost:.2f}")
    print("다음: python scripts/score_t3.py" + (" --smoke" if args.smoke else ""))


if __name__ == "__main__":
    main()
