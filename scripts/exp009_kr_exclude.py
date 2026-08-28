# -*- coding: utf-8 -*-
"""EXP-009 사전 체크 ③(개정 2 ⑦): 한국장 프로필 준중복 제외 목록 생성.

제외 사유: (a) 위약 쌍 문항 자체(KGSS A/B 분할표본 폼 전부 — 프로필에 들어가면 답 누설),
(b) 앵커(대선 후보 지지)와 준중복 — 정당지지·이념·투표·대통령·선거 계열.
산출: data/exp009_kr_profile_exclude.csv (러너 prep이 프로필 풀에서 차감)
"""
import io
import re
import sys
from pathlib import Path

import pandas as pd
import pyreadstat

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.registry import data_dir, resolve

_, meta = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")), metadataonly=True)
labels = meta.column_names_to_labels

placebo_stems = ["NUKPLT10", "ELEFRAUD", "LAWHARSH", "PROUD", "SAMPTHOU", "SAMPHUND", "SAMPTNTH"]
anchor_kw = re.compile(r"정당|지지|이념|진보.*보수|보수.*진보|투표|대통령|대선|선거|후보", re.I)

rows = []
for var, lab in labels.items():
    lab = lab or ""
    v_up = var.upper()
    if any(v_up.startswith(s) for s in placebo_stems):
        rows.append({"var": var, "label": lab[:80], "reason": "위약쌍 문항(A/B폼)"})
    elif anchor_kw.search(lab):
        rows.append({"var": var, "label": lab[:80], "reason": "앵커 준중복(정치성향/투표)"})

E = pd.DataFrame(rows).drop_duplicates("var")
E.to_csv(data_dir() / "exp009_kr_profile_exclude.csv", index=False, encoding="utf-8-sig")
print(f"제외 변수 {len(E)}개 (위약 {sum(E.reason.str.startswith('위약'))}, "
      f"준중복 {sum(E.reason.str.startswith('앵커'))})")
print("DONE")
