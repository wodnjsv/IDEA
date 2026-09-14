# -*- coding: utf-8 -*-
"""EXP-011 사전 체크 8: KGSS 문항 정규화 섀넌 엔트로피 순위 (Kinzinger 2026 — 변별력 기준 문항 선별).
2023 웨이브, 프로필 풀(제외 200변수·관리·인구 제외) 대상. 산출: data/kgss_item_entropy.csv"""
import io
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import data_dir, resolve  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
df, meta = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
labels = meta.column_names_to_labels
d = df[df["YEAR"] == 2023]
num = d.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)
excl = set(pd.read_csv(data_dir() / "exp009_kr_profile_exclude.csv")["var"])
ADMIN = ["ID", "WT", "WEIGHT", "MODE", "INTV", "DATE", "MONTH", "AREA", "SIZE", "YEAR"]
DEMO = re.compile(r"몇 세|만 나이|성별|최종 학력|교육 수준|혼인 상태|태어|출생|가구원|거주|설문지 유형|가구번호|면접|응답자 번호|국적")
rows = []
for c in num.columns:
    if c in excl or any(p in c.upper() for p in ADMIN) or DEMO.search(labels.get(c) or ""):
        continue
    s = num[c].dropna()
    if len(s) / len(d) < 0.3 or s.nunique() < 2 or s.nunique() > 12:
        continue
    p = s.value_counts(normalize=True).values
    h = -(p * np.log2(p)).sum() / np.log2(s.nunique())
    rows.append({"var": c, "label": (labels.get(c) or "")[:50], "n_cat": s.nunique(),
                 "coverage": round(len(s) / len(d), 2), "H_norm": round(float(h), 3)})
E = pd.DataFrame(rows).sort_values("H_norm", ascending=False)
E.to_csv(data_dir() / "kgss_item_entropy.csv", index=False, encoding="utf-8-sig")
q = E.H_norm.quantile([.25, .5, .75])
print(f"프로필 풀 {len(E)}문항 | H_norm 분위 25/50/75 = {q[.25]:.2f}/{q[.5]:.2f}/{q[.75]:.2f}")
print("상위 10:"); print(E.head(10).to_string(index=False))
print("하위 5:"); print(E.tail(5).to_string(index=False))
