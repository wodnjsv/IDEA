"""페르소나 뱅크 빌더: 스켈레톤 샘플링(센서스 실레코드) + 추첨(조회표) + 렌더링.

⚠️ 이념(ideology) 라벨은 ISS-010 인간 검증 게이트 통과 전 '개발용'이다 — 프로덕션 런 사용 금지.
"""
import json

import numpy as np
import pandas as pd

from . import harmonize as H
from .registry import resolve
from .tables import build_belief_table, build_income_table, build_wage_table

CENSUS_P_COLS = ["가구일련번호", "행정구역시도코드", "행정구역시군구코드", "성별코드", "만연령",
                 "교육정도코드", "혼인상태코드", "경제활동상태코드", "종사상지위코드",
                 "산업대분류코드", "직업대분류코드", "통근통학구분코드", "통근통학장소코드",
                 "통근통학_소요분수", "인구가중값"]
CENSUS_H_COLS = ["가구일련번호", "점유형태코드", "거처종류코드", "세대유형코드", "가구가중값"]


def load_pool():
    p = pd.read_csv(resolve("census_2020_2pct_person"), encoding="cp949", dtype=str, usecols=CENSUS_P_COLS)
    h = pd.read_csv(resolve("census_2020_2pct_household"), encoding="cp949", dtype=str, usecols=CENSUS_H_COLS)
    h = h.drop_duplicates(subset="가구일련번호")
    p["만연령"] = p["만연령"].astype(int)
    pool = p[p["만연령"] >= 18].merge(h, on="가구일련번호", how="left", suffixes=("", "_h"))
    pool["인구가중값"] = pool["인구가중값"].astype(float)
    return pool


def load_tables():
    laf = pd.read_csv(resolve("laf_2025h1_a"), encoding="cp949", dtype=str,
                      usecols=["성별코드", "만연령", "교육정도_학력구분코드", "최근3개월_월평균급여",
                               "4자리_행정구역시군구코드", "시군구가중값"])
    laf = laf.rename(columns={"성별코드": "sex", "만연령": "age", "교육정도_학력구분코드": "edu",
                              "최근3개월_월평균급여": "wage", "4자리_행정구역시군구코드": "sgg4",
                              "시군구가중값": "wt"}).fillna("")
    laf = laf[laf["wage"] != ""]
    W = build_wage_table(laf)

    sflc = pd.read_csv(resolve("sflc_2025_master"), encoding="cp949", dtype=str,
                       usecols=["수도권여부", "가구주연령_10세단위코드", "가구주_교육정도_통합코드",
                                "입주형태통합코드", "소득10분위코드(보완)(2017년~)", "가중값"])
    sflc = sflc.rename(columns={"수도권여부": "cap", "가구주연령_10세단위코드": "age10",
                                "가구주_교육정도_통합코드": "edu", "입주형태통합코드": "ten",
                                "소득10분위코드(보완)(2017년~)": "d10", "가중값": "wt"}).fillna("")
    I = build_income_table(sflc)

    import pyreadstat
    kgss, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")),
                                  usecols=["YEAR", "PARTYLR", "REGION", "AGE", "SEX", "EDUC"])
    K = build_belief_table(kgss)
    return W, I, K


SFLC_TEN = {"자기집": "G1", "전세": "G2", "월세": "G3", "기타": "G4"}


def persona_keys(row) -> dict:
    sido = row["행정구역시도코드"]
    sgg = row["행정구역시군구코드"]
    age = int(row["만연령"])
    edu4 = H.edu4_census(row["교육정도코드"]) if pd.notna(row["교육정도코드"]) and row["교육정도코드"] else None
    ten4 = H.tenure4(row["점유형태코드"]) if pd.notna(row["점유형태코드"]) and row["점유형태코드"] else "기타"
    return {
        "sido": sido, "sgg": sgg, "age": age, "age_g": H.age_band(age),
        "age10": H.age_band10_sflc(age), "sex": row["성별코드"], "edu4": edu4,
        "edu3": H.edu3_sflc(edu4) if edu4 else None,
        "reg7": H.SIDO_TO_REGION7[sido], "cap": H.sflc_capital(sido),
        "ten4_g": SFLC_TEN[ten4], "laf_sgg": H.CENSUS_TO_LAF_SIGUNGU.get((sido, sgg)),
    }


def render_card(sk: dict, drawn: dict) -> str:
    parts = [f"당신은 {H.SIDO_NAME[sk['sido']]}"]
    if sk.get("region_label"):
        parts[0] += f" {sk['region_label']}"
    parts[0] += f"에 사는 {sk['age']}세 {'남성' if sk['sex']=='1' else '여성'}입니다."
    edu_t = {"중졸이하": "학교는 중학교까지 다녔고", "고졸": "고등학교를 졸업했고",
             "전문·대졸": "대학을 졸업했고", "대학원이상": "대학원까지 마쳤고", None: ""}[sk["edu4"]]
    econ = sk["econ_label"]
    if econ:
        parts.append(f"{edu_t} 현재 {econ}.")
    if sk.get("commute_label"):
        parts.append(sk["commute_label"])
    parts.append(f"{sk['dwelling_label']}에 {sk['tenure_label']}로 거주하며, 혼인 상태는 {sk['marital_label']}입니다.")
    if drawn.get("wage_band"):
        parts.append(f"월평균 급여는 {drawn['wage_band']} 수준입니다.")
    if drawn.get("hh_income_decile"):
        parts.append(f"가구 소득은 전국 10분위 중 {drawn['hh_income_decile']}분위 정도입니다.")
    if drawn.get("ideology_label"):
        parts.append(f"정치적으로는 스스로 '{drawn['ideology_label']}' 성향이라고 생각합니다.")
    return " ".join(parts)


