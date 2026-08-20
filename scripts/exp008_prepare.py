# -*- coding: utf-8 -*-
"""EXP-008 1단 사전 준비 ($0, LLM 0콜) — 사전등록 규격의 기계적 실행.

산출: data/exp008/{prep_meta.json, profiles.jsonl, battery_table.txt}
  1) 고정 배터리 10문항 선정 (2023 파동, 커버리지>=0.80, 유분산, 5영역x2, 결정론적)
  2) 프로필 제외 목록: y-인접(투표·정당·이념) + 인구속성 사실형 + 배터리 준중복(|r|>=0.85)
  3) 평가셋 300명(배터리 8+ 유효, seed=42) / 참조셋(나머지 전원 — 베이스라인 학습 전용)
  4) 4암 프로필 렌더링 (K0/K5/FULL/SHUF — SHUF는 같은 셀 비평가 도너의 답, 시드 고정)
"""
import io
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

from engine import harmonize as H  # noqa: E402
from engine.registry import resolve  # noqa: E402

OUT = ROOT / "data" / "exp008"
OUT.mkdir(parents=True, exist_ok=True)
SEED = 42
N_EVAL = 300

# ── 로드 ──
sav = str(resolve("kgss_cum_2003_2025"))
df, meta = pyreadstat.read_sav(sav)
labels = meta.column_names_to_labels
vlabels = meta.variable_value_labels
d23 = df[df["YEAR"] == 2023].reset_index(drop=True)
dref_other = df[df["YEAR"].isin([2021, 2025])]

num23 = d23.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)

# ── 제외 목록 ──
Y_PAT = ["투표", "정당", "대선", "대통령", "선거", "지지", "총선"]
y_adj = {n for n in df.columns
         if n in ("PARTYLR", "LEFTRIGT")
         or any(p in (labels.get(n) or "") for p in Y_PAT)
         or any(k in n.upper() for k in ["VOTE", "PRTY", "PARTY", "ELEC", "PRES"])}
ADMIN_PAT = ["ID", "WT", "WEIGHT", "MODE", "INTV", "DATE", "MONTH", "AREA", "SIZE", "YEAR"]
DEMO_VARS = {"SEX", "AGE", "EDUC", "MARITAL", "REGION", "INCOM", "RINCOM", "INCOME",
             "BIRTH", "HOMPOP", "TENURE", "DWELL"}
DEMO_LABEL = re.compile(r"몇 세|만 나이|성별|최종 학력|교육 수준|혼인 상태|태어|출생|가구원|거주")

def is_admin(n):
    return any(p in n.upper() for p in ADMIN_PAT)

def is_demo(n):
    return n in DEMO_VARS or any(n.upper().startswith(v) for v in DEMO_VARS) \
        or bool(DEMO_LABEL.search(labels.get(n) or ""))

# ── 영역 분류 (키워드 — 결정론적) ──
DOMAINS = {
    "정치경제": r"정부|정치|경제|세금|복지|지출|기업|노동조합|노조|소득\s*차이|소득격차|규제|통일|북한|국방|실업",
    "가족젠더": r"가족|자녀|어린이|결혼|이혼|남편|아내|여성|남성|성\s*역할|맞벌이|부모|어머니|아버지",
    "종교전통": r"종교|신앙|기도|예배|하나님|신의|제사|전통|조상",
    "신뢰사회": r"신뢰|사람들.*믿|공정|도움|이기적|기관.*신뢰|지도층",
    "문화생활": r"여가|문화|행복|만족|건강|생활|음악|TV|텔레비전|운동|친구",
}

def domain_of(n):
    lab = labels.get(n) or ""
    for dom, pat in DOMAINS.items():
        if re.search(pat, lab):
            return dom
    return None

# ── (1) 배터리 후보: 2023 커버리지>=0.80·서열형(값 2~7종, 1..10)·유분산·비제외 ──
cand = []
for c in d23.columns:
    if is_admin(c) or is_demo(c) or c in y_adj:
        continue
    s = num23[c].dropna()
    if len(s) / len(d23) < 0.80:
        continue
    vals = sorted(s.unique())
    if not (2 <= len(vals) <= 7 and min(vals) >= 1 and max(vals) <= 10):
        continue
    if s.std() < 0.60:
        continue
    dom = domain_of(c)
    if dom is None:
        continue
    cand.append((dom, c, round(len(s) / len(d23), 3), round(float(s.std()), 3)))

