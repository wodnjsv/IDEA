# -*- coding: utf-8 -*-
"""EXP-009 한국장 러너 — paired(동일 페르소나 A/B 독립 호출) × 3암 × k3, gpt-4o-mini.

    python scripts/exp009_kr_run.py --smoke     # 앵커 2명 × 3암 × 2형 × k1 = 12콜
    python scripts/exp009_kr_run.py --full      # 25,200콜 (~$8)

페이싱: FULL암(프로필 ~8k토큰)은 TPM 제한 대응 저속, 소형암 고속.
재개 안전: key(item|arm|form|pid|rep). 원자료: data/exp009/kr_raw.jsonl. temperature 1.0.
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

OUT = ROOT / "data" / "exp009"
K = 3
ANS = re.compile(r'"answer"\s*:\s*"?(\d+)')


def build_prompt(item, arm, form, persona):
    spec = item[form]
    system = ("당신은 설문조사에 응답하는 실제 한국인입니다. " + item["date_anchor"] +
              " 아래 인물이 되어, 그 사람이 실제로 답할 그대로 문항에 답하십시오. "
              '반드시 JSON 형식 {"answer": 선택지 번호}로만 답하십시오.')
    if arm == "NOPROF":
        system = ("당신은 설문조사에 응답하는 한국의 성인입니다. " + item["date_anchor"] +
                  ' 반드시 JSON 형식 {"answer": 선택지 번호}로만 답하십시오.')
        body = ""
    else:
        body = f"[응답자 정보]\n{persona['demo']}\n"
        if arm == "FULL" and persona.get("full_lines"):
            body += ("\n[이 사람이 과거 설문조사들에서 실제로 답한 내용]\n"
                     + "\n".join(persona["full_lines"]) + "\n")
    opts = "\n".join(f"{o['v']}. {o['label']}" for o in spec["opts"])
    body += (f"\n[문항]\n{spec['q']}\n\n선택지:\n{opts}\n\n"
             '위 문항에 답하세요. JSON {"answer": 번호}만 출력하세요.')
    return system, body


def done_keys(path):
    ks = set()
    if path.exists():
        for l in open(path, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("pred") is not None:
                    ks.add(r["key"])
            except Exception:
                pass
    return ks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--rpm", type=int, default=250, help="소형암(NOPROF/DEMO)")
    ap.add_argument("--concurrency", type=int, default=15)
    ap.add_argument("--rpm-large", type=int, default=22, help="FULL암 — TPM 제한 대응")
    ap.add_argument("--conc-large", type=int, default=5)
    ap.add_argument("--key-file", default=None)
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")

    spec = LC.MODELS[args.model]
    client, fp = LC.make_client(spec.provider, args.key_file)
    print(f"[백엔드] {spec.id} cutoff={spec.cutoff} key={fp}", flush=True)

    items = json.load(open(OUT / "kr_items.json", encoding="utf-8"))
    personas = [json.loads(l) for l in open(OUT / "kr_personas.jsonl", encoding="utf-8")]
    by_wave = {}
    for p in personas:
        by_wave.setdefault(p["wave"], []).append(p)

    path = OUT / f"kr_raw{'_smoke' if args.smoke else ''}.jsonl"
    done = done_keys(path)
    tasks = []
    use_items = {"ANCHOR": items["ANCHOR"]} if args.smoke else items
    for name, it in use_items.items():
        pers = by_wave[it["wave"]][:2] if args.smoke else by_wave[it["wave"]]
        reps = 1 if args.smoke else K
        for arm in it["arms"]:
            for form in ("A", "B"):
                for per in pers:
                    for rep in range(reps):
                        key = f"{name}|{arm}|{form}|{per['pid']}|r{rep}"
                        if key not in done:
                            tasks.append((key, name, it, arm, form, per, rep))
    print(f"작업 {len(tasks)}콜 (스킵 {len(done)}) → {path.name}", flush=True)

    stats = {"429": 0, "err": 0, "parse_fail": 0, "ok": 0, "tok_in": 0, "tok_out": 0}

    def call_one(key, name, it, arm, form, per, rep, limiter):
        system, body = build_prompt(it, arm, form, per)
        valid = {o["v"] for o in it[form]["opts"]}
        last_err = None
        for _ in range(6):
            limiter.acquire()
            try:
                r = client.chat.completions.create(
                    model=spec.id, temperature=1.0, max_tokens=40,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": body}])
                text = LC.clean(r.choices[0].message.content) or ""
                stats["tok_in"] += r.usage.prompt_tokens
                stats["tok_out"] += r.usage.completion_tokens
                m = ANS.search(text) or re.search(r"\b(\d+)\b", text)
                if m and int(m.group(1)) in valid:
                    stats["ok"] += 1
                    return {"key": key, "item": name, "arm": arm, "form": form,
                            "pid": per["pid"], "pred": int(m.group(1)), "model": spec.id}
                last_err = f"parse:{text[:60]}"
            except Exception as e:  # noqa: BLE001
                last_err = LC.scrub(str(e))[:200]
                if "429" in last_err:
                    stats["429"] += 1
                    limiter.penalize(20)
        stats["parse_fail" if (last_err or "").startswith("parse:") else "err"] += 1
        return {"key": key, "item": name, "arm": arm, "form": form,
                "pid": per["pid"], "pred": None, "error": last_err, "model": spec.id}

    t0 = time.monotonic()
    phases = [("소형", [t for t in tasks if t[3] != "FULL"], args.rpm, args.concurrency),
              ("FULL", [t for t in tasks if t[3] == "FULL"], args.rpm_large, args.conc_large)]
    with open(path, "a", encoding="utf-8") as f:
        for pname, ph, rpm, conc in phases:
            if not ph:
                continue
            limiter = LC.RateLimiter(rpm)
            print(f"[{pname}] {len(ph)}콜 @ {rpm}rpm/{conc}conc", flush=True)
            with ThreadPoolExecutor(conc) as ex:
                futs = [ex.submit(call_one, *t, limiter) for t in ph]
                for n, fut in enumerate(as_completed(futs), 1):
                    f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                    f.flush()
                    if n % 200 == 0 or n == len(ph):
                        el = (time.monotonic() - t0) / 60
                        cost = stats["tok_in"] * 0.15e-6 + stats["tok_out"] * 0.6e-6
                        print(f"  {pname} {n}/{len(ph)} | {el:.1f}분 | ok {stats['ok']} "
                              f"429 {stats['429']} err {stats['err']} parse {stats['parse_fail']} "
                              f"| ${cost:.2f}", flush=True)
    cost = stats["tok_in"] * 0.15e-6 + stats["tok_out"] * 0.6e-6
    print(f"완료: {stats} | 비용 ${cost:.2f}")


if __name__ == "__main__":
    main()
