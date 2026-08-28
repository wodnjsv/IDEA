# -*- coding: utf-8 -*-
"""EXP-009 사전 체크 ⑥(개정 2 ⑥): KGSS A/B 분할표본 쌍의 의미 정렬 재계산 → 한국 위약 세트.

핵심 규율: B형이 척도 역순인 쌍은 (ncat+1-x) 재코딩 후 비교 — 미정렬 채점 시
−51.9%p급 가짜 효과(코딩 아티팩트)가 생긴다. 정렬 후 전 쌍 효과 ≈0 → 위약으로 등록.
개정 2 ⑥ 분류: 강한 위약 2(SAMPTHOU-무작위 2023, NUKPLT10 2018) / 약한 위약 5 /
NUKPLT10 2023은 경계(p=.09)라 양쪽 제외.
"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat
from scipy.stats import chi2_contingency

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.registry import resolve

df, meta = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
num = df.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)


def eff(a, b, y, reverse_b, ncat):
    sa = num.loc[df["YEAR"] == y, a].dropna()
    sb = num.loc[df["YEAR"] == y, b].dropna()
    if len(sa) < 100 or len(sb) < 100:
        return None
    if reverse_b:
        sb = ncat + 1 - sb
    cats = sorted(set(sa.unique()) | set(sb.unique()))
    diffs = {c: sa.eq(c).mean() - sb.eq(c).mean() for c in cats}
    fc, fd = max(diffs.items(), key=lambda kv: abs(kv[1]))
    tab = np.array([[sa.eq(c).sum() for c in cats], [sb.eq(c).sum() for c in cats]])
    p = chi2_contingency(tab[:, tab.sum(0) > 0]).pvalue
    return len(sa), len(sb), int(fc), fd * 100, p


print("== KGSS A/B 정렬 후 재계산 (반전형은 B형 척도 보정) ==")
jobs = [("NUKPLT10A", "NUKPLT10B", 2018, True, 3), ("NUKPLT10A", "NUKPLT10B", 2021, True, 3),
        ("NUKPLT10A", "NUKPLT10B", 2023, True, 3), ("ELEFRAUDA", "ELEFRAUDB", 2025, True, 3),
        ("LAWHARSHA", "LAWHARSHB", 2025, True, 5), ("PROUDDEM16A", "PROUDDEM16B", 2021, True, 4),
        ("PROUDECO16A", "PROUDECO16B", 2021, True, 4), ("PROUDSSS16A", "PROUDSSS16B", 2021, True, 4),
        ("SAMPTHOUA", "SAMPTHOUB23", 2023, False, 2), ("SAMPTHOUA", "SAMPTNTHB25", 2025, False, 2)]
for a, b, y, rev, nc in jobs:
    r = eff(a, b, y, rev, nc)
    kind = "순서(정렬후)" if rev else "워딩"
    if r:
        print(f"{a[:11]:12s} {y} {kind}: n={r[0]}/{r[1]} focal범주{r[2]} {r[3]:+.1f}%p p={r[4]:.4f}")
    else:
        print(f"{a[:11]:12s} {y}: 표본 부족/부재")
print("DONE")