cand_df = pd.DataFrame(cand, columns=["dom", "var", "cov", "std"])
battery = []
for dom in DOMAINS:
    sub = cand_df[cand_df["dom"] == dom].sort_values(["cov", "std", "var"], ascending=[False, False, True])
    battery += sub.head(2)["var"].tolist()
assert len(battery) == 10, f"배터리 선정 실패: {len(battery)}개 (영역별 후보 부족)"

# ── (2) 준중복: 배터리와 |r|>=0.85 (2023, 커버리지>=0.30 문항 대상) ──
wide = {c for c in d23.columns if not is_admin(c) and num23[c].notna().mean() >= 0.30}
near_dup = set()
for b in battery:
    for c in wide:
        if c == b or c in battery:
            continue
        r = num23[b].corr(num23[c])
        if pd.notna(r) and abs(r) >= 0.85:
            near_dup.add(c)

PROFILE_EXCLUDE = y_adj | set(battery) | near_dup

# ── (3) 평가셋/참조셋 분리 ──
valid_bat = num23[battery].notna().sum(axis=1)
eligible = d23.index[valid_bat >= 8].tolist()
rng = random.Random(SEED)
eval_idx = sorted(rng.sample(eligible, N_EVAL))
eval_set = set(eval_idx)
ref23_idx = [i for i in range(len(d23)) if i not in eval_set]

# ── 셀 정의 + 렌더링 유틸 ──
def cell_of(row):
    try:
        return (int(row["SEX"]), H.age_band(int(row["AGE"])), int(row["REGION"]),
                H.edu4_kgss(row["EDUC"]))
    except Exception:
        return None

def vlabel(var, v):
    m = vlabels.get(var)
    if m and v in m:
        return str(m[v]).strip()
    if m and float(v) in m:
        return str(m[float(v)]).strip()
    return str(int(v))

def render_item(var, v):
    lab = vlabel(var, v)
    m = vlabels.get(var) or {}
    if lab == str(int(v)) and m:  # 라벨 없는 중간 척도점 → 양끝 앵커 부기 (척도 방향 제공)
        ks = sorted(k for k in m if isinstance(k, (int, float)) and k >= 0)
        if ks:
            return (f"- {labels.get(var, var)}: {int(v)} "
                    f"({int(ks[0])}={str(m[ks[0]]).strip()} ~ {int(ks[-1])}={str(m[ks[-1]]).strip()})")
    return f"- {labels.get(var, var)}: {lab}"

def demo_text(row):
    sex = "남성" if int(row["SEX"]) == 1 else "여성"
    parts = [f"{int(row['AGE'])}세 {sex}"]
    for var, name in [("REGION", "거주지역"), ("EDUC", "학력"), ("MARITAL", "혼인상태")]:
        if var in row and pd.notna(row[var]) and row[var] >= 0:
            parts.append(f"{name}: {vlabel(var, row[var])}")
    return ", ".join(parts)

# 프로필 대상 문항: 2023에 존재(cov>=0.30)·비관리·비인구·비제외
profile_pool = [c for c in wide if not is_demo(c) and c not in PROFILE_EXCLUDE]

# ── (4) 프로필 4암 생성 ──
# SHUF 도너: 같은 셀의 2023 비평가 응답자 (유효응답 >=50), 없으면 폴백 사다리
ref_cells = {}
for i in ref23_idx:
    cell = cell_of(d23.loc[i])
    if cell and num23.loc[i, profile_pool].notna().sum() >= 50:
        ref_cells.setdefault(cell, []).append(i)

def find_donor(cell, prng):
    ladders = [cell, cell[:3], cell[:2], None]
    for lv, key in enumerate(ladders):
        pool = (ref_cells.get(key) if key is not None
                else [i for v in ref_cells.values() for i in v])
        if key is not None and len(cell) == 4 and lv > 0:
            pool = [i for c, v in ref_cells.items() if c[:len(key)] == key for i in v]
        if pool:
            return prng.choice(pool), f"L{lv+1}"
    return None, "NONE"

