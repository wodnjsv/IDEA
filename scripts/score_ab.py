"""EXP-005 채점기 — B(대조군, EXP-004 산출물) vs D(생각 카드) vs E(후보 프로필).

판정 기준(사전 등록 — EXP-005 카드):
  D암: ① 크로스보팅 출현(보수계→이재명 5~15% 방향, 진보계→김문수 >0) ② 중도→김문수 >10%
       ③ Step1 에코 해소(자가진단 분포가 단일값 아님) ④ topline MAE 악화 ≤ +1%p
  E암: ① 송진호 <1% ② 이준석 8.3% 방향 개선 ③ 이재명·김문수 변화 ±2%p 내(부작용 없음)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT = json.load(open(ROOT / "phase0" / "data" / "ground_truth_2025.json", encoding="utf-8"))
CANDS = GT["candidates"]
OUT = ROOT / "data" / "t3"
LEE, KIM, JUN, SONG = CANDS[0], CANDS[1], CANDS[2], CANDS[4]
G3 = {1: "진보", 2: "진보", 3: "중도", 4: "보수", 5: "보수"}


def parse(t):
    m = re.search(r"\{.*?\}", t or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def norm(v):
    if not isinstance(v, str):
        return None
    for c in CANDS + ["투표하지 않음", "누구에게 투표했는지 밝히고 싶지 않음"]:
        if c in v:
            return c
    for c in CANDS:
        if c.split()[-1] in v:
            return c
    return None


def ideo_of(rec, arm, bank):
    if arm == "D":
        pl = rec.get("donor_partylr")
        return G3.get(pl)
    ci = rec.get("card_ideology") or bank.get(rec["persona_id"], {}).get("drawn", {}).get("ideology_label")
    return {"매우 진보": "진보", "다소 진보": "진보", "중도": "중도",
            "다소 보수": "보수", "매우 보수": "보수"}.get(ci)


def score(path, arm, bank):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    shares = {c: 0.0 for c in CANDS}
    iv = {}
    step1 = {}
    abstain = tot = 0.0
    for r in rows:
        if "error" in r:
            continue
        w = r["weight_bank"] / len(r["samples"])
        ideo = ideo_of(r, arm, bank)
        for s in r["samples"]:
            p = parse(s)
            v = norm(p.get("vote") if p else None)
            tot += w
            if p and p.get("ideology"):
                step1[p["ideology"]] = step1.get(p["ideology"], 0) + 1
            if v in shares:
                shares[v] += w
                if ideo:
                    iv.setdefault(ideo, {c: 0.0 for c in CANDS})
                    iv[ideo][v] += w
            elif v == "투표하지 않음":
                abstain += w
    valid = sum(shares.values())
    pct = {c: round(shares[c] / valid * 100, 2) for c in CANDS}
    errs = {c: round(pct[c] - GT["national_pct"][c], 2) for c in CANDS}
    mapping = {}
    for ideo, d in iv.items():
        t = sum(d.values())
        mapping[ideo] = {c.split()[-1]: round(x / t * 100, 1) for c, x in d.items() if x / t > 0.005}
    return {"n": len(rows), "pct": pct, "err": errs,
            "mae": round(sum(abs(e) for e in errs.values()) / len(errs), 2),
            "song": pct[SONG], "jun": pct[JUN],
            "cross_cons_to_lee": mapping.get("보수", {}).get("이재명", 0.0),
            "cross_prog_to_kim": mapping.get("진보", {}).get("김문수", 0.0),
            "mid_to_kim": mapping.get("중도", {}).get("김문수", 0.0),
            "step1_dist": {k: round(v / sum(step1.values()) * 100, 1) for k, v in step1.items()},
            "mapping": mapping, "abstain_pct": round(abstain / tot * 100, 2)}


def main():
    smoke = "--smoke" in sys.argv
    suf = "_smoke" if smoke else ""
    bank = {json.loads(l)["persona_id"]: json.loads(l)
            for l in open(ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl", encoding="utf-8")}
    report = {}
    for arm in ["B", "D", "E"]:
        p = OUT / f"raw_{arm}{suf}.jsonl"
        if not p.exists():
            continue
        r = report[arm] = score(p, arm, bank)
        print(f"\n[{arm}암] n={r['n']} MAE {r['mae']}%p | 분포 {r['pct']}")
        print(f"  송진호 {r['song']}% | 이준석 {r['jun']}% | 기권 {r['abstain_pct']}%")
        print(f"  매핑: {json.dumps(r['mapping'], ensure_ascii=False)}")
        print(f"  Step1 자가진단 분포: {r['step1_dist']}")
    if "D" in report and "B" in report:
        d, b = report["D"], report["B"]
        print("\n═══ D암 판정 (생각 카드 — ISS-018) ═══")
        print(f"① 크로스보팅: 보수계→이재명 {d['cross_cons_to_lee']}% (B: {b['cross_cons_to_lee']}%) / 진보계→김문수 {d['cross_prog_to_kim']}% (B: {b['cross_prog_to_kim']}%)")
        print(f"② 중도→김문수: {d['mid_to_kim']}% (B: {b['mid_to_kim']}%)")
        print(f"③ Step1 다양화: {d['step1_dist']}")
        print(f"④ MAE: {d['mae']} vs B {b['mae']}")
    if "E" in report and "B" in report:
        e, b = report["E"], report["B"]
        print("\n═══ E암 판정 (후보 프로필 — ISS-017) ═══")
        print(f"① 송진호: {e['song']}% (B: {b['song']}%, 목표 <1%)")
        print(f"② 이준석: {e['jun']}% (B: {b['jun']}%, 실제 8.34%)")
        print(f"③ 부작용: 이재명 Δ{round(e['pct'][LEE]-b['pct'][LEE],2)}%p, 김문수 Δ{round(e['pct'][KIM]-b['pct'][KIM],2)}%p (±2 내 목표)")
    json.dump(report, open(OUT / f"score_ab{suf}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ {OUT / f'score_ab{suf}.json'}")


if __name__ == "__main__":
    main()
