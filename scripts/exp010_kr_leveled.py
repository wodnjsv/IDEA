# -*- coding: utf-8 -*-
"""EXP-010 부속 검증: 앵커 외 '다른 질문'의 절대 분포 재현 — KGSS 실측 대조.

SAMPTHOU23(2023, A/B폼)·NUKPLT18(2018, A/B폼)은 KGSS 실응답 분포(폼당 ~600명)가
정답지. 모델(강제선택/dist/ssr × 3암)의 집단 분포와 TVD 비교.
페르소나가 같은 웨이브 응답자 300명이므로 모집단 일치 대조.
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import resolve  # noqa: E402

D9 = ROOT / "data" / "exp009"
D10 = ROOT / "data" / "exp010"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── KGSS 실측 분포 ──
df, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
num = df.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)


def human_dist(var, year):
    s = num.loc[df["YEAR"] == year, var].dropna()
    return {int(k): float((s == k).mean()) for k in sorted(s.unique())}, len(s)


GT = {
    ("SAMPTHOU23", "A"): human_dist("SAMPTHOUA", 2023),
    ("SAMPTHOU23", "B"): human_dist("SAMPTHOUB23", 2023),
    ("NUKPLT18", "A"): human_dist("NUKPLT10A", 2018),
    ("NUKPLT18", "B"): human_dist("NUKPLT10B", 2018),
}

# ── 모델 분포 로더 (exp010_kr_score와 동일 로직 축약) ──
items = json.load(open(D9 / "kr_items.json", encoding="utf-8"))


def load_dist(path, key_dist="dist"):
    out = defaultdict(list)
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        if r.get(key_dist) is None:
            continue
        out[(r["grp"], r["arm"], r["form"])].append({int(k): v for k, v in r[key_dist].items()})
    return out


def load_forced(path):
    out = defaultdict(list)
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        if r.get("pred") is not None:
            out[(r["item"], r["arm"], r["form"])].append({r["pred"]: 1.0})
    return out


def load_ssr_tau():
    """kr_score.json의 τ로 SSR 분포 재계산 결과를 재현하는 대신, 저장된 τ 사용해 간단 재계산."""
    tau = json.load(open(D10 / "kr_score.json", encoding="utf-8"))["tau"]
    from engine import llm_client as LC
    rows = [json.loads(l) for l in open(D10 / "kr_ssr_raw.jsonl", encoding="utf-8")]
    rows = [r for r in rows if r.get("text")]
    client, _ = LC.make_client("openai", None)

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

    anchors = {}
    for name, it in items.items():
        for form in ("A", "B"):
            opts = it[form]["opts"]
            anchors[(name, form)] = ([o["v"] for o in opts],
                                     embed([anchor_sentence(o["label"]) for o in opts]))
    V = embed([r["text"] for r in rows])
    out = defaultdict(list)
    for r, v in zip(rows, V):
        keys, AV = anchors[(r["grp"], r["form"])]
        p = np.exp(tau * (AV @ v))
        p = p / p.sum()
        out[(r["grp"], r["arm"], r["form"])].append(dict(zip(keys, p)))
    return out


def gdist(plist, keys):
    return {k: float(np.mean([p.get(k, 0.0) for p in plist])) for k in keys}


def tvd(p, q):
    ks = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0) - q.get(k, 0)) for k in ks)


forced = load_forced(D9 / "kr_raw.jsonl")
dist = load_dist(D10 / "kr_dist_raw.jsonl")
ssr = load_ssr_tau()

for (grp, form), (hd, n) in GT.items():
    keys = sorted(hd)
    hs = " / ".join(f"{hd[k]*100:4.1f}" for k in keys)
    labels = {o['v']: o['label'] for o in items[grp][form]['opts']}
    print(f"\n=== {grp} {form}형 (KGSS 실측 n={n}) — 선택지 {[labels[k] for k in keys]}")
    print(f"  실측(정답)      : {hs}")
    for ch_name, data in [("강제선택", forced), ("분포발화", dist), ("SSR", ssr)]:
        for arm in items[grp]["arms"]:
            pl = data.get((grp, arm, form), [])
            if not pl:
                continue
            gd = gdist(pl, keys)
            ms = " / ".join(f"{gd[k]*100:4.1f}" for k in keys)
            print(f"  {ch_name:4} {arm:6} : {ms}   TVD {tvd(gd, hd):.3f}")
print("\nDONE")
