# -*- coding: utf-8 -*-
"""EXP-009 미국장 채점 (개정 2 규격).

부문① 민감도: 실측 17쌍 방향 일치 ≥13 (단측 이항 p=.0245)
부문② 특이도: 위약 20쌍 오탐(페르소나-부트스트랩 95% CI가 0 제외) ≤3
              + 위약 |Δ̂| 중앙값 ≤ 실측 |Δ̂| 중앙값 × 1/3
부문③ 크기: Δ_인간 ~ a + b·Δ_LLM, leave-study-out 교차검증
부문④ 개인화 보조: 무프로필판 10쌍 vs 프로필판 Δ 대조 (기술 보고)
정렬: align_rule 쌍(j6xgs)은 B 응답 (lo+hi)−x 재코딩 후 focal 비율.
Δ = focal_cat 응답 비율(A) − 비율(B), %p. paired 페르소나 부트스트랩(B=4000).
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "exp009"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rng = np.random.default_rng(20260828)
B = 4000

pairs = {p["study"]: p for p in
         (json.loads(l) for l in open(OUT / "us_pairs_runtime.jsonl", encoding="utf-8"))}
raw = [json.loads(l) for l in open(OUT / "us_raw.jsonl", encoding="utf-8")]
raw = [r for r in raw if r.get("pred") is not None]

# (study, profile) → persona → cond → [preds]
data = defaultdict(lambda: defaultdict(lambda: {"A": [], "B": []}))
for r in raw:
    persona = r["key"].split("|")[2]
    data[(r["study"], bool(r.get("profile")))][persona][r["cond"]].append(r["pred"])


def pair_delta(study, profile=True):
    """paired Δ(%p)와 부트스트랩 CI. 반환 (delta, lo, hi, n_persona) 또는 None."""
    pr = pairs[study]
    fc, lo_v, hi_v = pr["focal_cat"], pr["valid_lo"], pr["valid_hi"]
    rev = bool(pr["align_rule"])
    pers = data.get((study, profile), {})
    fa, fb = [], []
    for p, d in pers.items():
        if not d["A"] or not d["B"]:
            continue
        a = np.mean([v == fc for v in d["A"]])
        bvals = [((lo_v + hi_v) - v) if rev else v for v in d["B"]]
        b = np.mean([v == fc for v in bvals])
        fa.append(a)
        fb.append(b)
    if len(fa) < 20:
        return None
    fa, fb = np.array(fa), np.array(fb)
    diff = fa - fb
    delta = diff.mean() * 100
    idx = rng.integers(0, len(diff), (B, len(diff)))
    bs = diff[idx].mean(axis=1) * 100
    return delta, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), len(diff)


res = {"real": [], "null": [], "ref": []}
for study, pr in pairs.items():
    out = pair_delta(study, True)
    if out is None:
        print(f"  (미완) {study}: 페르소나 부족 — 스킵")
        continue
    d, lo, hi, n = out
    row = {"study": study, "subtype": pr["subtype"], "human_pp": pr["human_pp"],
           "llm_pp": round(d, 2), "ci": [round(lo, 2), round(hi, 2)], "n": n,
           "dir_match": bool(np.sign(d) == np.sign(pr["human_pp"]) and d != 0),
           "sig": bool(lo > 0 or hi < 0)}
    res[pr["role"]].append(row)

print("=== 부문① 민감도 (실측 17쌍) ===")
hits = sum(r["dir_match"] for r in res["real"])
n_real = len(res["real"])
for r in sorted(res["real"], key=lambda x: -abs(x["human_pp"])):
    mark = "O" if r["dir_match"] else "X"
    print(f"  {mark} {r['study']:7} {r['subtype']:14} 인간 {r['human_pp']:+6.1f} | "
          f"LLM {r['llm_pp']:+6.2f} [{r['ci'][0]:+.1f},{r['ci'][1]:+.1f}] n={r['n']}")
if n_real:
    p = binomtest(hits, n_real, 0.5, alternative="greater").pvalue
    verdict = "합격" if (hits >= 13 and n_real == 17) else ("불합격" if n_real == 17 else "미완")
    print(f"방향 일치 {hits}/{n_real} (이항 단측 p={p:.4f}) → 게이트(≥13/17): {verdict}")

print("\n=== 부문② 특이도 (위약 20쌍) ===")
fps = sum(r["sig"] for r in res["null"])
for r in res["null"]:
    mark = "!" if r["sig"] else " "
    print(f"  {mark} {r['study']:7} {r['subtype']:16} LLM {r['llm_pp']:+6.2f} "
          f"[{r['ci'][0]:+.1f},{r['ci'][1]:+.1f}]")
if res["null"] and res["real"]:
    med_n = float(np.median([abs(r["llm_pp"]) for r in res["null"]]))
    med_r = float(np.median([abs(r["llm_pp"]) for r in res["real"]]))
    ok_fp = fps <= 3
    ok_sep = med_n <= med_r / 3
    print(f"오탐 {fps}/{len(res['null'])} (게이트 ≤3: {'합격' if ok_fp else '불합격'}) | "
          f"|Δ| 중앙값 위약 {med_n:.2f} vs 실측 {med_r:.2f} (≤1/3: {'합격' if ok_sep else '불합격'})")

if len(res["real"]) >= 10:
    print("\n=== 부문③ 크기 (LOSO 회귀) ===")
    X = np.array([r["llm_pp"] for r in res["real"]])
    Y = np.array([r["human_pp"] for r in res["real"]])
    preds = []
    for i in range(len(X)):
        m = np.ones(len(X), bool)
        m[i] = False
        b, a = np.polyfit(X[m], Y[m], 1)
        preds.append(a + b * X[i])
    b_all, a_all = np.polyfit(X, Y, 1)
    r_loso = np.corrcoef(preds, Y)[0, 1]
    print(f"전체적합 b={b_all:.2f} a={a_all:.2f} | LOSO 예측상관 r={r_loso:.3f}")

print("\n=== 부문④ 개인화 보조 (무프로필판 10쌍) ===")
for study in [s for s, p in pairs.items() if p["noprofile_arm"]]:
    o_np = pair_delta(study, False)
    o_pf = pair_delta(study, True)
    if o_np and o_pf:
        print(f"  {study:7} 인간 {pairs[study]['human_pp']:+6.1f} | "
              f"프로필 {o_pf[0]:+6.2f} vs 무프로필 {o_np[0]:+6.2f}")

if res["ref"]:
    r = res["ref"][0]
    print(f"\n=== 참고쌍(정보제공형) === {r['study']} 인간 {r['human_pp']:+.1f} | "
          f"LLM {r['llm_pp']:+.2f} [{r['ci'][0]:+.1f},{r['ci'][1]:+.1f}]")

json.dump(res, io.open(OUT / "us_score.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n저장: us_score.json | 응답 행:", len(raw))
