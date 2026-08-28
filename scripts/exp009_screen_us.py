# -*- coding: utf-8 -*-
"""EXP-009 사전 체크 ①: 미국 코퍼스(SocSci210)에서 실측효과/무효과 쌍 스크리닝.

기준(개정 2 동결): 조건별 n>=150, 자극 유사도>=0.5, 스터디당 1쌍, 응답 2~9범주.
  실측효과 후보: |focal|>=5%p AND p<1e-3
  강한 위약 후보: |focal|<=2%p AND p>0.5 AND 조건별 n>=400 (실측 배정 스터디 제외)
산출: data/exp009_us_{real,null}_candidates.csv (자극 발췌 포함)
후속: 후보 전수 수동 심사(자극 diff·원문·응답분포 대조 — 개정 2 ① 기준) 후
      exp009_freeze_pairs.py 가 최종 동결표를 생성. 순서/방향 반전 쌍은 정렬 재계산 필수.
"""
import io
import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.registry import data_dir, resolve

SRC = resolve("socsci210")
OUT = data_dir()

shards = sorted(SRC.rglob("*.parquet"))
print(f"parquet {len(shards)}개 로드 중...")
cols = ["study_id", "task_num", "condition_num", "response", "stimuli", "participant"]
df = pd.concat([pd.read_parquet(p, columns=cols) for p in shards], ignore_index=True)
print(f"총 {len(df):,}행, 스터디 {df['study_id'].nunique()}개")

rows = []
for (sid, task), g in df.groupby(["study_id", "task_num"]):
    conds = g.groupby("condition_num")
    sizes = conds.size()
    big = sizes[sizes >= 150].index.tolist()
    if len(big) < 2:
        continue
    vals = g["response"].dropna()
    cats = sorted(v for v in vals.unique() if 0 <= v <= 20)
    if not (2 <= len(cats) <= 9):
        continue
    stim = {c: str(conds.get_group(c)["stimuli"].iloc[0]) for c in big}
    for i, ca in enumerate(big):
        for cb in big[i + 1:]:
            sa = conds.get_group(ca)["response"].dropna()
            sb = conds.get_group(cb)["response"].dropna()
            sim = SequenceMatcher(None, stim[ca][:1500], stim[cb][:1500]).ratio()
            if sim < 0.5:
                continue
            diffs = {c: sa.eq(c).mean() - sb.eq(c).mean() for c in cats}
            fc, fd = max(diffs.items(), key=lambda kv: abs(kv[1]))
            tab = np.array([[sa.eq(c).sum() for c in cats], [sb.eq(c).sum() for c in cats]])
            tab = tab[:, tab.sum(0) > 0]
            if tab.shape[1] < 2 or (tab.sum(1) == 0).any():
                continue
            try:
                p = chi2_contingency(tab).pvalue
            except ValueError:
                continue
            rows.append({"study": sid, "task": task, "condA": ca, "condB": cb,
                         "nA": len(sa), "nB": len(sb), "ncat": len(cats), "sim": round(sim, 3),
                         "focal_cat": fc, "focal_pp": round(fd * 100, 2), "p": p,
                         "stimA": stim[ca][:220].replace("\n", " "),
                         "stimB": stim[cb][:220].replace("\n", " ")})

R = pd.DataFrame(rows)
print(f"유사도>=0.5 후보 쌍: {len(R)}개 (스터디 {R['study'].nunique()}개)")
real = R[(R["focal_pp"].abs() >= 5) & (R["p"] < 1e-3)].copy()
null = R[(R["focal_pp"].abs() <= 2) & (R["p"] > 0.5) & (R[["nA", "nB"]].min(axis=1) >= 400)].copy()
real = real.reindex(real["focal_pp"].abs().sort_values(ascending=False).index).drop_duplicates("study")
used = set(real["study"].head(30))
null = null[~null["study"].isin(used)]
null = null.reindex(null[["nA", "nB"]].min(axis=1).sort_values(ascending=False).index).drop_duplicates("study")
print(f"실측효과 후보(스터디당 1): {len(real)}개 | 강한 위약 후보: {len(null)}개")
real.head(88).to_csv(OUT / "exp009_us_real_candidates.csv", index=False, encoding="utf-8-sig")
null.head(60).to_csv(OUT / "exp009_us_null_candidates.csv", index=False, encoding="utf-8-sig")
print("DONE")
