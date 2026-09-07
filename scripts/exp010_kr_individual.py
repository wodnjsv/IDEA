# -*- coding: utf-8 -*-
"""EXP-010 부속: 분포 채널의 **개인 수준** 재현 — KGSS 실제 답이 있는 위약 문항으로 채점.

한국장 페르소나(2023: EXP-008 평가셋 300 / 2018: 300)는 SAMPTHOU(2023 A/B폼)·NUKPLT10(2018 A/B폼)에
실제로 답했다(각자 한 폼만). 모델이 그 사람에게 준 분포(해당 폼)에서 실제 답의 확률을 읽어
개인 수준 예측력을 잰다. 채널: 강제선택(k3 비율) / 분포발화 / SSR(임베딩 τ=8).
지표: 범주별 AUC(P̂_k vs 실제==k) 평균, 개인 확률-실답 점이연 상관, 로그손실.
EXP-008(강제선택, 10문항 배터리)의 개인 상관 z=.19와 같은 질문의 분포 채널판.
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402
from engine.registry import resolve  # noqa: E402

D9, D10 = ROOT / "data" / "exp009", ROOT / "data" / "exp010"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
items = json.load(open(D9 / "kr_items.json", encoding="utf-8"))

df, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
num = df.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)
by_year = {y: (df[df["YEAR"] == y].reset_index(drop=True), num[df["YEAR"] == y].reset_index(drop=True))
           for y in (2018, 2023)}
FORMS = {"SAMPTHOU23": (2023, {"A": "SAMPTHOUA", "B": "SAMPTHOUB23"}),
         "NUKPLT18": (2018, {"A": "NUKPLT10A", "B": "NUKPLT10B"})}


def actual(pid, item):
    year, fv = FORMS[item]
    i = int(pid.split("_")[1])
    _, nw = by_year[year]
    for form, var in fv.items():
        v = nw.loc[i, var]
        if pd.notna(v):
            return form, int(v)
    return None, None


# ── 채널별 개인 분포 로드 ──
def load_dist():
    out = defaultdict(dict)
    for l in open(D10 / "kr_dist_raw.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r.get("dist"):
            out[(r["grp"], r["arm"], r["form"])][r["pid"]] = {int(k): v for k, v in r["dist"].items()}
    return out


def load_forced():
    cnt = defaultdict(lambda: defaultdict(list))
    for l in open(D9 / "kr_raw.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r.get("pred") is not None:
            cnt[(r["item"], r["arm"], r["form"])][r["pid"]].append(r["pred"])
    return {k: {pid: {c: preds.count(c) / len(preds) for c in set(preds)} for pid, preds in v.items()}
            for k, v in cnt.items()}


def load_ssr(tau=8):
    rows = [json.loads(l) for l in open(D10 / "kr_ssr_raw.jsonl", encoding="utf-8")]
    rows = [r for r in rows if r.get("text") and r["grp"] in FORMS]
    client, _ = LC.make_client("openai", None)

    def embed(texts):
        V = []
        for i in range(0, len(texts), 1000):
            resp = client.embeddings.create(model="text-embedding-3-small",
                                            input=[t[:2000] for t in texts[i:i + 1000]])
            V += [d.embedding for d in resp.data]
        V = np.array(V)
        return V / np.linalg.norm(V, axis=1, keepdims=True)

    def anchor(label):
        return "잘 모르겠다. 아직 판단을 유보하고 싶다." if ("유보" in label or "모르" in label) else f"내 생각: {label}"

    anchors = {}
    for name in FORMS:
        for form in ("A", "B"):
            opts = items[name][form]["opts"]
            anchors[(name, form)] = ([o["v"] for o in opts], embed([anchor(o["label"]) for o in opts]))
    V = embed([r["text"] for r in rows])
    out = defaultdict(dict)
    for r, v in zip(rows, V):
        keys, AV = anchors[(r["grp"], r["form"])]
        p = np.exp(tau * (AV @ v))
        out[(r["grp"], r["arm"], r["form"])][r["pid"]] = dict(zip(keys, p / p.sum()))
    return out


channels = {"강제선택(k3)": load_forced(), "분포발화": load_dist(), "SSR(임베딩)": load_ssr()}

print("개인 수준 재현 — 모델이 그 사람에게 준 확률 vs 그 사람의 실제 KGSS 답\n")
for item, (year, fv) in FORMS.items():
    cats = sorted({o["v"] for o in items[item]["A"]["opts"]})
    print(f"=== {item} ({year}, 실답 보유자만) ===")
    for ch, data in channels.items():
        for arm in items[item]["arms"]:
            P, Y = [], []
            for form in ("A", "B"):
                for pid, d in data.get((item, arm, form), {}).items():
                    f_act, y = actual(pid, item)
                    if f_act != form or y is None:
                        continue
                    # B폼 역순 라벨 → A 기준 의미로 정렬 (라벨 문자열 매칭)
                    if form == "B":
                        la = {o["label"].replace(" ", ""): o["v"] for o in items[item]["A"]["opts"]}
                        lb = {o["v"]: o["label"].replace(" ", "") for o in items[item]["B"]["opts"]}
                        d = {la[lb[k]]: v for k, v in d.items() if lb.get(k) in la}
                        y = la.get(lb.get(y), y)
                    P.append([d.get(c, 0.0) for c in cats])
                    Y.append(y)
            if len(Y) < 30:
                continue
            P, Y = np.array(P), np.array(Y)
            aucs, rs = [], []
            for j, c in enumerate(cats):
                yk = (Y == c).astype(int)
                if 0 < yk.sum() < len(yk):
                    aucs.append(roc_auc_score(yk, P[:, j]))
                    rs.append(np.corrcoef(P[:, j], yk)[0, 1])
            ll = float(np.mean([np.log(max(P[i, cats.index(Y[i])], 1e-6)) for i in range(len(Y))]))
            base = float(np.mean([np.log(max((Y == y).mean(), 1e-6)) for y in Y]))
            print(f"  {ch:12} {arm:6} n={len(Y):3d} | AUC {np.mean(aucs):.3f} | r {np.mean(rs):+.3f} | "
                  f"로그손실 {ll:.3f} (기저 {base:.3f}) | P̂ 분산 {P.std(axis=0).mean():.3f}")
    print()
print("해석: AUC .5 = 개인 정보 없음, r = EXP-008의 개인 상관과 같은 척도(강제선택 FULL 배터리 z≈.19)")
