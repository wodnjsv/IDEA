"""조건부 조회표 3종 + 계단식 폴백.

- W: P(월평균급여 구간 | 지역, 연령대, 성, 학력4)   ← 지역별고용조사 A형 (임금근로자, 만원)
- I: P(가구소득 10분위 | 수도권, 연령10, 학력3, 점유형태4)  ← 가계금융복지조사 가구마스터
- K: P(정치성향 PARTYLR+DK | 권역7, 성, 연령대, 학력4)      ← KGSS 최근 3파동

원칙: 추첨은 분포에서(최빈값 금지). 셀 n < MIN_CELL 이면 다음 레벨로 폴백(레벨 기록).
"""
import numpy as np
import pandas as pd

MIN_CELL = 30       # 급여·소득 (제안값, EXP-002)
MIN_CELL_KGSS = 5   # T2 명세

WAGE_BANDS = [(0, 100, "월 100만원 미만"), (100, 200, "월 100만원대"), (200, 300, "월 200만원대"),
              (300, 400, "월 300만원대"), (400, 500, "월 400만원대"), (500, 700, "월 500~600만원대"),
              (700, 10**9, "월 700만원 이상")]


def wage_band(w: float) -> str:
    for lo, hi, lab in WAGE_BANDS:
        if lo <= w < hi:
            return lab
    return WAGE_BANDS[-1][2]


class CascadeTable:
    """levels: [(이름, 키함수)] 상위→하위. draw() 시 첫 번째로 n 충족하는 레벨 사용."""

    def __init__(self, levels, min_cell):
        self.levels = levels
        self.min_cell = min_cell
        self.tables = [{} for _ in levels]

    def fit(self, rows, value_of, weight_of):
        for i, (_, keyfn) in enumerate(self.levels):
            agg = {}
            for r in rows:
                k, v, w = keyfn(r), value_of(r), weight_of(r)
                if k is None or v is None:
                    continue
                agg.setdefault(k, {}).setdefault(v, [0.0, 0])
                agg[k][v][0] += w
                agg[k][v][1] += 1
            for k, dist in agg.items():
                tot_w = sum(w for w, _ in dist.values())
                tot_n = sum(n for _, n in dist.values())
                self.tables[i][k] = {
                    "cats": list(dist.keys()),
                    "probs": [w / tot_w for w, _ in dist.values()],
                    "n": tot_n,
                }
        return self

    def draw(self, persona, rng):
        for i, (lname, keyfn) in enumerate(self.levels):
            k = keyfn(persona)
            cell = self.tables[i].get(k)
            if cell and cell["n"] >= self.min_cell:
                v = rng.choice(cell["cats"], p=np.array(cell["probs"]) / sum(cell["probs"]))
                return v, lname, cell["n"]
        return None, "none", 0


def build_wage_table(laf: pd.DataFrame, from_h=None):
    """지역별고용: 급여 비결측(임금근로자) 대상. 키 우선순위: 시군구→시도→전국."""
    from .harmonize import age_band, edu4_laf
    rows = []
    for _, r in laf.iterrows():
        if not r["wage"] or float(r["wage"]) <= 0:
            continue
        rows.append({
            "sgg": str(r["sgg4"]), "sido": str(r["sgg4"])[:2],
            "age_g": age_band(int(r["age"])), "sex": str(int(float(r["sex"]))),
            "edu4": edu4_laf(r["edu"]) if r["edu"] != "" else None,
            "band": wage_band(float(r["wage"])), "w": float(r["wt"]),
        })
    levels = [
        ("L1_시군구·연령·성", lambda p: (p.get("laf_sgg"), p["age_g"], p["sex"]) if p.get("laf_sgg") else None),
        ("L2_시도·연령·성·학력", lambda p: (p["sido"], p["age_g"], p["sex"], p["edu4"])),
        ("L3_시도·연령·성", lambda p: (p["sido"], p["age_g"], p["sex"])),
        ("L4_전국·연령·성", lambda p: (p["age_g"], p["sex"])),
    ]
    fit_levels = [
        ("L1_시군구·연령·성", lambda r: (r["sgg"], r["age_g"], r["sex"])),
        ("L2_시도·연령·성·학력", lambda r: (r["sido"], r["age_g"], r["sex"], r["edu4"]) if r["edu4"] else None),
        ("L3_시도·연령·성", lambda r: (r["sido"], r["age_g"], r["sex"])),
        ("L4_전국·연령·성", lambda r: (r["age_g"], r["sex"])),
    ]
    t = CascadeTable(fit_levels, MIN_CELL).fit(rows, lambda r: r["band"], lambda r: r["w"])
    t.levels = levels  # draw 시 페르소나 키 함수로 교체
    return t


