# -*- coding: utf-8 -*-
"""EXP-011 사전 체크 3·(뼈대 소스): 봉인 시도별 KGSS 정답지 크기 + 전국 뱅크 v1의 시도별 뼈대 수."""
import io
import json
import sys
from collections import Counter

import pyreadstat

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
df, meta = pyreadstat.read_sav(r"C:\dev\idea\data\raw\kor_data_CUM0074_V2.sav", usecols=["YEAR", "REGION", "AGE"])
lab = meta.variable_value_labels["REGION"]
print("REGION 코드:", {int(k): v for k, v in lab.items() if k >= 0})
k = df[df["YEAR"].isin([2018, 2021, 2023, 2025]) & (df["AGE"] > 0)]
tab = k.groupby(["REGION", "YEAR"]).size().unstack(fill_value=0)
tab["합계"] = tab.sum(axis=1)
tab.index = [lab.get(i, i) for i in tab.index]
print("\n[KGSS 시도×웨이브 성인 응답자 수]")
print(tab.to_string())

bank = [json.loads(l) for l in open(r"C:\dev\idea\data\banks\persona_bank_national_v1.jsonl", encoding="utf-8")]
c = Counter(p["skeleton"]["sido_name"] for p in bank)
print("\n[전국 뱅크 v1 시도별 뼈대 수]", dict(c))
