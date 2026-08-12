"""EXP-007 신념 카드 v2 — 축 재균형(경제2·안보1·신뢰1·생활1) + 톤 2종(D2A 단정 / D2B 완화).

v1(build_belief_cards.py)의 핫덱 로직 재사용: 같은 셀(권역·성·연령·학력) 실제 KGSS 응답자
1명에게서 5문항을 통째로 복사(문항 간 상관 보존). D2A/D2B는 **동일 도너**(동일 시드) —
차이는 렌더링 톤뿐이므로 톤 효과가 분리된다. donor PARTYLR은 진단용 저장·비렌더링(ISS-022).

실행 전 사전등록 검증($0)을 먼저 출력한다: 문항별 파동(2021/2023/2025) 커버리지 + PARTYLR 상관.

    python scripts/build_belief_cards_v2.py
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

ITEMS = ["UNIFI", "CONBUS", "SATFIN", "GOVSPD6", "GOVSPD7"]
VALID = {"UNIFI": (1, 2, 3, 4), "CONBUS": (1, 2, 3), "SATFIN": (1, 2, 3, 4, 5),
         "GOVSPD6": (1, 2, 3, 4, 5), "GOVSPD7": (1, 2, 3, 4, 5)}

# ── 단정 톤 (D2A) — v1 문장 유지(UNIFI/CONBUS/SATFIN) + 지출 2문항 신규 ──
A_UNIFI = {1: "남북통일이 매우 필요하다고 생각합니다.", 2: "남북통일이 어느 정도 필요하다고 생각합니다.",
           3: "남북통일이 별로 필요하지 않다고 생각합니다.", 4: "남북통일이 전혀 필요하지 않다고 생각합니다."}
A_CONBUS = {1: "대기업을 매우 신뢰합니다.", 2: "대기업을 어느 정도 신뢰합니다.", 3: "대기업을 거의 신뢰하지 않습니다."}
A_SATFIN = {1: "요즘 가계 형편에는 매우 만족하는 편입니다.", 2: "요즘 가계 형편에는 대체로 만족하는 편입니다.",
            3: "요즘 가계 형편은 만족도 불만족도 아닙니다.", 4: "요즘 가계 형편에는 다소 불만족하는 편입니다.",
            5: "요즘 가계 형편에는 매우 불만족하는 편입니다."}
A_G6 = {1: "노인연금에 대한 정부 지출을 훨씬 더 늘려야 한다고 생각하고", 2: "노인연금에 대한 정부 지출을 다소 더 늘려야 한다고 생각하고",
        3: "노인연금에 대한 정부 지출은 지금 수준이 적당하다고 생각하고", 4: "노인연금에 대한 정부 지출을 다소 줄여야 한다고 생각하고",
        5: "노인연금에 대한 정부 지출을 크게 줄여야 한다고 생각하고"}
A_G7 = {1: "실업수당은 훨씬 더 늘려야 한다고 봅니다.", 2: "실업수당은 다소 더 늘려야 한다고 봅니다.",
        3: "실업수당은 지금 수준이 적당하다고 봅니다.", 4: "실업수당은 다소 줄여야 한다고 봅니다.",
        5: "실업수당은 크게 줄여야 한다고 봅니다."}

# ── 완화 톤 (D2B) — "예전 설문에서 ~쪽에 가깝다고 답한 적이 있다" (ISS-018 옵션 2 결합) ──
B_UNIFI = {1: "남북통일이 매우 필요하다는 쪽에 가깝다고 답한 적이 있습니다.", 2: "남북통일이 어느 정도 필요하다는 쪽에 가깝다고 답한 적이 있습니다.",
           3: "남북통일이 별로 필요하지 않다는 쪽에 가깝다고 답한 적이 있습니다.", 4: "남북통일이 전혀 필요하지 않다는 쪽에 가깝다고 답한 적이 있습니다."}
B_CONBUS = {1: "대기업은 매우 신뢰하는 편이라고 답했습니다.", 2: "대기업은 어느 정도 신뢰하는 편이라고 답했습니다.",
            3: "대기업은 거의 신뢰하지 않는 편이라고 답했습니다."}
B_SATFIN = {1: "요즘 가계 형편에는 매우 만족하는 편이라고 답했습니다.", 2: "요즘 가계 형편에는 대체로 만족하는 편이라고 답했습니다.",
            3: "요즘 가계 형편은 그저 그렇다고 답했습니다.", 4: "요즘 가계 형편에는 다소 불만족하는 편이라고 답했습니다.",
            5: "요즘 가계 형편에는 매우 불만족하는 편이라고 답했습니다."}
B_G6 = {1: "노인연금 지출은 훨씬 더 늘리는 쪽에 가깝다고 했고", 2: "노인연금 지출은 다소 더 늘리는 쪽에 가깝다고 했고",
        3: "노인연금 지출은 지금 수준이 적당하다는 쪽이라고 했고", 4: "노인연금 지출은 다소 줄이는 쪽에 가깝다고 했고",
        5: "노인연금 지출은 크게 줄이는 쪽에 가깝다고 했고"}
B_G7 = {1: "실업수당은 훨씬 더 늘리는 쪽이라고 답했습니다.", 2: "실업수당은 다소 더 늘리는 쪽이라고 답했습니다.",
        3: "실업수당은 지금 수준이 적당하다는 쪽이라고 답했습니다.", 4: "실업수당은 다소 줄이는 쪽이라고 답했습니다.",
        5: "실업수당은 크게 줄이는 쪽이라고 답했습니다."}


def render(ans: dict, tone: str) -> str:
    u, c, s = (A_UNIFI, A_CONBUS, A_SATFIN) if tone == "A" else (B_UNIFI, B_CONBUS, B_SATFIN)
    g6, g7 = (A_G6, A_G7) if tone == "A" else (B_G6, B_G7)
    parts = []
    if ans.get("UNIFI"):
        parts.append(("평소 " if tone == "A" else "") + u[ans["UNIFI"]])
    if ans.get("CONBUS"):
        parts.append(c[ans["CONBUS"]])
    if ans.get("GOVSPD6") and ans.get("GOVSPD7"):
        parts.append(f"정부 지출에 대해서는 {g6[ans['GOVSPD6']]}, {g7[ans['GOVSPD7']]}")
    elif ans.get("GOVSPD6"):
        parts.append(g6[ans["GOVSPD6"]].replace("생각하고", "생각합니다.").replace("했고", "했습니다."))
    elif ans.get("GOVSPD7"):
        parts.append(g7[ans["GOVSPD7"]])
    if ans.get("SATFIN"):
        parts.append(s[ans["SATFIN"]])
    body = " ".join(parts)
    return body if tone == "A" else ("예전 한 설문조사에서 이렇게 답한 적이 있습니다: " + body)


def main():
    kgss, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")),
                                  usecols=["YEAR", "PARTYLR", "REGION", "AGE", "SEX", "EDUC"] + ITEMS)
    d = kgss[kgss["YEAR"].isin([2021, 2023, 2025])].copy()
    d = d.dropna(subset=["REGION", "AGE", "SEX", "EDUC"])
    for c in ITEMS:
        d[c] = d[c].where(d[c].isin(list(VALID[c])))

    # ── 사전등록 검증 ①: 파동 커버리지 ──
    print("== 사전등록 검증 ①: 파동별 유효 응답 수 ==")
    for c in ITEMS:
        cov = {int(y): int(d[d["YEAR"] == y][c].notna().sum()) for y in (2021, 2023, 2025)}
        print(f"  {c:8s} {cov}")
    # ── 사전등록 검증 ②: 문항별 PARTYLR(1진보~5보수) 상관 — 신호 강도 실측 ──
    print("== 사전등록 검증 ②: PARTYLR 상관 (참고: v1 안보축 +0.36/+0.55) ==")
    pl = d["PARTYLR"].where(d["PARTYLR"].isin([1, 2, 3, 4, 5]))
    for c in ITEMS:
        r = d[c].corr(pl)
        print(f"  {c:8s} r={r:+.3f}  (n={int((d[c].notna() & pl.notna()).sum())})")

    d["n_valid"] = d[ITEMS].notna().sum(axis=1)
    d = d[d["n_valid"] >= 3]
    d["age_g"] = d["AGE"].astype(int).map(H.age_band)
    d["edu4"] = d["EDUC"].map(H.edu4_kgss)
    d["sex"] = d["SEX"].astype(int).astype(str)
    d["reg7"] = d["REGION"].astype(int)
    print(f"도너 풀: {len(d)}명 (v2 문항 3+ 유효)")

    levels = [["reg7", "sex", "age_g", "edu4"], ["sex", "age_g", "edu4"], ["age_g"], []]
    groups = [d.groupby(lv) if lv else None for lv in levels]
    bank = [json.loads(l) for l in open(ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl", encoding="utf-8")]
    out, level_use = {}, {}
    for p in bank:
        sk = p["skeleton"]
        key_all = {"reg7": H.SIDO_TO_REGION7[sk["sido"]], "sex": "1" if sk["sex"] == "남" else "2",
                   "age_g": sk["age_band"], "edu4": sk["edu4"]}
        rng = random.Random(f"belief-v2-{p['persona_id']}")
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
            "D2A": {"sentences": render(ans, "A")}, "D2B": {"sentences": render(ans, "B")},
            "answers": ans,
            "donor_partylr": int(donor["PARTYLR"]) if donor["PARTYLR"] in (1, 2, 3, 4, 5) else 0,
            "donor_year": int(donor["YEAR"]),
        }
    json.dump(out, open(ROOT / "data" / "t3" / "belief_cards_v2.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"신념 카드 v2 {len(out)}건 → data/t3/belief_cards_v2.json | 폴백: {level_use}")
    ex = out[bank[0]["persona_id"]]
    print("예시 D2A:", ex["D2A"]["sentences"])
    print("예시 D2B:", ex["D2B"]["sentences"])


if __name__ == "__main__":
    main()