def build_income_table(sflc: pd.DataFrame):
    """가금복: 소득10분위. 키: 수도권·연령10·학력3·점유4 → 수도권·연령10 → 전국·연령10 → 전국."""
    from .harmonize import SFLC_EDU_TO_EDU3
    rows = []
    for _, r in sflc.iterrows():
        if not r["d10"]:
            continue
        rows.append({"cap": r["cap"], "age10": r["age10"], "edu3": SFLC_EDU_TO_EDU3.get(r["edu"], None),
                     "ten": r["ten"], "d10": r["d10"], "w": float(r["wt"])})
    fit_levels = [
        ("L1_수도권·연령·학력·점유", lambda r: (r["cap"], r["age10"], r["edu3"], r["ten"]) if r["edu3"] else None),
        ("L2_수도권·연령·점유", lambda r: (r["cap"], r["age10"], r["ten"])),
        ("L3_수도권·연령", lambda r: (r["cap"], r["age10"])),
        ("L4_전국", lambda r: "ALL"),
    ]
    t = CascadeTable(fit_levels, MIN_CELL).fit(rows, lambda r: r["d10"], lambda r: r["w"])
    t.levels = [
        ("L1_수도권·연령·학력·점유", lambda p: (p["cap"], p["age10"], p["edu3"], p["ten4_g"])),
        ("L2_수도권·연령·점유", lambda p: (p["cap"], p["age10"], p["ten4_g"])),
        ("L3_수도권·연령", lambda p: (p["cap"], p["age10"])),
        ("L4_전국", lambda p: "ALL"),
    ]
    return t


def build_belief_table(kgss: pd.DataFrame, waves=3):
    """KGSS PARTYLR(1~5) + DK(0) — 최근 waves개 파동. 키: 권역·성·연령·학력 → 성·연령·학력 → 연령 → 전국."""
    from .harmonize import age_band, edu4_kgss
    recent_years = sorted(kgss["YEAR"].dropna().unique())[-waves:]
    sub = kgss[kgss["YEAR"].isin(recent_years)].copy()
    rows = []
    for _, r in sub.iterrows():
        p = r["PARTYLR"]
        if p in (1, 2, 3, 4, 5):
            v = int(p)
        elif p in (8, -8):
            v = 0  # DK/무응답 — 상태로 보존 (phase0 부동층 교훈)
        else:
            continue
        if pd.isna(r["AGE"]) or pd.isna(r["SEX"]) or pd.isna(r["EDUC"]) or pd.isna(r["REGION"]):
            continue
        rows.append({"reg7": int(r["REGION"]), "sex": str(int(r["SEX"])),
                     "age_g": age_band(int(r["AGE"])), "edu4": edu4_kgss(r["EDUC"]), "v": v, "w": 1.0})
    fit_levels = [
        ("L1_권역·성·연령·학력", lambda r: (r["reg7"], r["sex"], r["age_g"], r["edu4"])),
        ("L2_성·연령·학력", lambda r: (r["sex"], r["age_g"], r["edu4"])),
        ("L3_연령", lambda r: (r["age_g"],)),
        ("L4_전국", lambda r: "ALL"),
    ]
    t = CascadeTable(fit_levels, MIN_CELL_KGSS).fit(rows, lambda r: r["v"], lambda r: r["w"])
    t.levels = [
        ("L1_권역·성·연령·학력", lambda p: (p["reg7"], p["sex"], p["age_g"], p["edu4"])),
        ("L2_성·연령·학력", lambda p: (p["sex"], p["age_g"], p["edu4"])),
        ("L3_연령", lambda p: (p["age_g"],)),
        ("L4_전국", lambda p: "ALL"),
    ]
    t.meta = {"waves": [int(y) for y in recent_years], "n": len(rows)}
    return t
