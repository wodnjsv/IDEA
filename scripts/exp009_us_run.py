# -*- coding: utf-8 -*-
"""EXP-009 미국장 러너 — paired(동일 페르소나 A/B 각각 독립 호출) × k3.

    python scripts/exp009_us_run.py --probe               # 암기 프로브(실측 17쌍, 발사 전 1회)
    python scripts/exp009_us_run.py --smoke               # 2쌍 × 2명 × 2조건 × k1 = 8콜
    python scripts/exp009_us_run.py --full                # 45,360콜 (~2일)

재개 안전: key(study|cond|persona|rep) 성공분 스킵. 원자료: data/exp009/us_raw.jsonl
파서: 응답 첫 정수 → 쌍별 유효범위(valid_lo..hi) 검증. temperature 1.0 동결(분포 보존).
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
INT = re.compile(r"-?\d+")

SYS_PROFILE = ("You are participating in a social science survey. Answer exactly as the specific "
               "person described in [About you] would actually answer. Follow the response "
               "instruction in the survey item precisely — output only the number, nothing else.")
SYS_NOPROF = ("You are participating in a social science survey. Follow the response instruction "
              "in the survey item precisely — output only the number, nothing else.")


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


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


def build_tasks(pairs, personas, smoke=False):
    by_study = {}
    for p in personas:
        by_study.setdefault(p["study"], []).append(p)
    tasks = []
    use_pairs = pairs[:2] if smoke else pairs
    for pr in use_pairs:
        pers = by_study.get(pr["study"], [])
        if smoke:
            pers = pers[:2]
        reps = 1 if smoke else K
        for cond in ("A", "B"):
            stim = pr["stimA"] if cond == "A" else pr["stimB"]
            for per in pers:
                for rep in range(reps):
                    tasks.append({"key": f"{pr['study']}|{cond}|{per['persona_id']}|r{rep}",
                                  "study": pr["study"], "cond": cond, "profile": True,
                                  "lo": pr["valid_lo"], "hi": pr["valid_hi"],
                                  "system": SYS_PROFILE,
                                  "user": f"[About you]\n{per['demo']}\n\n[Survey item]\n{stim}"})
            if pr["noprofile_arm"] and not smoke:
                for i in range(120):
                    for rep in range(K):
                        tasks.append({"key": f"{pr['study']}|{cond}|NP{i}|r{rep}",
                                      "study": pr["study"], "cond": cond, "profile": False,
                                      "lo": pr["valid_lo"], "hi": pr["valid_hi"],
                                      "system": SYS_NOPROF, "user": f"[Survey item]\n{stim}"})
    return tasks


def build_probe_tasks(pairs):
    tasks = []
    for pr in pairs:
        if pr["role"] != "real":
            continue
        q = ("A published survey experiment showed respondents one of two versions of an item.\n"
             f"Version A: {pr['stimA'][:400]}\nVersion B: {pr['stimB'][:400]}\n\n"
             "Do you know this specific study and its published quantitative results? "
             "If you know the actual published effect, state the study name and the numeric effect. "
             "If you do not know this specific study's published results, reply exactly UNKNOWN.")
        tasks.append({"key": f"probe|{pr['study']}", "study": pr["study"], "cond": "probe",
                      "profile": False, "lo": None, "hi": None,
                      "system": "Answer honestly about your knowledge.", "user": q})
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--model", default="llama-3.1-70b")
    ap.add_argument("--rpm", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--key-file", default=None)
    args = ap.parse_args()
    if not (args.smoke or args.full or args.probe):
        sys.exit("--smoke / --full / --probe 중 하나")

    spec = LC.MODELS[args.model]
    client, fp = LC.make_client(spec.provider, args.key_file)
    print(f"[백엔드] {spec.id} cutoff={spec.cutoff} key={fp} | {args.rpm}rpm/{args.concurrency}conc",
          flush=True)

    pairs = load_jsonl(OUT / "us_pairs_runtime.jsonl")
    if args.probe:
        tasks = build_probe_tasks(pairs)
        path = OUT / "us_probe.jsonl"
    else:
        personas = load_jsonl(OUT / "us_personas.jsonl")
        tasks = build_tasks(pairs, personas, smoke=args.smoke)
        path = OUT / f"us_raw{'_smoke' if args.smoke else ''}.jsonl"
    done = done_keys(path)
    tasks = [t for t in tasks if t["key"] not in done]
    print(f"작업 {len(tasks)}콜 (스킵 {len(done)}) → {path.name}", flush=True)

    stats = {"429": 0, "err": 0, "parse_fail": 0, "ok": 0}
    limiter = LC.RateLimiter(args.rpm)

    def call_one(t):
        last_err = None
        probe = t["cond"] == "probe"
        for _ in range(6):
            limiter.acquire()
            try:
                r = client.chat.completions.create(
                    model=spec.id, temperature=0.0 if probe else 1.0,
                    max_tokens=300 if probe else 16,
                    messages=[{"role": "system", "content": t["system"]},
                              {"role": "user", "content": t["user"]}])
                text = LC.clean(r.choices[0].message.content) or ""
                if probe:
                    stats["ok"] += 1
                    return {"key": t["key"], "study": t["study"], "cond": t["cond"],
                            "pred": text[:500], "model": spec.id}
                m = INT.search(text)
                if m:
                    v = int(m.group(0))
                    if t["lo"] <= v <= t["hi"]:
                        stats["ok"] += 1
                        return {"key": t["key"], "study": t["study"], "cond": t["cond"],
                                "profile": t["profile"], "pred": v, "model": spec.id,
                                "usage": {"in": r.usage.prompt_tokens, "out": r.usage.completion_tokens}}
                last_err = f"parse:{text[:60]}"
            except Exception as e:  # noqa: BLE001
                last_err = LC.scrub(str(e))[:200]
                if "429" in last_err:
                    stats["429"] += 1
                    limiter.penalize(30)
        stats["parse_fail" if (last_err or "").startswith("parse:") else "err"] += 1
        return {"key": t["key"], "study": t["study"], "cond": t["cond"],
                "profile": t.get("profile"), "pred": None, "error": last_err, "model": spec.id}

    t0 = time.monotonic()
    with open(path, "a", encoding="utf-8") as f:
        with ThreadPoolExecutor(args.concurrency) as ex:
            futs = [ex.submit(call_one, t) for t in tasks]
            for n, fut in enumerate(as_completed(futs), 1):
                f.write(json.dumps(fut.result(), ensure_ascii=False) + "\n")
                f.flush()
                if n % 200 == 0 or n == len(tasks):
                    el = (time.monotonic() - t0) / 60
                    print(f"  {n}/{len(tasks)} | {el:.1f}분 | ok {stats['ok']} 429 {stats['429']} "
                          f"err {stats['err']} parse {stats['parse_fail']}", flush=True)
    print(f"완료: {stats}")


if __name__ == "__main__":
    main()