def build_bank(track: str, n: int, seed: int, pool, W, I, K):
    rng = np.random.default_rng(seed)
    if track == "gwangmyeong":
        sub = pool[(pool["행정구역시도코드"] == "31") & (pool["행정구역시군구코드"] == "060")]
        idx = rng.choice(sub.index, size=n, replace=False,
                         p=(sub["인구가중값"] / sub["인구가중값"].sum()).values)
        picked = sub.loc[idx]
    elif track == "national":
        # 시도 층화: 가중 인구 비례 배분(최소 5), 시도 내 가중 샘플링
        alloc_w = pool.groupby("행정구역시도코드")["인구가중값"].sum()
        alloc = (alloc_w / alloc_w.sum() * n).round().astype(int).clip(lower=5)
        while alloc.sum() != n:
            alloc[alloc.idxmax()] += np.sign(n - alloc.sum())
        parts = []
        for sido, k in alloc.items():
            s = pool[pool["행정구역시도코드"] == sido]
            idx = rng.choice(s.index, size=int(k), replace=False,
                             p=(s["인구가중값"] / s["인구가중값"].sum()).values)
            parts.append(s.loc[idx])
        picked = pd.concat(parts)
    else:
        raise ValueError(track)

    personas, fallback_stats = [], {"wage": {}, "income": {}, "belief": {}}
    for i, (_, row) in enumerate(picked.iterrows()):
        sk = persona_keys(row)
        sk["region_label"] = "광명시" if sk["laf_sgg"] == "3106" else None
        sk["marital_label"] = H.MARITAL.get(row["혼인상태코드"], "미상")
        sk["dwelling_label"] = H.DWELLING.get(row["거처종류코드"], "주택")
        sk["tenure_label"] = H.TENURE.get(row["점유형태코드"], "기타")
        emp = H.EMPSTAT.get(row["종사상지위코드"])
        occ = H.OCCUPATION.get(row["직업대분류코드"])
        ind = H.INDUSTRY.get(row["산업대분류코드"])
        if emp and occ:
            sk["econ_label"] = f"{ind or ''} 분야에서 {occ}로 일하는 {emp}입니다".strip()
        elif H.ECON.get(row["경제활동상태코드"]) == "일하지 않았음":
            sk["econ_label"] = "일을 하고 있지 않습니다"
        else:
            sk["econ_label"] = None
        cm = row["통근통학구분코드"]
        if cm == "1" and row["통근통학장소코드"]:
            place = H.COMMUTE_PLACE.get(row["통근통학장소코드"], "")
            mins = row["통근통학_소요분수"]
            sk["commute_label"] = f"직장은 {place}에 있고 통근에 약 {int(float(mins))}분 걸립니다." if mins else f"직장은 {place}에 있습니다."
        else:
            sk["commute_label"] = None

        drawn = {}
        # 급여: 스켈레톤이 임금근로자일 때만
        if row["종사상지위코드"] == "1":
            v, lv, cn = W.draw(sk, rng)
            drawn["wage_band"] = v
            fallback_stats["wage"][lv] = fallback_stats["wage"].get(lv, 0) + 1
        v, lv, cn = I.draw(sk, rng)
        drawn["hh_income_decile"] = int(v[1:]) if v else None
        fallback_stats["income"][lv] = fallback_stats["income"].get(lv, 0) + 1
        v, lv, cn = K.draw(sk, rng)
        drawn["ideology_code"] = int(v) if v is not None else None
        drawn["ideology_label"] = H.IDEOLOGY.get(drawn["ideology_code"]) if v is not None else None
        if drawn["ideology_label"] == "모름/무응답":
            drawn["ideology_label"] = None  # 카드에는 미표기(무응답 보존은 코드로)
        fallback_stats["belief"][lv] = fallback_stats["belief"].get(lv, 0) + 1

        personas.append({
            "persona_id": f"{track[:2].upper()}-{seed}-{i:05d}",
            "track": track,
            "skeleton": {
                "sido": sk["sido"], "sido_name": H.SIDO_NAME[sk["sido"]], "sigungu": sk["sgg"],
                "sex": "남" if sk["sex"] == "1" else "여", "age": sk["age"], "age_band": sk["age_g"],
                "edu4": sk["edu4"], "marital": sk["marital_label"],
                "empstat": emp, "occupation": occ, "industry": ind,
                "commute": sk["commute_label"], "tenure": sk["tenure_label"],
                "dwelling": sk["dwelling_label"], "hh_id": row["가구일련번호"],
            },
            "drawn": drawn,
            "weight_person": float(row["인구가중값"]),
            "card": render_card(sk, drawn),
            "provenance": {"census": "2020_2pct", "wage": "LAF_2025H1_A", "income": "SFLC_2025",
                           "kgss": "CUM0074_V2_recent3", "seed": seed,
                           "ideology_gate": "ISS-010 인간검증 전 — 개발용"},
        })
    return personas, picked, fallback_stats
