# -*- coding: utf-8 -*-
"""EXP-010 미국장 채점 (dist 채널) — EXP-009 게이트 동일 적용, 채널 간 직접 비교.

개인 분포에서 focal 확률을 읽어 paired Δ(%p) 산출 (align_rule 쌍은 B 분포 키 재매핑).
G4 방향 ≥13/17 · 위약 오탐 ≤3/20 + 분리도 · LOSO. EXP-009 강제선택 결과 병기.
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import argparse

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
D9 = ROOT / "data" / "exp009"
D10 = ROOT / "data" / "exp010"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rng = np.random.default_rng(20260828)
B = 4000

ap = argparse.ArgumentParser()
ap.add_argument("--raw", default="us_dist_raw.jsonl", help="dist 스키마 입력(us_ssr_scored.jsonl 가능)")
ap.add_argument("--out", default=None)
args = ap.parse_args()
OUT_NAME = args.out or args.raw.replace("_raw", "").replace(".jsonl", "_score.json") \
    .replace("_scored", "_score.json").replace(".json.json", ".json")

pairs = {p["study"]: p for p in
         (json.loads(l) for l in open(D9 / "us_pairs_runtime.jsonl", encoding="utf-8"))}
prev = json.load(open(D9 / "us_score.json", encoding="utf-8"))
prev_by = {r["study"]: r for role in prev for r in prev[role]}

data = defaultdict(lambda: defaultdict(dict))
for l in open(D10 / args.raw, encoding="utf-8"):
    r = json.loads(l)
    if r.get("dist") is None:
        continue
    data[r["grp"]][r["pid"]][r["form"]] = {int(k): v for k, v in r["dist"].items()}


def pair_delta(study):
    pr = pairs[study]
    fc, lo_v, hi_v = pr["focal_cat"], pr["valid_lo"], pr["valid_hi"]
    rev = bool(pr["align_rule"])
    diffs = []
    for d in data.get(study, {}).values():
        if "A" not in d or "B" not in d:
            continue
        a = d["A"].get(fc, 0.0)
        bd = {(lo_v + hi_v) - k: v for k, v in d["B"].items()} if rev else d["B"]
        diffs.append(a - bd.get(fc, 0.0))
    if len(diffs) < 20:
        return None
    diffs = np.array(diffs)
    idx = rng.integers(0, len(diffs), (B, len(diffs)))
    bs = diffs[idx].mean(axis=1) * 100
    return (diffs.mean() * 100, float(np.percentile(bs, 2.5)),
            float(np.percentile(bs, 97.5)), len(diffs))


res = {"real": [], "null": [], "ref": []}
for study, pr in pairs.items():
    out = pair_delta(study)
    if out is None:
        print(f"  (미완) {study}")
        continue
    d, lo, hi, n = out
    res[pr["role"]].append({
        "study": study, "subtype": pr["subtype"], "human_pp": pr["human_pp"],
        "llm_pp": round(d, 2), "ci": [round(lo, 2), round(hi, 2)], "n": n,
        "dir_match": bool(np.sign(d) == np.sign(pr["human_pp"]) and d != 0),
        "sig": bool(lo > 0 or hi < 0),
        "forced_pp": prev_by.get(study, {}).get("llm_pp")})

print("=== dist 채널: 민감도 (실측 17쌍) — [강제선택 EXP-009 병기] ===")
hits = sum(r["dir_match"] for r in res["real"])
for r in sorted(res["real"], key=lambda x: -abs(x["human_pp"])):
    m = "O" if r["dir_match"] else "X"
    print(f"  {m} {r['study']:7} {r['subtype']:14} 인간 {r['human_pp']:+6.1f} | "
          f"dist {r['llm_pp']:+7.2f} [{r['ci'][0]:+.1f},{r['ci'][1]:+.1f}] | 강제 {r['forced_pp']:+7.2f}")
n_real = len(res["real"])
if n_real:
    p = binomtest(hits, n_real, 0.5, alternative="greater").pvalue
    print(f"방향 {hits}/{n_real} (p={p:.4f}) → G4(≥13/17): "
          f"{'합격' if hits >= 13 and n_real == 17 else '불합격' if n_real == 17 else '미완'} "
          f"[강제선택: 12/17 p=.072 불합격]")

print("\n=== dist 채널: 특이도 (위약 20쌍) ===")
fps = sum(r["sig"] for r in res["null"])
for r in res["null"]:
    m = "!" if r["sig"] else " "
    print(f"  {m} {r['study']:7} {r['subtype']:16} dist {r['llm_pp']:+7.2f} "
          f"[{r['ci'][0]:+.1f},{r['ci'][1]:+.1f}] | 강제 {r['forced_pp']:+7.2f}")
if res["null"] and res["real"]:
    med_n = float(np.median([abs(r["llm_pp"]) for r in res["null"]]))
    med_r = float(np.median([abs(r["llm_pp"]) for r in res["real"]]))
    print(f"오탐 {fps}/{len(res['null'])} (게이트 ≤3: {'합격' if fps <= 3 else '불합격'}) "
          f"[강제선택 12/20] | |Δ| 중앙값 위약 {med_n:.2f} vs 실측 {med_r:.2f} "
          f"(≤1/3: {'합격' if med_n <= med_r / 3 else '불합격'}) [강제선택 5.97/7.50]")

if len(res["real"]) >= 10:
    X = np.array([r["llm_pp"] for r in res["real"]])
    Y = np.array([r["human_pp"] for r in res["real"]])
    preds = []
    for i in range(len(X)):
        msk = np.ones(len(X), bool)
        msk[i] = False
        b_, a_ = np.polyfit(X[msk], Y[msk], 1)
        preds.append(a_ + b_ * X[i])
    print(f"\n=== 크기 (LOSO) === r={np.corrcoef(preds, Y)[0, 1]:.3f} "
          f"(전체 b={np.polyfit(X, Y, 1)[0]:.2f}) [강제선택 r=.679 b=.90]")

if res["ref"]:
    r = res["ref"][0]
    print(f"\n=== 참고쌍 === {r['study']} 인간 {r['human_pp']:+.1f} | dist {r['llm_pp']:+.2f} "
          f"| 강제 {r['forced_pp']:+.2f}")

json.dump(res, io.open(D10 / OUT_NAME, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"\n저장: {OUT_NAME}")
