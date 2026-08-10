"""EXP-006 사후 지식 프로브 — 문서 컷오프의 경험적 반증 (ISS-012 보강).

페르소나 없이 모델에 직접 묻는다: 21대 대선 당선자를 아는가. ×N회(기본 20).
- 정답률 ≤ 우연 수준(~20%)이면 컷오프 주장과 정합
- 유의하게 높으면 모델카드 컷오프와 무관하게 MEMORIZATION_RISK
주의: 모델이 결과를 몰라도 사전지식(유력 후보)만으로 이재명을 '추측'할 수 있으므로,
정답률과 함께 응답 원문(확신 표현 vs 추측 표현)을 저장해 판정 근거로 남긴다.

    python scripts/probe_knowledge.py --model llama-3.1-70b --n 20
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402

QUESTION = (
    "2025년 6월 3일에 실시된 대한민국 제21대 대통령선거의 당선자는 누구입니까? "
    "모르면 반드시 '모른다'고 답하세요. 한 문장으로 답하세요."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="nvidia")
    ap.add_argument("--model", default="llama-3.1-70b")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--rpm", type=int, default=30)
    ap.add_argument("--key-file", default=None)
    args = ap.parse_args()

    client, fp = LC.make_client(args.provider, args.key_file)
    spec = LC.MODELS[args.model]
    print(f"모델 {spec.id} | 문서 컷오프 {spec.cutoff} | 키 {fp}")

    interval = 60.0 / args.rpm
    rows = []
    correct = dk = 0
    for i in range(args.n):
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=spec.id, temperature=1.0, max_tokens=100,
                messages=[{"role": "user", "content": QUESTION}],
            )
            text = LC.clean(r.choices[0].message.content) or ""
        except Exception as e:  # noqa: BLE001
            text = f"[ERROR] {LC.scrub(str(e))[:200]}"
        hit = "이재명" in text
        knows_not = any(w in text for w in ("모른다", "모릅니다", "모르겠", "알 수 없", "정보가 없", "확인할 수 없"))
        correct += hit
        dk += (not hit) and knows_not
        rows.append({"i": i, "hit": hit, "dk": knows_not, "text": text.strip()[:300]})
        print(f"  {i+1:2d}/{args.n} hit={hit} dk={knows_not} | {text.strip()[:80]!r}")
        time.sleep(max(0.0, interval - (time.time() - t0)))

    out = {
        "model": spec.id, "cutoff_doc": spec.cutoff, "n": args.n,
        "correct": correct, "correct_rate": correct / args.n,
        "dont_know": dk, "question": QUESTION, "rows": rows,
        "verdict_rule": "correct_rate<=0.2 → 컷오프 정합 / 유의 초과 → MEMORIZATION_RISK (EXP-006 사전등록)",
    }
    path = ROOT / "data" / "t3" / f"knowledge_probe_{args.model}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n정답률 {correct}/{args.n} = {correct/args.n:.0%} | '모른다' 응답 {dk}/{args.n}")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
