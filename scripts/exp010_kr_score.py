# -*- coding: utf-8 -*-
"""EXP-010 한국장 채점 — 채널(강제선택[EXP-009] vs dist vs ssr) × 3암 게이트 판정.

지표(카드 동결): 앵커 Δ=(P지원−P견제)_A−(동)_B [게이트 G1: [4.3,39]] ·
위약 |Δ| [G2] · 유보 질량 [G3: >5%] · 절대 분포 TVD·평균 엔트로피 [G5].
SSR: 텍스트→임베딩→앵커 문장(기계 규칙: "내 생각: "+라벨, 유보류는 고정 문구)
유사도→softmax(τ). τ는 DEMO암 A형 집단분포와 인간 A분포(38/45/17)의 TVD 최소로
1회 캘리브레이션 후 전 문항·전 암 고정 (개발셋 지표 — 대외 인용 금지).
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402

D9 = ROOT / "data" / "exp009"
D10 = ROOT / "data" / "exp010"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rng = np.random.default_rng(20260828)
B = 4000
HUMAN_A = {1: 0.38, 2: 0.45, 9: 0.17}
HUMAN_B = {1: 0.31, 2: 0.51, 9: 0.18}

items = json.load(open(D9 / "kr_items.json", encoding="utf-8"))


def anchor_sentence(label):
    if "유보" in label or "모르" in label:
        return "잘 모르겠다. 아직 판단을 유보하고 싶다."
    return f"내 생각: {label}"


def load_dist_rows(path):
    """→ {(grp, arm)}{pid}{form} = dist(dict int→p)"""
    out = defaultdict(lambda: defaultdict(lambda: {}))
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        if r.get("dist") is None:
            continue
        out[(r["grp"], r["arm"])][r["pid"]][r["form"]] = {int(k): v for k, v in r["dist"].items()}
    return out


def ssr_embed_once(path):
    """SSR 텍스트·앵커 문장 임베딩 1회 계산 (τ와 무관) → (rows, sims 목록)."""
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
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

    anchors = {}
    for name, it in items.items():
        for form in ("A", "B"):
            opts = it[form]["opts"]
            sents = [anchor_sentence(o["label"]) for o in opts]
            anchors[(name, form)] = ([o["v"] for o in opts], embed(sents))
    V = embed([r["text"] for r in rows])
    sims = []
    for r, v in zip(rows, V):
        keys, AV = anchors[(r["grp"], r["form"])]
        sims.append((keys, AV @ v))
    return rows, sims


def ssr_apply_tau(rows, sims, tau):
    out = defaultdict(lambda: defaultdict(lambda: {}))
    for r, (keys, s) in zip(rows, sims):
        p = np.exp(tau * s)
        p = p / p.sum()
        out[(r["grp"], r["arm"])][r["pid"]][r["form"]] = dict(zip(keys, p.round(5)))
    return out


def load_forced(path):
    """EXP-009 강제선택 → 페르소나별 k3 풀링 경험 분포."""
    cnt = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        if r.get("pred") is None:
            continue
        cnt[(r["item"], r["arm"])][r["pid"]][r["form"]].append(r["pred"])
    out = defaultdict(lambda: defaultdict(lambda: {}))
    for ga, pids in cnt.items():
        for pid, forms in pids.items():
            for form, preds in forms.items():
                ks = sorted(set(preds))
                out[ga][pid][form] = {k: preds.count(k) / len(preds) for k in ks}
    return out


def group_dist(pid_map, form, keys):
    ps = [d[form] for d in pid_map.values() if form in d]
    if not ps:
        return None
    return {k: float(np.mean([p.get(k, 0.0) for p in ps])) for k in keys}


def anchor_delta(pid_map):
    diffs = []
    for d in pid_map.values():
        if "A" not in d or "B" not in d:
            continue
        gA = d["A"].get(1, 0) - d["A"].get(2, 0)
        gB = d["B"].get(1, 0) - d["B"].get(2, 0)
        diffs.append(gA - gB)
    if len(diffs) < 15:
        return None
    diffs = np.array(diffs)
    idx = rng.integers(0, len(diffs), (B, len(diffs)))
    bs = diffs[idx].mean(axis=1) * 100
    return diffs.mean() * 100, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), len(diffs)


def placebo_delta(pid_map, item_name):
    """정렬(라벨 매칭) 후 범주별 Δ 최대 |Δ|."""
    it = items[item_name]
    la = {o["v"]: o["label"].replace(" ", "") for o in it["A"]["opts"]}
    lb = {o["v"]: o["label"].replace(" ", "") for o in it["B"]["opts"]}
    bmap = {vb: next((va for va, s in la.items() if s == sb), vb) for vb, sb in lb.items()}
    cats = sorted(la)
    best = None
    for c in cats:
        diffs = []
        for d in pid_map.values():
            if "A" not in d or "B" not in d:
                continue
            a = d["A"].get(c, 0.0)
            b = sum(v for k, v in d["B"].items() if bmap.get(k) == c)
            diffs.append(a - b)
        if len(diffs) < 15:
            return None
        diffs = np.array(diffs)
        idx = rng.integers(0, len(diffs), (B, len(diffs)))
        bs = diffs[idx].mean(axis=1) * 100
        cand = (c, diffs.mean() * 100, float(np.percentile(bs, 2.5)),
                float(np.percentile(bs, 97.5)), len(diffs))
        if best is None or abs(cand[1]) > abs(best[1]):
            best = cand
    return best


def entropy(pid_map):
    hs = []
    for d in pid_map.values():
        for form in ("A", "B"):
            if form in d:
                p = np.array([v for v in d[form].values() if v > 0])
                hs.append(float(-(p * np.log(p)).sum()))
    return float(np.mean(hs)) if hs else None


def tvd(p, q):
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0) - q.get(k, 0)) for k in keys)


def report(tag, data):
    print(f"\n######## 채널: {tag} ########")
    res = {}
    for arm in ["NOPROF", "DEMO", "FULL"]:
        pm = data.get(("ANCHOR", arm), {})
        out = anchor_delta(pm)
        if out is None:
            continue
        d, lo, hi, n = out
        gA = group_dist(pm, "A", [1, 2, 9]) or {}
        gB = group_dist(pm, "B", [1, 2, 9]) or {}
        ent = entropy(pm)
        g1 = "O" if 4.3 <= d <= 39.0 else "X"
        g3 = "O" if min(gA.get(9, 0), gB.get(9, 0)) > 0.05 else "X"
        print(f"[앵커 {arm:6}] Δ={d:+6.2f} [{lo:+.1f},{hi:+.1f}] n={n} | G1(크기) {g1} | "
              f"유보 A {gA.get(9,0)*100:.1f}%/B {gB.get(9,0)*100:.1f}% G3 {g3} | 엔트로피 {ent:.3f}")
        print(f"    분포 A: 지원 {gA.get(1,0)*100:4.1f}/견제 {gA.get(2,0)*100:4.1f}/유보 {gA.get(9,0)*100:4.1f}"
              f"  (인간 38/45/17, TVD {tvd(gA, HUMAN_A):.3f})")
        print(f"    분포 B: 지원 {gB.get(1,0)*100:4.1f}/견제 {gB.get(2,0)*100:4.1f}/유보 {gB.get(9,0)*100:4.1f}"
              f"  (인간 31/51/18, TVD {tvd(gB, HUMAN_B):.3f})")
        res[arm] = {"delta": round(d, 2), "ci": [round(lo, 2), round(hi, 2)],
                    "distA": gA, "distB": gB, "entropy": ent}
    for name in ["SAMPTHOU23", "NUKPLT18"]:
        for arm in items[name]["arms"]:
            pm = data.get((name, arm), {})
            out = placebo_delta(pm, name)
            if out is None:
                continue
            c, d, lo, hi, n = out
            sig = "!" if (lo > 0 or hi < 0) else " "
            g2 = "O" if abs(d) <= 5 else "X"
            print(f"[위약 {name:11} {arm:6}] {sig} 최대|Δ| 범주{c}: {d:+6.2f} [{lo:+.1f},{hi:+.1f}] G2 {g2}")
            res[f"{name}|{arm}"] = {"cat": c, "delta": round(d, 2), "ci": [round(lo, 2), round(hi, 2)]}
    return res


# ── 실행 ──
forced = load_forced(D9 / "kr_raw.jsonl")
dist = load_dist_rows(D10 / "kr_dist_raw.jsonl")

# SSR τ 캘리브레이션 (DEMO암 A형 vs 인간 A 분포) — 임베딩 1회, τ 그리드만 재적용
ssr_rows, ssr_sims = ssr_embed_once(D10 / "kr_ssr_raw.jsonl")
best_tau, best_tvd = None, 9
for tau in [3, 5, 8, 12, 18, 25, 35, 50]:
    ssr_d = ssr_apply_tau(ssr_rows, ssr_sims, tau)
    gA = group_dist(ssr_d.get(("ANCHOR", "DEMO"), {}), "A", [1, 2, 9])
    t = tvd(gA, HUMAN_A) if gA else 9
    if t < best_tvd:
        best_tau, best_tvd = tau, t
print(f"SSR τ* = {best_tau} (DEMO-A TVD {best_tvd:.3f}) — 이후 고정")
ssr = ssr_apply_tau(ssr_rows, ssr_sims, best_tau)

all_res = {"tau": best_tau}
all_res["forced"] = report("강제선택 (EXP-009 기준선)", forced)
all_res["dist"] = report("분포 발화 (dist)", dist)
all_res["ssr"] = report(f"SSR (τ={best_tau})", ssr)
json.dump(all_res, io.open(D10 / "kr_score.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=float)
print("\n저장: data/exp010/kr_score.json")