profiles = []
fallback_use = {}
for i in eval_idx:
    row = d23.loc[i]
    pid = f"e23_{i}"
    prng = random.Random(f"{SEED}-{pid}")
    valid_items = [c for c in profile_pool if pd.notna(num23.loc[i, c])]
    prng.shuffle(valid_items)  # 순서 무작위 (전 암 공통 순서 — FULL/K5 중첩 보장)
    # K5: 영역별 1개 (셔플된 순서에서 앞선 것 — 결정론적), 부족 시 기타로 보충
    k5, seen_dom = [], set()
    for c in valid_items:
        dm = domain_of(c)
        if dm and dm not in seen_dom:
            k5.append(c)
            seen_dom.add(dm)
        if len(k5) == 5:
            break
    for c in valid_items:
        if len(k5) >= 5:
            break
        if c not in k5:
            k5.append(c)
    cell = cell_of(row)
    donor_i, flv = find_donor(cell, prng) if cell else (None, "NONE")
    fallback_use[flv] = fallback_use.get(flv, 0) + 1
    drow = num23.loc[donor_i] if donor_i is not None else None
    shuf_lines = []
    if drow is not None:
        for c in valid_items:  # 같은 문항 슬롯·같은 순서, 답만 도너 것 (없으면 그 문항 생략)
            if pd.notna(drow[c]):
                shuf_lines.append(render_item(c, drow[c]))
    profiles.append({
        "pid": pid, "cell": list(cell) if cell else None, "donor": (f"e23_{donor_i}" if donor_i is not None else None),
        "donor_fallback": flv,
        "demo": demo_text(row),
        "arms": {
            "K0": [],
            "K5": [render_item(c, num23.loc[i, c]) for c in [v for v in valid_items if v in k5]],
            "FULL": [render_item(c, num23.loc[i, c]) for c in valid_items],
            "SHUF": shuf_lines,
        },
        "n_full": len(valid_items),
        "battery": [{
            "var": b, "q": labels.get(b, b),
            # 척도 절단 방지: 관측값 ∪ 값라벨 정의역(1..10) — 미관측 척도점도 선택지에 제시
            "options": [{"v": v, "label": vlabel(b, v)} for v in sorted(
                {int(x) for x in num23[b].dropna().unique()} |
                {int(float(k)) for k in (vlabels.get(b) or {}) if 1 <= float(k) <= 10})],
            "actual": (int(num23.loc[i, b]) if pd.notna(num23.loc[i, b]) else None),
        } for b in battery],
    })

with io.open(OUT / "profiles.jsonl", "w", encoding="utf-8") as f:
    for p in profiles:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")

# 참조셋 행렬 (베이스라인용): 2023 비평가 + 2021/2025 전원, battery+profile_pool 값
ref_rows = []
for i in ref23_idx:
    ref_rows.append({"src": f"e23_{i}", **{c: (float(num23.loc[i, c]) if pd.notna(num23.loc[i, c]) else None)
                                           for c in profile_pool + battery},
                     "SEX": float(d23.loc[i, "SEX"]), "AGE": float(d23.loc[i, "AGE"])})
numo = dref_other.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)
for j, (_, r) in enumerate(dref_other.iterrows()):
    ref_rows.append({"src": f"o_{j}", **{c: (float(numo.iloc[j][c]) if c in numo.columns and pd.notna(numo.iloc[j][c]) else None)
                                         for c in profile_pool + battery},
                     "SEX": (float(r["SEX"]) if pd.notna(r["SEX"]) else None),
                     "AGE": (float(r["AGE"]) if pd.notna(r["AGE"]) else None)})
pd.DataFrame(ref_rows).to_parquet(OUT / "reference.parquet", index=False)

meta_out = {
    "seed": SEED, "n_eval": N_EVAL, "wave": 2023,
    "battery": battery, "near_dup_excluded": sorted(near_dup),
    "y_adjacent_n": len(y_adj), "profile_pool_n": len(profile_pool),
    "eligible_n": len(eligible), "ref23_n": len(ref23_idx), "ref_other_n": len(dref_other),
    "shuf_fallback": fallback_use,
}
json.dump(meta_out, io.open(OUT / "prep_meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

with io.open(OUT / "battery_table.txt", "w", encoding="utf-8") as f:
    f.write("영역 | 변수 | 커버리지 | std | 라벨 | 선택지\n")
    for dom in DOMAINS:
        for b in battery:
            if domain_of(b) == dom:
                opts = " / ".join(f"{int(v)}={vlabel(b, v)}" for v in sorted(num23[b].dropna().unique()))
                f.write(f"{dom} | {b} | {num23[b].notna().mean():.2f} | {num23[b].std():.2f} | {labels.get(b)} | {opts}\n")

print("PREP OK")
print(f"battery={battery}")
print(f"near_dup={len(near_dup)} profile_pool={len(profile_pool)} eligible={len(eligible)}")
print(f"fallback={fallback_use}")
print(f"n_full 분포: min={min(p['n_full'] for p in profiles)} med={sorted(p['n_full'] for p in profiles)[150]} max={max(p['n_full'] for p in profiles)}")
