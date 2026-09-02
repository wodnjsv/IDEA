# -*- coding: utf-8 -*-
"""EXP-010 사전 분석 2: SSR 측정기 3종 비교 — 최소대립 붕괴의 원인 분리.

대상: 기존 한국 SSR 서술(kr_ssr_raw.jsonl, 재호출 없음) — SAMPTHOU23(실패)·ANCHOR(대조).
측정기: (a) 라벨 임베딩+softmax(τ=8, 기존) (b) 증강 앵커 임베딩 앙상블(탐색)
       (c) LLM 채점자(gpt-4o-mini temp0 — 유사도 아닌 판정).
지표: 집단 분포와 실측(SAMPTHOU 33/67 · 앵커 A 38/45/17, B 31/51/18)의 TVD.
"""
import io
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402

D9 = ROOT / "data" / "exp009"
D10 = ROOT / "data" / "exp010"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

items = json.load(open(D9 / "kr_items.json", encoding="utf-8"))
rows = [json.loads(l) for l in open(D10 / "kr_ssr_raw.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("text") and r["grp"] in ("SAMPTHOU23", "ANCHOR")]
print(f"대상 서술 {len(rows)}행")

GT = {
    ("SAMPTHOU23", "A"): {1: 0.326, 2: 0.674},
    ("SAMPTHOU23", "B"): {1: 0.330, 2: 0.670},
    ("ANCHOR", "A"): {1: 0.38, 2: 0.45, 9: 0.17},
    ("ANCHOR", "B"): {1: 0.31, 2: 0.51, 9: 0.18},
}

# (b) 증강 앵커 — 선택지당 상세 진술 3개 (탐색: 연구자 작성, 자유도 명시)
AUG = {
    ("SAMPTHOU23", 1): [
        "그 정도 표본이면 충분하다. 표본조사를 제대로 하면 국민 전체의 여론을 꽤 정확하게 파악할 수 있다고 본다.",
        "여론조사는 믿을 만하다. 무작위로 뽑으면 일부만 조사해도 전체 여론의 흐름을 알 수 있다.",
        "통계적으로 표본이 대표성을 가지므로 그런 조사는 국민 생각을 잘 보여준다고 생각한다.",
    ],
    ("SAMPTHOU23", 2): [
        "겨우 그 인원으로 오천만 국민의 생각을 알 수 있다는 건 무리다. 여론조사는 실제 여론과 다를 때가 많다.",
        "여론조사는 못 믿겠다. 표본이 너무 적어서 전체 국민의 여론을 정확히 반영할 수 없다고 본다.",
        "그런 조사로는 국민 전체의 생각을 알 수 없다. 조사마다 결과가 다르고 틀리는 경우도 많지 않나.",
    ],
    ("ANCHOR", 1): [
        "정부가 일을 제대로 하려면 여당에 힘을 실어줘야 한다. 국정 안정이 우선이다.",
        "지금은 정부와 여당을 밀어줘야 할 때다. 발목만 잡아서는 되는 일이 없다.",
        "여당이 다수가 되어야 국정운영이 안정되고 정책이 추진력을 얻는다고 생각한다.",
    ],
    ("ANCHOR", 2): [
        "정부와 여당을 견제해야 한다. 야당에 힘을 실어줘서 균형을 잡아야 한다.",
        "지금 정부는 견제가 필요하다. 야당이 이겨서 일방적인 국정운영을 막아야 한다.",
        "권력 독주를 막으려면 야당 후보가 많이 당선되는 게 낫다고 본다.",
    ],
    ("ANCHOR", 9): [
        "글쎄, 아직 잘 모르겠다. 어느 쪽이라고 말하기 어렵다.",
        "둘 다 마음에 들지 않아서 판단을 유보하고 싶다.",
        "정치는 잘 몰라서 뭐라 답하기 어렵다. 좀 더 지켜봐야겠다.",
    ],
}

client, fp = LC.make_client("openai", None)
print(f"key={fp}")


def embed(texts):
    V = []
    for i in range(0, len(texts), 1000):
        resp = client.embeddings.create(model="text-embedding-3-small",
                                        input=[t[:2000] for t in texts[i:i + 1000]])
        V += [d.embedding for d in resp.data]
    V = np.array(V)
    return V / np.linalg.norm(V, axis=1, keepdims=True)


def anchor_sentence(label):
    if "유보" in label or "모르" in label:
        return "잘 모르겠다. 아직 판단을 유보하고 싶다."
    return f"내 생각: {label}"


TAU = 8
V_text = embed([r["text"] for r in rows])

# (a) 기존 라벨 앵커
plain = {}
for name in ("SAMPTHOU23", "ANCHOR"):
    for form in ("A", "B"):
        opts = items[name][form]["opts"]
        plain[(name, form)] = ([o["v"] for o in opts],
                               embed([anchor_sentence(o["label"]) for o in opts]))
# (b) 증강 앵커 (폼 무관 — 의미 기준. SAMPTHOU B형도 동일 진술)
aug = {}
for name in ("SAMPTHOU23", "ANCHOR"):
    keys = sorted({o["v"] for o in items[name]["A"]["opts"]})
    mats = {k: embed(AUG[(name, k)]) for k in keys}
    aug[name] = (keys, mats)

dists = {"plain": defaultdict(list), "aug": defaultdict(list), "judge": defaultdict(list)}
for r, v in zip(rows, V_text):
    keys, AV = plain[(r["grp"], r["form"])]
    p = np.exp(TAU * (AV @ v))
    dists["plain"][(r["grp"], r["arm"], r["form"])].append(dict(zip(keys, p / p.sum())))
    keys2, mats = aug[r["grp"]]
    sims = np.array([float(np.mean(mats[k] @ v)) for k in keys2])
    p2 = np.exp(TAU * sims)
    dists["aug"][(r["grp"], r["arm"], r["form"])].append(dict(zip(keys2, p2 / p2.sum())))

# (c) LLM 채점자
SYS = ("당신은 설문 응답 분류기입니다. 응답자의 자유 서술을 읽고, 그 사람이 아래 선택지 중 "
       "무엇을 골랐을지 확률로 판정하십시오. 서술 내용만 근거로 판단하고, 애매하면 확률을 "
       "나누십시오. 반드시 JSON(선택지 번호: 확률, 합=1)만 출력하십시오.")
import re  # noqa: E402
JSONBLOB = re.compile(r"\{[^{}]*\}")
limiter = LC.RateLimiter(300)
stats = {"ok": 0, "fail": 0, "tok_in": 0, "tok_out": 0}


def judge(idx_r):
    i, r = idx_r
    it = items[r["grp"]][r["form"]]
    opts = "\n".join(f"{o['v']}. {o['label']}" for o in it["opts"])
    valid = {o["v"] for o in it["opts"]}
    user = (f"[문항]\n{it['q']}\n\n[선택지]\n{opts}\n\n[응답자의 서술]\n{r['text']}\n\nJSON:")
    for _ in range(5):
        limiter.acquire()
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini-2024-07-18", temperature=0.0, max_tokens=120,
                messages=[{"role": "system", "content": SYS},
                          {"role": "user", "content": user}])
            text = LC.clean(resp.choices[0].message.content) or ""
            stats["tok_in"] += resp.usage.prompt_tokens
            stats["tok_out"] += resp.usage.completion_tokens
            m = JSONBLOB.search(text)
            if m:
                try:
                    raw = json.loads(m.group(0))
                    d = {}
                    for k, val in raw.items():
                        ki = int(re.sub(r"\D", "", str(k)) or -1)
                        if ki in valid:
                            d[ki] = max(0.0, float(val))
                    s = sum(d.values())
                    if s > 0:
                        stats["ok"] += 1
                        return i, {k: v / s for k, v in d.items()}
                except Exception:
                    pass
        except Exception as e:  # noqa: BLE001
            if "429" in str(e):
                limiter.penalize(15)
    stats["fail"] += 1
    return i, None


t0 = time.monotonic()
with ThreadPoolExecutor(15) as ex:
    futs = [ex.submit(judge, (i, r)) for i, r in enumerate(rows)]
    for n, fut in enumerate(as_completed(futs), 1):
        i, d = fut.result()
        if d:
            r = rows[i]
            dists["judge"][(r["grp"], r["arm"], r["form"])].append(d)
        if n % 600 == 0 or n == len(rows):
            print(f"  채점자 {n}/{len(rows)} | {(time.monotonic()-t0)/60:.1f}분 | {stats}", flush=True)


def gdist(plist, keys):
    return {k: float(np.mean([p.get(k, 0.0) for p in plist])) for k in keys}


def tvd(p, q):
    return 0.5 * sum(abs(p.get(k, 0) - q.get(k, 0)) for k in set(p) | set(q))


print("\n### 측정기 비교 (집단 분포 vs 실측, 인구암 기준 + 전체암 병기)")
summary = {}
for (grp, form), hd in GT.items():
    keys = sorted(hd)
    hs = " / ".join(f"{hd[k]*100:4.1f}" for k in keys)
    print(f"\n[{grp} {form}형] 실측: {hs}")
    for meter in ("plain", "aug", "judge"):
        for arm in items[grp]["arms"]:
            pl = dists[meter].get((grp, arm, form), [])
            if not pl:
                continue
            gd = gdist(pl, keys)
            ms = " / ".join(f"{gd[k]*100:4.1f}" for k in keys)
            t = tvd(gd, hd)
            print(f"  {meter:5} {arm:6}: {ms}   TVD {t:.3f}")
            summary[f"{grp}|{form}|{meter}|{arm}"] = {"dist": gd, "tvd": round(t, 4)}
json.dump(summary, io.open(D10 / "meter_compare.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
cost = stats["tok_in"] * 0.15e-6 + stats["tok_out"] * 0.6e-6
print(f"\n비용 ${cost:.2f} | 저장: meter_compare.json")
