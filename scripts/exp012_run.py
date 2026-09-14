# -*- coding: utf-8 -*-
"""EXP-012 21대 대선 재현 — 분포 채널판 러너 (D1 라벨 포함 / D2 라벨 제거).

    python scripts/exp012_run.py --smoke        # 2암 × 10명
    python scripts/exp012_run.py --full         # 2암 × 1,000명 (EXP-004 부분표본)

채널: "이 인물이 100번 투표한다면 각 선택지 비율" JSON 분포, temperature 0,
선택지 순서 = EXP-004 persona_order(페르소나별 고정 시드 — paired 규약).
위생판 승계(x만). 자기진단 Step 없음. 출력 data/exp012/raw.jsonl (재개 안전).
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402
from engine.prompts_t3 import ABSTAIN, CANDIDATES, DK, SYSTEM_COMMON, persona_order  # noqa: E402

BANK = ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl"
SUB = ROOT / "data" / "t3" / "subsample_ids_1000.json"
OUT = ROOT / "data" / "exp012"
OUT.mkdir(exist_ok=True)
IDEO_PAT = re.compile(r"\s*정치적으로는 스스로 '[^']*' 성향이라고 생각합니다\.")
JSONBLOB = re.compile(r"\{[^{}]*\}")

SYS = (SYSTEM_COMMON + "\n\n이 과제에서는 답 하나를 고르지 않습니다. 아래 인물이 같은 선거를 100번 겪는다고 "
       "상상하고, 각 선택지를 고를 횟수의 비율(확률)을 추정하십시오. 실제 사람은 확신이 없으면 표가 갈리고, "
       "투표하지 않거나 답을 밝히지 않기도 합니다. 반드시 JSON(선택지 번호: 확률, 합=1)만 출력하십시오.")


def build(persona, arm):
    card = persona["card"]
    if arm == "D2":
        card = IDEO_PAT.sub("", card)
    opts = persona_order(persona["persona_id"], CANDIDATES) + [ABSTAIN, DK]
    lines = "\n".join(f"{i+1}. {o}" for i, o in enumerate(opts))
    keys = ", ".join(f'"{i+1}": 확률' for i in range(len(opts)))
    body = (f"[페르소나]\n{card}\n\n[과제]\n2025년 6월 3일 제21대 대통령선거 당일, 이 인물은 다음 중 누구에게 "
            f"투표했겠습니까? 100번 중 각 선택지를 고를 비율을 추정하세요.\n\n선택지:\n{lines}\n\n"
            f"JSON {{{keys}}} 형식으로만 출력하세요.")
    return SYS, body, opts


def parse(text, n):
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
            if 1 <= ki <= n:
                d[ki] = max(0.0, float(v))
        except Exception:
            continue
    s = sum(d.values())
    return {k: round(v / s, 5) for k, v in d.items()} if s > 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--rpm", type=int, default=250)
    ap.add_argument("--concurrency", type=int, default=15)
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")
    spec = LC.MODELS["gpt-4o-mini"]
    gate = LC.assert_cutoff(spec)
    client, fp = LC.make_client("openai", None)
    print(f"[EXP-012] {LC.describe('gpt-4o-mini', gate, fp)}", flush=True)

    ids = set(json.load(open(SUB, encoding="utf-8")))
    bank = {p["persona_id"]: p for p in (json.loads(l) for l in open(BANK, encoding="utf-8"))}
    personas = [bank[i] for i in sorted(ids) if i in bank]
    if args.smoke:
        personas = personas[:10]
    path = OUT / f"raw{'_smoke' if args.smoke else ''}.jsonl"
    done = set()
    if path.exists():
        for l in open(path, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("dist"):
                    done.add(r["key"])
            except Exception:
                pass
    tasks = [(p, arm) for arm in ("D1", "D2") for p in personas if f"{arm}|{p['persona_id']}" not in done]
    print(f"작업 {len(tasks)}콜 (스킵 {len(done)}) → {path.name}", flush=True)
    stats = {"ok": 0, "err": 0, "parse_fail": 0, "tok_in": 0, "tok_out": 0}
    limiter = LC.RateLimiter(args.rpm)

    def call(p, arm):
        system, body, opts = build(p, arm)
        last = None
        for _ in range(6):
            limiter.acquire()
            try:
                r = client.chat.completions.create(model=spec.id, temperature=0.0, max_tokens=160,
                                                   messages=[{"role": "system", "content": system},
                                                             {"role": "user", "content": body}])
                text = LC.clean(r.choices[0].message.content) or ""
                stats["tok_in"] += r.usage.prompt_tokens
                stats["tok_out"] += r.usage.completion_tokens
                d = parse(text, len(opts))
                base = {"key": f"{arm}|{p['persona_id']}", "arm": arm, "persona_id": p["persona_id"],
                        "sido_name": p["skeleton"]["sido_name"], "weight_bank": p["weight_bank"],
                        "ideology": p["drawn"].get("ideology_label"), "options": opts, "model": spec.id}
                if d:
                    stats["ok"] += 1
                    return {**base, "dist": {opts[k - 1]: v for k, v in d.items()}}
                last = f"parse:{text[:60]}"
            except Exception as e:  # noqa: BLE001
                last = LC.scrub(str(e))[:150]
                if "429" in last:
                    limiter.penalize(15)
        stats["parse_fail" if (last or "").startswith("parse:") else "err"] += 1
        return {"key": f"{arm}|{p['persona_id']}", "arm": arm, "persona_id": p["persona_id"], "error": last}

    t0 = time.monotonic()
    with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(args.concurrency) as ex:
        futs = [ex.submit(call, p, arm) for p, arm in tasks]
        for n, fut in enumerate(as_completed(futs), 1):
            f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
            f.flush()
            if n % 200 == 0 or n == len(tasks):
                cost = stats["tok_in"] * 0.15e-6 + stats["tok_out"] * 0.6e-6
                print(f"  {n}/{len(tasks)} | {(time.monotonic()-t0)/60:.1f}분 | {stats} | ${cost:.2f}", flush=True)
    print(f"완료: {stats}")


if __name__ == "__main__":
    main()
