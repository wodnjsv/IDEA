# -*- coding: utf-8 -*-
"""광명 뼈대 4,568명 vs KGSS 도너 풀(2018/21/23/25 합산): 셀 매칭 사다리별 도너 수 분포."""
import io
import json
import sys
from collections import Counter

import pandas as pd
import pyreadstat

sys.path.insert(0, r"C:\dev\idea\src")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from engine import harmonize as H  # noqa: E402

df, meta = pyreadstat.read_sav(r"C:\dev\idea\data\raw\kor_data_CUM0074_V2.sav",
                               usecols=["YEAR", "SEX", "AGE", "EDUC", "REGION", "MARITAL"])
k = df[df["YEAR"].isin([2018, 2021, 2023, 2025])].copy()
k = k[(k["SEX"] > 0) & (k["AGE"] > 0)]
reg_lab = meta.variable_value_labels.get("REGION", {})
cap_codes = {c for c, lab in reg_lab.items() if any(s in str(lab) for s in ("서울", "경기", "인천"))}
print(f"KGSS 4웨이브 성인 {len(k):,}명 | 수도권 코드 {sorted(cap_codes)} → {int(k['REGION'].isin(cap_codes).sum()):,}명")

def kgss_key(r, level):
    sex = "남" if int(r["SEX"]) == 1 else "여"
    age10 = f"{int(r['AGE']) // 10 * 10}대"
    try:
        edu = H.edu4_kgss(r["EDUC"])
    except Exception:
        edu = None
    cap = "수도권" if r["REGION"] in cap_codes else "비수도권"
    mar = "기혼" if r.get("MARITAL") == 1 else "비혼"
    return {1: (sex, age10, edu, cap, mar), 2: (sex, age10, edu, cap), 3: (sex, age10, edu), 4: (sex, age10)}[level]

pools = {lv: Counter(kgss_key(r, lv) for _, r in k.iterrows()) for lv in (1, 2, 3, 4)}

bank = [json.loads(l) for l in open(r"C:\dev\idea\data\banks\persona_bank_gwangmyeong_v1.jsonl", encoding="utf-8")]
def bank_key(p, level):
    s = p["skeleton"]
    age10 = f"{int(s['age']) // 10 * 10}대"
    mar = "기혼" if s["marital"] == "배우자 있음" else "비혼"
    return {1: (s["sex"], age10, s["edu4"], "수도권", mar), 2: (s["sex"], age10, s["edu4"], "수도권"),
            3: (s["sex"], age10, s["edu4"]), 4: (s["sex"], age10)}[level]

names = {1: "성×연령10×학력×수도권×혼인", 2: "성×연령10×학력×수도권", 3: "성×연령10×학력", 4: "성×연령10"}
print(f"\n광명 뼈대 {len(bank):,}명 — 매칭 사다리별 '같은 뼈대' KGSS 도너 수")
print(f"{'수준':32} {'중앙값':>6} {'<10명':>7} {'<30명':>7} {'0명':>6} {'셀수':>5} {'뼈대/도너':>9}")
for lv in (1, 2, 3, 4):
    cnts = [pools[lv].get(bank_key(p, lv), 0) for p in bank]
    s = pd.Series(cnts)
    cells = Counter(bank_key(p, lv) for p in bank)
    used = sum(pools[lv].get(c, 0) for c in cells)
    print(f"{names[lv]:32} {int(s.median()):6d} {(s<10).mean()*100:6.1f}% {(s<30).mean()*100:6.1f}% "
          f"{(s==0).mean()*100:5.1f}% {len(cells):5d} {len(bank)/max(used,1):9.2f}")
print("\n뼈대/도너 = 광명 인물 수 ÷ 그 셀들이 가진 도너 총수 (>1이면 도너 반복 불가피)")
