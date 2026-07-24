"""EXP-005 D암용 '생각 카드' 생성기 — KGSS hot-deck (조합 보존).

각 페르소나와 같은 셀(권역·성·연령·학력)의 실제 KGSS 응답자 1명을 추첨해
신념 5문항 응답을 통째로 복사한다(문항 간 상관 보존 — 소득×주거 교훈과 동일 논리).
donor의 PARTYLR은 진단용으로만 저장하고 카드에는 렌더링하지 않는다.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

from engine import harmonize as H  # noqa: E402
from engine.registry import resolve  # noqa: E402

ITEMS = ["UNIFI", "NORTHWHO", "CONBUS", "CONLABOR", "SATFIN"]
SENT = {
    "UNIFI": {1: "남북통일이 매우 필요하다고 생각하고", 2: "남북통일이 어느 정도 필요하다고 생각하고",
              3: "남북통일이 별로 필요하지 않다고 생각하고", 4: "남북통일이 전혀 필요하지 않다고 생각하고"},
    "NORTHWHO": {1: "북한을 지원해야 할 대상으로 봅니다.", 2: "북한을 협력 대상으로 봅니다.",
                 3: "북한을 경계해야 할 대상으로 봅니다.", 4: "북한을 적대 대상으로 봅니다."},
    "CONBUS": {1: "대기업을 매우 신뢰하고", 2: "대기업을 어느 정도 신뢰하고", 3: "대기업을 거의 신뢰하지 않고"},
    "CONLABOR": {1: "노동조합은 매우 신뢰합니다.", 2: "노동조합은 어느 정도 신뢰합니다.", 3: "노동조합은 거의 신뢰하지 않습니다."},
    "SATFIN": {1: "요즘 가계 형편에는 매우 만족하는 편입니다.", 2: "요즘 가계 형편에는 대체로 만족하는 편입니다.",
               3: "요즘 가계 형편은 만족도 불만족도 아닙니다.", 4: "요즘 가계 형편에는 다소 불만족하는 편입니다.",
               5: "요즘 가계 형편에는 매우 불만족하는 편입니다."},
}


def render(ans: dict) -> str:
    parts = []
    if ans.get("UNIFI") and ans.get("NORTHWHO"):
        parts.append(f"평소 {SENT['UNIFI'][ans['UNIFI']]}, {SENT['NORTHWHO'][ans['NORTHWHO']]}")
    elif ans.get("UNIFI"):
        parts.append(f"평소 {SENT['UNIFI'][ans['UNIFI']].replace('생각하고','생각합니다.')}")
    elif ans.get("NORTHWHO"):
        parts.append(f"평소 {SENT['NORTHWHO'][ans['NORTHWHO']]}")
    if ans.get("CONBUS") and ans.get("CONLABOR"):
        parts.append(f"{SENT['CONBUS'][ans['CONBUS']]}, {SENT['CONLABOR'][ans['CONLABOR']]}")
    elif ans.get("CONBUS"):
        parts.append(SENT['CONBUS'][ans['CONBUS']].replace("신뢰하고", "신뢰합니다."))
    elif ans.get("CONLABOR"):
        parts.append(SENT['CONLABOR'][ans['CONLABOR']])
    if ans.get("SATFIN"):
        parts.append(SENT['SATFIN'][ans['SATFIN']])
    return " ".join(parts)


def main():
    kgss, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")),
                                  usecols=["YEAR", "PARTYLR", "REGION", "AGE", "SEX", "EDUC"] + ITEMS)
    d = kgss[kgss["YEAR"].isin([2021, 2023, 2025])].copy()
    d = d.dropna(subset=["REGION", "AGE", "SEX", "EDUC"])
    for c in ITEMS:
        d[c] = d[c].where(d[c].isin(list(SENT[c].keys())))
    d["n_valid"] = d[ITEMS].notna().sum(axis=1)
    d = d[d["n_valid"] >= 3]
    d["age_g"] = d["AGE"].astype(int).map(H.age_band)
    d["edu4"] = d["EDUC"].map(H.edu4_kgss)
    d["sex"] = d["SEX"].astype(int).astype(str)
    d["reg7"] = d["REGION"].astype(int)
    print(f"도너 풀: {len(d)}명 (신념 3문항+ 유효)")

    levels = [["reg7", "sex", "age_g", "edu4"], ["sex", "age_g", "edu4"], ["age_g"], []]
    groups = [d.groupby(lv) if lv else None for lv in levels]

    bank = [json.loads(l) for l in open(ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl", encoding="utf-8")]
    out, level_use = {}, {}
    for p in bank:
        sk = p["skeleton"]
        key_all = {"reg7": H.SIDO_TO_REGION7[sk["sido"]], "sex": "1" if sk["sex"] == "남" else "2",
                   "age_g": sk["age_band"], "edu4": sk["edu4"]}
        rng = random.Random(f"belief-{p['persona_id']}")
        donor = None
        for li, lv in enumerate(levels):
            try:
                pool = groups[li].get_group(tuple(key_all[k] for k in lv)) if lv else d
            except KeyError:
                continue
            if len(pool) >= 5:
                donor = pool.iloc[rng.randrange(len(pool))]
                level_use[f"L{li+1}"] = level_use.get(f"L{li+1}", 0) + 1
                break
        ans = {c: int(donor[c]) if pd.notna(donor[c]) else None for c in ITEMS}
        out[p["persona_id"]] = {
            "sentences": render(ans), "answers": ans,
            "donor_partylr": int(donor["PARTYLR"]) if donor["PARTYLR"] in (1, 2, 3, 4, 5) else 0,
            "donor_year": int(donor["YEAR"]),
        }
    json.dump(out, open(ROOT / "data" / "t3" / "belief_cards.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"생각 카드 {len(out)}건 생성 → data/t3/belief_cards.json | 폴백: {level_use}")
    ex = out[bank[0]["persona_id"]]
    print("예시:", ex["sentences"])


if __name__ == "__main__":
    main()
