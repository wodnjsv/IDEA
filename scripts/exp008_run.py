# -*- coding: utf-8 -*-
"""EXP-008 1단 러너 — 문항별 개별 호출 (배터리 1콜 오염 차단, Codex #5 반영).

    python scripts/exp008_run.py --smoke            # 2명 x 4암 x 10문항 ~= 80콜
    python scripts/exp008_run.py --full             # 300명 x 4암 x ~10문항 ~= 12,000콜

재개 안전: (pid|arm|var) 키로 성공분 스킵. 원자료: data/exp008/raw[_smoke].jsonl
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

OUT = ROOT / "data" / "exp008"
ARMS = ["K0", "K5", "FULL", "SHUF"]
ANS = re.compile(r'"answer"\s*:\s*"?(\d+)')


def build_prompt(p, arm, item):
    system = ("당신은 설문조사에 응답하는 실제 한국인입니다. 아래 [응답자 정보]의 인물이 되어, "
              "그 사람이 실제로 답할 그대로 문항에 답하십시오. "
              '반드시 JSON 형식 {"answer": 선택지 번호}로만 답하십시오.')
    lines = p["arms"][arm]
    body = f"[응답자 정보]\n{p['demo']}\n"
    if lines:
        body += "\n[이 사람이 과거 설문조사들에서 실제로 답한 내용]\n" + "\n".join(lines) + "\n"
    opts = "\n".join(f"{o['v']}. {o['label']}" for o in item["options"])
    body += (f"\n[문항]\n{item['q']}\n\n선택지:\n{opts}\n\n"
             '이 사람으로서 위 문항에 답하세요. JSON {"answer": 번호}만 출력하세요.')
    return system, body


def done_keys(path):
    ks = set()
    if path.exists():
        for l in open(path, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("pred") is not None:
                    ks.add((r["pid"], r["arm"], r["var"]))
            except Exception:
                pass
    return ks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--model", default="llama-3.1-70b")
    ap.add_argument("--rpm", type=int, default=20, help="소형 판(K0/K5) 분당 요청")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--rpm-large", type=int, default=8, help="대형 판(FULL/SHUF) — 토큰 스루풋 제한 대응")
    ap.add_argument("--conc-large", type=int, default=4)
    ap.add_argument("--key-file", default=None)
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")

    spec = LC.MODELS[args.model]
    client, fp = LC.make_client(spec.provider, args.key_file)
    print(f"[백엔드] {spec.id} cutoff={spec.cutoff} key={fp} | 소형 {args.rpm}rpm/{args.concurrency}conc "
          f"| 대형 {args.rpm_large}rpm/{args.conc_large}conc (스모크 실측: 429는 토큰 스루풋 제한)")

    profiles = [json.loads(l) for l in open(OUT / "profiles.jsonl", encoding="utf-8")]
    if args.smoke:
        profiles = profiles[:2]
    path = OUT / f"raw{'_smoke' if args.smoke else ''}.jsonl"
    done = done_keys(path)

    tasks = []
    for p in profiles:
        for arm in ARMS:
            if arm == "SHUF" and not p["arms"]["SHUF"]:
                continue
            for item in p["battery"]:
                if item["actual"] is None:
                    continue
                if (p["pid"], arm, item["var"]) not in done:
                    tasks.append((p, arm, item))
    print(f"작업 {len(tasks)}콜 (스킵 {len(done)}) → {path.name}")

    stats = {"429": 0, "err": 0, "parse_fail": 0, "ok": 0}

    def call_one(p, arm, item, limiter):
        system, body = build_prompt(p, arm, item)
        last_err = None
        for attempt in range(6):
            limiter.acquire()
            try:
                r = client.chat.completions.create(
                    model=spec.id, temperature=1.0, max_tokens=40,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": body}])
                text = LC.clean(r.choices[0].message.content)
                m = ANS.search(text or "") or re.search(r"\b(\d+)\b", text or "")
                if m:
                    v = int(m.group(1))
                    if any(o["v"] == v for o in item["options"]):
                        stats["ok"] += 1
                        return {"pid": p["pid"], "arm": arm, "var": item["var"], "pred": v,
                                "actual": item["actual"], "model": spec.id,
                                "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens}}
                last_err = f"parse:{(text or '')[:60]}"
            except Exception as e:  # noqa: BLE001
                last_err = LC.scrub(str(e))[:200]
                if "429" in last_err:
                    stats["429"] += 1
                    limiter.penalize(30)
        stats["parse_fail" if (last_err or "").startswith("parse:") else "err"] += 1
        return {"pid": p["pid"], "arm": arm, "var": item["var"], "pred": None,
                "actual": item["actual"], "error": last_err, "model": spec.id}

    t0 = time.monotonic()
    phases = [("소형", [t for t in tasks if t[1] in ("K0", "K5")], args.rpm, args.concurrency),
              ("대형", [t for t in tasks if t[1] in ("FULL", "SHUF")], args.rpm_large, args.conc_large)]
    with open(path, "a", encoding="utf-8") as f:
        for name, ph_tasks, rpm, conc in phases:
            if not ph_tasks:
                continue
            limiter = LC.RateLimiter(rpm)
            print(f"[{name}판] {len(ph_tasks)}콜 @ {rpm}rpm/{conc}conc", flush=True)
            with ThreadPoolExecutor(conc) as ex:
                futs = [ex.submit(call_one, *t, limiter) for t in ph_tasks]
                for n, fut in enumerate(as_completed(futs), 1):
                    f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                    f.flush()
                    if n % 100 == 0 or n == len(ph_tasks):
                        el = (time.monotonic() - t0) / 60
                        print(f"  {name} {n}/{len(ph_tasks)} | {el:.1f}분 | ok {stats['ok']} "
                              f"429 {stats['429']} err {stats['err']} parse {stats['parse_fail']}", flush=True)
    print(f"완료: {stats}")


if __name__ == "__main__":
    main()
