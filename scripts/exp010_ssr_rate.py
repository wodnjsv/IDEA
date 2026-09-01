# -*- coding: utf-8 -*-
"""EXP-010 미국장 SSR 측정기 — 서술 → 선택지 확률 매핑 (LLM 채점자, 카드 개정).

근거: 미국 자극은 선택지 라벨이 문장 내 비구조적(임베딩 앵커 기계 추출 불안정) →
gpt-4o-mini(temp 0, 컷오프 2023-10 < 코퍼스 공개 — 클린) 채점자로 매핑.
채점자는 문항 원문(선택지 정의 포함)과 서술만 받음 — 페르소나·실측 정보 미노출.
산출: data/exp010/us_ssr_scored.jsonl (dist 스키마 — exp010_us_score.py --raw 로 채점)
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402

D9 = ROOT / "data" / "exp009"
D10 = ROOT / "data" / "exp010"

SYS = ("You map a survey respondent's free-text reaction onto the response options of a survey "
       "item. Judge only from the reaction text. Output ONLY a JSON object mapping each option "
       "number to the probability that the reaction corresponds to that option (probabilities "
       "sum to 1). If the reaction is ambiguous or expresses uncertainty, spread probability "
       "accordingly.")
JSONBLOB = re.compile(r"\{[^{}]*\}")


def parse_dist(text, valid):
    m = JSONBLOB.search(text or "")
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
    except Exception:
        return None
    d = {}
    for k, v in raw.items():
        try:
            ki = int(re.sub(r"\D", "", str(k)) or -1)
            d[ki] = max(0.0, float(v))
        except Exception:
            continue
    d = {k: v for k, v in d.items() if k in valid}
    s = sum(d.values())
    return {k: round(v / s, 5) for k, v in d.items()} if s > 0 else None


def main():
    pairs = {p["study"]: p for p in
             (json.loads(l) for l in open(D9 / "us_pairs_runtime.jsonl", encoding="utf-8"))}
    rows = [json.loads(l) for l in open(D10 / "us_ssr_raw.jsonl", encoding="utf-8")]
    rows = [r for r in rows if r.get("text")]
    out_path = D10 / "us_ssr_scored.jsonl"
    done = set()
    if out_path.exists():
        for l in open(out_path, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("dist"):
                    done.add(r["key"])
            except Exception:
                pass
    rows = [r for r in rows if r["key"] not in done]
    spec = LC.MODELS["gpt-4o-mini"]
    client, fp = LC.make_client("openai", None)
    print(f"[SSR 채점자] {spec.id} key={fp} | 작업 {len(rows)} (스킵 {len(done)})", flush=True)

    stats = {"ok": 0, "err": 0, "parse_fail": 0, "tok_in": 0, "tok_out": 0}
    limiter = LC.RateLimiter(300)

    def rate(r):
        pr = pairs[r["grp"]]
        stim = pr["stimA"] if r["form"] == "A" else pr["stimB"]
        valid = set(range(pr["valid_lo"], pr["valid_hi"] + 1))
        user = (f"[Survey item and its response options]\n{stim}\n\n"
                f"[Respondent's free-text reaction]\n{r['text']}\n\n"
                "JSON probabilities:")
        last = None
        for _ in range(6):
            limiter.acquire()
            try:
                resp = client.chat.completions.create(
                    model=spec.id, temperature=0.0, max_tokens=150,
                    messages=[{"role": "system", "content": SYS},
                              {"role": "user", "content": user}])
                text = LC.clean(resp.choices[0].message.content) or ""
                stats["tok_in"] += resp.usage.prompt_tokens
                stats["tok_out"] += resp.usage.completion_tokens
                d = parse_dist(text, valid)
                if d:
                    stats["ok"] += 1
                    return {"key": r["key"], "grp": r["grp"], "arm": r["arm"],
                            "form": r["form"], "pid": r["pid"], "dist": d}
                last = f"parse:{text[:60]}"
            except Exception as e:  # noqa: BLE001
                last = LC.scrub(str(e))[:150]
                if "429" in last:
                    limiter.penalize(15)
        stats["parse_fail" if (last or "").startswith("parse:") else "err"] += 1
        return {"key": r["key"], "grp": r["grp"], "arm": r["arm"], "form": r["form"],
                "pid": r["pid"], "error": last}

    t0 = time.monotonic()
    with open(out_path, "a", encoding="utf-8") as f:
        with ThreadPoolExecutor(15) as ex:
            futs = [ex.submit(rate, r) for r in rows]
            for n, fut in enumerate(as_completed(futs), 1):
                f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                f.flush()
                if n % 500 == 0 or n == len(rows):
                    el = (time.monotonic() - t0) / 60
                    cost = stats["tok_in"] * 0.15e-6 + stats["tok_out"] * 0.6e-6
                    print(f"  {n}/{len(rows)} | {el:.1f}분 | {stats} | ${cost:.2f}", flush=True)
    print(f"완료: {stats}")


if __name__ == "__main__":
    main()
