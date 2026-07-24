"""EXP-004 채점기: 3암 재분해 리포트. 집계는 weight_bank (ISS-016 게이트).

지표(ISS-015 취지): 후보별 오차(MAE·최대), 1·2위 마진 오차, 이준석 raw 건수·재현율,
기권·DK율(분모 분리), 시도 1위 적중(가중), phase0 기록 대비 4성분 재분해.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT = json.load(open(ROOT / "phase0" / "data" / "ground_truth_2025.json", encoding="utf-8"))
CANDS = GT["candidates"]
OUT = ROOT / "data" / "t3"
PHASE0_VALID = {"더불어민주당 이재명": 70.42, "국민의힘 김문수": 29.58, "개혁신당 이준석": 0.0}
SIDO_FULL = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
             "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
             "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
             "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도",
             "제주": "제주특별자치도"}  # 뱅크 축약명 → 정답지 풀네임 (AUDIT: 이름 매칭 버그 수정)


def parse(text):
    m = re.search(r"\{.*?\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def norm_vote(v, options):
    if not isinstance(v, str):
        return None
    for c in CANDS + ["투표하지 않음", "누구에게 투표했는지 밝히고 싶지 않음"]:
        if c in v or v in c:
            return c
    for o in options:  # A암 주석 포함 선택지 대응
        if v.strip() == o.strip():
            for c in CANDS:
                if c in o:
                    return c
    return None


def score_arm(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    shares = {c: 0.0 for c in CANDS}
    abstain = dk = bad = 0.0
    total_w = 0.0
    sido_votes = {}
    raw_counts = {c: 0 for c in CANDS}
    for r in rows:
        if "error" in r:
            continue
        w = r["weight_bank"] / len(r["samples"])   # 샘플 분포 보존 (최빈값 금지 — AGENTS)
        for s in r["samples"]:
            p = parse(s)
            v = norm_vote(p.get("vote") if p else None, r.get("options", []))
            total_w += w
            if v in shares:
                shares[v] += w
                raw_counts[v] += 1
                sd = r["sido_name"]
                sido_votes.setdefault(sd, {c: 0.0 for c in CANDS})
                sido_votes[sd][v] += w
            elif v == "투표하지 않음":
                abstain += w
            elif v is not None:
                dk += w
            else:
                bad += w
    valid = sum(shares.values())
    pct = {c: round(shares[c] / valid * 100, 2) for c in CANDS} if valid else {}
    errs = {c: round(pct.get(c, 0) - GT["national_pct"][c], 2) for c in CANDS}
    margin_err = round((pct.get(CANDS[0], 0) - pct.get(CANDS[1], 0))
                       - (GT["national_pct"][CANDS[0]] - GT["national_pct"][CANDS[1]]), 2)
    # 시도 1위 적중 (가중)
    hit = tot = 0
    for sd, v in sido_votes.items():
        gt_sd = GT["sido_pct"].get(SIDO_FULL.get(sd, sd))
        if not gt_sd:
            continue
        tot += 1
        if max(v, key=v.get) == max(gt_sd, key=gt_sd.get):
            hit += 1
    return {"n_rows": len(rows), "pct_valid": pct, "err": errs,
            "mae": round(sum(abs(e) for e in errs.values()) / len(errs), 2),
            "max_err": round(max(abs(e) for e in errs.values()), 2),
            "margin_err": margin_err,
            "lee_junseok_raw": raw_counts["개혁신당 이준석"],
            "abstain_pct": round(abstain / total_w * 100, 2) if total_w else 0,
            "dk_pct": round(dk / total_w * 100, 2) if total_w else 0,
            "parse_fail_pct": round(bad / total_w * 100, 2) if total_w else 0,
            "sido_hit": f"{hit}/{tot}"}


def main():
    smoke = "--smoke" in sys.argv
    suf = "_smoke" if smoke else ""
    report = {}
    for arm in ["A", "B", "C"]:
        p = OUT / f"raw_{arm}{suf}.jsonl"
        if p.exists():
            report[arm] = score_arm(p)
            r = report[arm]
            print(f"\n[{arm}암] n={r['n_rows']} | 유효표 분포 {r['pct_valid']}")
            print(f"  MAE {r['mae']}%p | 최대오차 {r['max_err']}%p | 마진오차 {r['margin_err']}%p | "
                  f"이준석 raw {r['lee_junseok_raw']} | 기권 {r['abstain_pct']}% | DK {r['dk_pct']}% | 시도적중 {r['sido_hit']}")
    if {"A", "B", "C"} <= set(report):
        lee = CANDS[0]
        print("\n═══ 4성분 재분해 (이재명 유효표 % 기준) ═══")
        a, b, c = (report[x]["pct_valid"].get(lee, 0) for x in "ABC")
        print(f"phase0 기록 {PHASE0_VALID[lee]} → A {a} (페르소나 소스 효과 {round(a-PHASE0_VALID[lee],1)})")
        print(f"A {a} → B {b} (프롬프트 자책골 성분 {round(b-a,1)})")
        print(f"B {b} → C {c} (강제선택 성분 {round(c-b,1)})")
        print(f"C {c} vs 실제 {GT['national_pct'][lee]} (잔여 모델 편향 {round(c-GT['national_pct'][lee],1)})")
    json.dump(report, open(OUT / f"score_report{suf}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n→ {OUT / f'score_report{suf}.json'}")


if __name__ == "__main__":
    main()
