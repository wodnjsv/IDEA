# -*- coding: utf-8 -*-
"""EXP-010 부속 4: 수준(level) 재현율 — 인텔리시아식 지표(실제 vs 모델 선택지 분포 스피어만 상관)로 산출.

한국장: 앵커 A/B(웹실험 실측) + SAMPTHOU23 A/B + NUKPLT18 A/B(KGSS 실측) — 채널 3종 × 암.
미국장: 37쌍 × 2조건(실측 = 코퍼스 응답 분포) — 강제선택(EXP-009) vs 분포발화(EXP-010).
지표: 풀링 스피어만(모든 (문항,선택지) 점유율 쌍) · 문항별 스피어만 평균(선택지 ≥3) · MAE(%p) · 1−TVD 평균.
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import resolve  # noqa: E402

D9, D10 = ROOT / "data" / "exp009", ROOT / "data" / "exp010"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def metrics(pairs_hm):
    """pairs_hm: list of (human_dict, model_dict) over shared keys."""
    H, M, tvds, per_item = [], [], [], []
    for h, m in pairs_hm:
        ks = sorted(set(h) | set(m))
        hv = np.array([h.get(k, 0) for k in ks])
        mv = np.array([m.get(k, 0) for k in ks])
        H += list(hv)
        M += list(mv)
        tvds.append(0.5 * np.abs(hv - mv).sum())
        if len(ks) >= 3 and hv.std() > 0 and mv.std() > 0:
            per_item.append(spearmanr(hv, mv).correlation)
    rho = spearmanr(H, M).correlation
    return dict(n_items=len(pairs_hm), pooled_rho=round(float(rho), 3),
                item_rho=round(float(np.mean(per_item)), 3) if per_item else None,
                mae_pp=round(float(np.mean(np.abs(np.array(H) - np.array(M)))) * 100, 2),
                match=round(float(1 - np.mean(tvds)), 3))


# ── 한국장 ──
kr = json.load(open(D10 / "kr_score.json", encoding="utf-8"))
HUMAN_KR = {("ANCHOR", "A"): {1: .38, 2: .45, 9: .17}, ("ANCHOR", "B"): {1: .31, 2: .51, 9: .18},
            ("SAMPTHOU23", "A"): {1: .326, 2: .674}, ("SAMPTHOU23", "B"): {1: .330, 2: .670},
            ("NUKPLT18", "A"): {1: .192, 2: .498, 3: .310}, ("NUKPLT18", "B"): {1: .291, 2: .517, 3: .192}}
lev = {}
try:
    lev = json.load(open(D10 / "kr_leveled.json", encoding="utf-8"))
except Exception:
    pass
print("=== 한국장 수준 재현 (앵커 2판 + KGSS 실측 4판, 인구암) ===")
# 앵커는 kr_score.json의 distA/distB, 위약은 exp010_kr_leveled 출력값 재사용(하드코딩 — 해당 스크립트 출력 기준)
LEVELED = {  # from exp010_kr_leveled.py output (DEMO arm)
    "forced": {("SAMPTHOU23", "A"): {1: 0, 2: 1}, ("SAMPTHOU23", "B"): {1: 0, 2: 1},
               ("NUKPLT18", "A"): {1: .108, 2: .563, 3: .329}, ("NUKPLT18", "B"): {1: .597, 2: .366, 3: .038}},
    "dist": {("SAMPTHOU23", "A"): {1: .285, 2: .715}, ("SAMPTHOU23", "B"): {1: .288, 2: .712},
             ("NUKPLT18", "A"): {1: .272, 2: .456, 3: .273}, ("NUKPLT18", "B"): {1: .430, 2: .359, 3: .211}},
    "ssr": {("SAMPTHOU23", "A"): {1: .490, 2: .510}, ("SAMPTHOU23", "B"): {1: .494, 2: .506}},
}
for ch in ("forced", "dist", "ssr"):
    a = kr[ch]["DEMO"]
    pairs = [(HUMAN_KR[("ANCHOR", "A")], {int(k): v for k, v in a["distA"].items()}),
             (HUMAN_KR[("ANCHOR", "B")], {int(k): v for k, v in a["distB"].items()})]
    pairs += [(HUMAN_KR[k], v) for k, v in LEVELED[ch].items()]
    print(f"  {ch:7} {metrics(pairs)}")

# ── 미국장 ──
pairs_rt = {p["study"]: p for p in (json.loads(l) for l in open(D9 / "us_pairs_runtime.jsonl", encoding="utf-8"))}
SRC = resolve("socsci210")
cols = ["study_id", "task_num", "condition_num", "response"]
df = pd.concat([pd.read_parquet(p, columns=cols) for p in sorted(SRC.rglob("*.parquet"))], ignore_index=True)
df = df[df.study_id.isin(pairs_rt)]

def human_dist(study, cond):
    pr = pairs_rt[study]
    c = pr["condA"] if cond == "A" else pr["condB"]
    s = df[(df.study_id == study) & (df.task_num == pr["task"]) & (df.condition_num == c)]["response"].dropna()
    s = s[(s >= pr["valid_lo"]) & (s <= pr["valid_hi"])]
    return {int(k): float(v) for k, v in (s.value_counts(normalize=True)).items()}

# 모델: 분포발화(개인 분포 평균) / 강제선택(k3 응답 점유율)
md = defaultdict(list)
for l in open(D10 / "us_dist_raw.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r.get("dist"):
        md[(r["grp"], r["form"])].append({int(k): v for k, v in r["dist"].items()})
mf = defaultdict(list)
for l in open(D9 / "us_raw.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r.get("pred") is not None and r.get("profile"):
        mf[(r["study"], r["cond"])].append(r["pred"])

def avg(dlist):
    ks = set().union(*dlist)
    return {k: float(np.mean([d.get(k, 0) for d in dlist])) for k in ks}

print("\n=== 미국장 수준 재현 (37쌍 × 2조건 = 74판, 프로필암) ===")
P_dist, P_forced = [], []
for study in pairs_rt:
    for cond in ("A", "B"):
        h = human_dist(study, cond)
        if md.get((study, cond)):
            P_dist.append((h, avg(md[(study, cond)])))
        if mf.get((study, cond)):
            v = pd.Series(mf[(study, cond)]).value_counts(normalize=True)
            P_forced.append((h, {int(k): float(x) for k, x in v.items()}))
print(f"  forced  {metrics(P_forced)}")
print(f"  dist    {metrics(P_dist)}")
print("\n지표: pooled_rho=전 (판,선택지) 점유율 스피어만 | item_rho=판별 스피어만 평균(선택지≥3) | mae_pp=선택지 점유율 절대오차 | match=1−TVD")
