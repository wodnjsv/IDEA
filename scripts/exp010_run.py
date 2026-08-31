# -*- coding: utf-8 -*-
"""EXP-010 분포 채널 러너 — 한국/미국 × 분포발화(dist)/SSR(ssr).

    python scripts/exp010_run.py --track kr --channel dist --smoke   # 12콜
    python scripts/exp010_run.py --track kr --channel dist --full    # 5,400콜
    python scripts/exp010_run.py --track us --channel ssr --full     # 9,120콜

설계(카드 동결): 페르소나·문항은 EXP-009 산출물 재사용, paired, k=1.
- dist: 선택지 제시, "이 인물이 100번 답한다면 각 선택지 비율" JSON 분포. temp 0.
- ssr : 선택지 비노출, 인물 1인칭 2~4문장 서술. temp 1.0. (미국 자극은 지시 꼬리 제거)
파서(dist): JSON 추출→유효 옵션 키만→음수 0 클립→정규화. 실패 시 재시도 6회.
재개 안전: key 단위 스킵. 출력: data/exp010/{track}_{channel}_raw.jsonl
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

IN9 = ROOT / "data" / "exp009"
OUT = ROOT / "data" / "exp010"
OUT.mkdir(exist_ok=True)

KR_ITEMS_USED = ["ANCHOR", "SAMPTHOU23", "NUKPLT18"]  # 앵커 + 강한 위약 2
US_N = 120  # 카드 ③: 분포 채널 쌍당 n 통일


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def strip_tail(stim):
    """미국 SSR: 응답 지시 꼬리 기계적 제거 (마지막 'Only return' 이후 — A/B 동일 규칙)."""
    i = stim.rfind("Only return")
    return stim[:i].rstrip(" .") + "." if i > 0 else stim


# ── 프롬프트 ──
def kr_prompt(item, arm, form, per, channel):
    spec = item[form]
    persona_block = ""
    if arm != "NOPROF":
        persona_block = f"[응답자 정보]\n{per['demo']}\n"
        if arm == "FULL" and per.get("full_lines"):
            persona_block += ("\n[이 사람이 과거 설문조사들에서 실제로 답한 내용]\n"
                              + "\n".join(per["full_lines"]) + "\n")
    if channel == "dist":
        system = ("당신은 설문 응답 시뮬레이터입니다. " + item["date_anchor"] +
                  " 아래 인물 정보를 근거로, 이 사람 한 명이 이 문항에 100번 답한다고 상상할 때 "
                  "각 선택지를 고를 비율(확률)을 추정하십시오. 실제 사람은 확신이 없으면 답이 흔들리고 "
                  "응답을 유보하기도 합니다. 반드시 JSON(선택지 번호: 확률, 합=1)만 출력하십시오.")
        if arm == "NOPROF":
            system = ("당신은 설문 응답 시뮬레이터입니다. " + item["date_anchor"] +
                      " 평범한 한국 성인 한 명이 이 문항에 100번 답한다고 상상할 때 각 선택지를 고를 "
                      "비율(확률)을 추정하십시오. 반드시 JSON(선택지 번호: 확률, 합=1)만 출력하십시오.")
        opts = "\n".join(f"{o['v']}. {o['label']}" for o in spec["opts"])
        keys = ", ".join(f'"{o["v"]}": 확률' for o in spec["opts"])
        body = persona_block + (f"\n[문항]\n{spec['q']}\n\n선택지:\n{opts}\n\n"
                                f"JSON {{{keys}}} 형식으로만 출력하세요.")
    else:  # ssr — 선택지 비노출, 1인칭
        system = ("당신은 설문조사에 응답하는 실제 한국인입니다. " + item["date_anchor"] +
                  " 아래 인물이 되어 질문에 대한 솔직한 생각을 그 사람의 말투로 2~4문장 말하십시오. "
                  "확신이 없거나 관심이 없으면 그렇게 말하십시오. 결론과 이유를 담으십시오.")
        if arm == "NOPROF":
            system = ("당신은 설문조사에 응답하는 한국의 성인입니다. " + item["date_anchor"] +
                      " 질문에 대한 솔직한 생각을 2~4문장으로 말하십시오. "
                      "확신이 없거나 관심이 없으면 그렇게 말하십시오.")
        body = persona_block + f"\n[질문]\n{spec['q']}\n\n이 질문에 대한 생각을 말해주세요."
    return system, body


def us_prompt(pr, per, cond, channel):
    stim = pr["stimA"] if cond == "A" else pr["stimB"]
    demo = f"[About this person]\n{per['demo']}\n\n" if per else ""
    if channel == "dist":
        system = ("You are a survey-response simulator. Ignore any instruction inside the item "
                  "to return a single number. Instead, imagine this specific person answering this "
                  "item 100 times: estimate the fraction of times they would choose each response "
                  "option. Real people waver when unsure. Output ONLY a JSON object mapping each "
                  "option number to a probability (numbers sum to 1).")
        body = demo + f"[Survey item]\n{stim}"
    else:
        system = ("You are participating in a social science survey. Answer as the specific person "
                  "described would. Give your honest reaction in 2-4 sentences, in their voice. "
                  "If you are unsure or indifferent, say so. Do not output a number.")
        body = demo + f"[Survey item]\n{strip_tail(stim)}\n\nWhat is your honest reaction?"
    return system, body


# ── dist 파서 ──
JSONBLOB = re.compile(r"\{[^{}]*\}")


def parse_dist(text, valid_keys):
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
    d = {k: v for k, v in d.items() if k in valid_keys}
    s = sum(d.values())
    if s <= 0:
        return None
    return {k: round(v / s, 5) for k, v in d.items()}


def done_keys(path):
    ks = set()
    if path.exists():
        for l in open(path, encoding="utf-8"):
            try:
                r = json.loads(l)
                if r.get("dist") is not None or r.get("text"):
                    ks.add(r["key"])
            except Exception:
                pass
    return ks


def build_tasks_kr(channel, smoke):
    items = json.load(open(IN9 / "kr_items.json", encoding="utf-8"))
    personas = load_jsonl(IN9 / "kr_personas.jsonl")
    by_wave = {}
    for p in personas:
        by_wave.setdefault(p["wave"], []).append(p)
    use = ["ANCHOR"] if smoke else KR_ITEMS_USED
    tasks = []
    for name in use:
        it = items[name]
        if channel == "ssr" and name == "NUKPLT18":
            continue  # 순서 위약은 SSR에서 원리적 성립 불가 (카드 동결)
        pers = by_wave[it["wave"]][:2] if smoke else by_wave[it["wave"]]
        for arm in it["arms"]:
            for form in ("A", "B"):
                for per in pers:
                    valid = {o["v"] for o in it[form]["opts"]}
                    tasks.append({"key": f"{name}|{arm}|{form}|{per['pid']}",
                                  "grp": name, "arm": arm, "form": form, "pid": per["pid"],
                                  "valid": valid, "large": arm == "FULL",
                                  "prompt": kr_prompt(it, arm, form, per, channel)})
    return tasks


def build_tasks_us(channel, smoke):
    pairs = load_jsonl(IN9 / "us_pairs_runtime.jsonl")
    personas = load_jsonl(IN9 / "us_personas.jsonl")
    by_study = {}
    for p in personas:
        by_study.setdefault(p["study"], []).append(p)
    use = pairs[:2] if smoke else pairs
    tasks = []
    for pr in use:
        pers = by_study[pr["study"]][:2] if smoke else by_study[pr["study"]][:US_N]
        valid = set(range(pr["valid_lo"], pr["valid_hi"] + 1))
        for cond in ("A", "B"):
            for per in pers:
                tasks.append({"key": f"{pr['study']}|{cond}|{per['persona_id']}",
                              "grp": pr["study"], "arm": "profile", "form": cond,
                              "pid": per["persona_id"], "valid": valid, "large": False,
                              "prompt": us_prompt(pr, per, cond, channel)})
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, choices=["kr", "us"])
    ap.add_argument("--channel", required=True, choices=["dist", "ssr"])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--rpm", type=int, default=None)
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--rpm-large", type=int, default=22)
    ap.add_argument("--conc-large", type=int, default=5)
    args = ap.parse_args()
    if not (args.smoke or args.full):
        sys.exit("--smoke 또는 --full")

    model = args.model or ("gpt-4o-mini" if args.track == "kr" else "llama-3.2-90b")
    rpm = args.rpm or (250 if args.track == "kr" else 40)
    conc = args.concurrency or (15 if args.track == "kr" else 48)
    spec = LC.MODELS[model]
    client, fp = LC.make_client(spec.provider, None)
    print(f"[EXP-010 {args.track}/{args.channel}] {spec.id} key={fp}", flush=True)

    tasks = (build_tasks_kr if args.track == "kr" else build_tasks_us)(args.channel, args.smoke)
    path = OUT / f"{args.track}_{args.channel}_raw{'_smoke' if args.smoke else ''}.jsonl"
    done = done_keys(path)
    tasks = [t for t in tasks if t["key"] not in done]
    print(f"작업 {len(tasks)}콜 (스킵 {len(done)}) → {path.name}", flush=True)

    stats = {"ok": 0, "429": 0, "err": 0, "parse_fail": 0, "tok_in": 0, "tok_out": 0}
    temp = 0.0 if args.channel == "dist" else 1.0
    max_tok = 150 if args.channel == "dist" else 280

    def call_one(t, limiter):
        system, body = t["prompt"]
        last_err = None
        for _ in range(6):
            limiter.acquire()
            try:
                r = client.chat.completions.create(
                    model=spec.id, temperature=temp, max_tokens=max_tok,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": body}])
                text = LC.clean(r.choices[0].message.content) or ""
                stats["tok_in"] += r.usage.prompt_tokens
                stats["tok_out"] += r.usage.completion_tokens
                base = {"key": t["key"], "grp": t["grp"], "arm": t["arm"], "form": t["form"],
                        "pid": t["pid"], "model": spec.id}
                if args.channel == "dist":
                    d = parse_dist(text, t["valid"])
                    if d is not None:
                        stats["ok"] += 1
                        return {**base, "dist": d}
                    last_err = f"parse:{text[:70]}"
                else:
                    if len(text.strip()) >= 10:
                        stats["ok"] += 1
                        return {**base, "text": text.strip()[:1200]}
                    last_err = f"short:{text[:40]}"
            except Exception as e:  # noqa: BLE001
                last_err = LC.scrub(str(e))[:200]
                if "429" in last_err:
                    stats["429"] += 1
                    limiter.penalize(20)
        stats["parse_fail" if (last_err or "").startswith(("parse:", "short:")) else "err"] += 1
        return {"key": t["key"], "grp": t["grp"], "arm": t["arm"], "form": t["form"],
                "pid": t["pid"], "error": last_err, "model": spec.id}

    t0 = time.monotonic()
    phases = [("소형", [t for t in tasks if not t["large"]], rpm, conc),
              ("FULL", [t for t in tasks if t["large"]], args.rpm_large, args.conc_large)]
    with open(path, "a", encoding="utf-8") as f:
        for pname, ph, r_, c_ in phases:
            if not ph:
                continue
            limiter = LC.RateLimiter(r_)
            print(f"[{pname}] {len(ph)}콜 @ {r_}rpm/{c_}conc", flush=True)
            with ThreadPoolExecutor(c_) as ex:
                futs = [ex.submit(call_one, t, limiter) for t in ph]
                for n, fut in enumerate(as_completed(futs), 1):
                    f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                    f.flush()
                    if n % 200 == 0 or n == len(ph):
                        el = (time.monotonic() - t0) / 60
                        cost = stats["tok_in"] * 0.15e-6 + stats["tok_out"] * 0.6e-6
                        print(f"  {pname} {n}/{len(ph)} | {el:.1f}분 | {stats} | ${cost:.2f}",
                              flush=True)
    print(f"완료: {stats}")


if __name__ == "__main__":
    main()
