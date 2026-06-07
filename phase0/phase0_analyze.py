"""
Phase 0 — 결과 분석 및 합격 판정
==================================
사용법:
    python phase0_analyze.py [--mode pilot|full]

입력:
    results/raw_responses_{mode}.jsonl
    data/ground_truth_2025.json

출력:
    results/analysis_{mode}.json
    results/verdict_{mode}.md
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict, Counter


PROVINCE_GROUPS = {
    "수도권": ["서울", "인천", "경기"],
    "영남": ["부산", "대구", "울산", "경상북", "경상남"],
    "호남": ["광주", "전라북", "전라남"],
    "충청": ["대전", "세종", "충청북", "충청남"],
    "강원제주": ["강원", "제주"],
}


def get_region(prov):
    for r, members in PROVINCE_GROUPS.items():
        if prov in members:
            return r
    return None


PROVINCE_NORMALIZE = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충청북": "충청북도",
    "충청남": "충청남도",
    "전라북": "전북특별자치도",
    "전라남": "전라남도",
    "경상북": "경상북도",
    "경상남": "경상남도",
    "제주": "제주특별자치도",
}

# 21대 대선 후보 (다양한 응답 변형 대응)
# 매칭 우선순위: 정확 → 후보명 → 정당명 → 키워드
VOTE_KEYWORDS = {
    "더불어민주당 이재명": ["이재명", "더불어민주당", "민주당", "이 재명"],
    "국민의힘 김문수": ["김문수", "국민의힘", "국힘", "김 문수"],
    "개혁신당 이준석": ["이준석", "개혁신당", "이 준석"],
    "민주노동당 권영국": ["권영국", "민주노동당", "노동당", "권 영국"],
    "무소속 송진호": ["송진호", "송 진호"],
    "투표하지 않음": ["투표하지 않음", "투표 안", "안 함", "기권", "투표안함", "투표 안함", "안함"],
}

CANDIDATES = [
    "더불어민주당 이재명",
    "국민의힘 김문수",
    "개혁신당 이준석",
    "민주노동당 권영국",
    "무소속 송진호",
    "투표하지 않음",
]


def normalize_vote(v):
    """다양한 응답 변형 → 표준 후보명. 우선순위 기반 매칭."""
    if not v:
        return None
    v = str(v).strip()
    # 후보명 우선 검색 (더 specific)
    for standard, keywords in VOTE_KEYWORDS.items():
        for kw in keywords:
            if kw in v:
                return standard
    return None


def normalize_province(p):
    if not p:
        return None
    return PROVINCE_NORMALIZE.get(p.strip(), p.strip())


def main(mode):
    base = Path(__file__).parent
    responses_path = base / f"results/raw_responses_{mode}.jsonl"
    ground_truth_path = base / "data/ground_truth_2025.json"

    if not responses_path.exists():
        print(f"Error: {responses_path} 없음. 먼저 phase0_run.py 실행.")
        return

    # Load ground truth
    with open(ground_truth_path, encoding="utf-8") as f:
        gt = json.load(f)

    # Load responses
    persona_results = []
    with open(responses_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                persona_results.append(json.loads(line))

    print(f"분석 대상: {len(persona_results)}명 페르소나")

    # 전국 집계 (각 페르소나 1표로 등가 가중. 추후 인구 가중치 적용 가능)
    national_votes = Counter()
    by_province = defaultdict(Counter)
    unparseable = 0
    total_samples = 0

    for pr in persona_results:
        sido = normalize_province(pr["demographic"].get("province"))
        votes_for_persona = Counter()
        for s in pr["samples"]:
            total_samples += 1
            parsed = s.get("parsed")
            if not parsed:
                unparseable += 1
                continue
            vote = normalize_vote(parsed.get("vote"))
            if vote:
                votes_for_persona[vote] += 1
            else:
                unparseable += 1
        # 페르소나당 가장 빈번한 응답을 그 사람의 투표로 결정 (mode)
        if votes_for_persona:
            top_vote = votes_for_persona.most_common(1)[0][0]
            national_votes[top_vote] += 1
            if sido:
                by_province[sido][top_vote] += 1

    # 유효 후보만 (투표하지 않음 제외) — 정답지와 동일 기준
    valid_candidates = [c for c in CANDIDATES if c != "투표하지 않음"]

    # 전국 득표율 계산 (분모: 실제 투표한 페르소나 = 투표하지 않음 제외)
    valid_votes_total = sum(national_votes.get(c, 0) for c in valid_candidates)
    sim_national_pct = {c: round(national_votes.get(c, 0) / max(valid_votes_total, 1) * 100, 2)
                        for c in valid_candidates}
    nonvote_count = national_votes.get("투표하지 않음", 0)
    nonvote_rate = round(nonvote_count / max(len(persona_results), 1) * 100, 2)

    # 시도별 1위 (유효 후보 중에서만)
    sim_sido_winner = {}
    for sido, votes in by_province.items():
        valid_votes_in_sido = {c: votes[c] for c in valid_candidates if c in votes}
        if valid_votes_in_sido:
            sim_sido_winner[sido] = max(valid_votes_in_sido.items(), key=lambda x: x[1])[0]

    # 정답과 비교
    print(f"\n시뮬 투표 안 함 비율: {nonvote_rate:.1f}% ({nonvote_count}/{len(persona_results)})")
    print(f"실제 21대 대선 투표율: 79.4% (참고)")
    print("\n=== 전국 득표율 비교 (유효 투표 기준) ===")
    print(f"{'후보':<25} {'실제':>8} {'시뮬':>8} {'오차':>8}")
    print("-" * 55)
    errors = {}
    for c in valid_candidates:
        actual = gt["national_pct"].get(c, 0)
        sim = sim_national_pct.get(c, 0)
        err = abs(actual - sim)
        errors[c] = err
        flag = "✓" if err <= 5.0 else "✗"
        print(f"  {c:<23} {actual:>7.2f}% {sim:>7.2f}% {err:>+7.2f}p {flag}")

    avg_err = sum(errors.values()) / len(errors)
    max_err = max(errors.values())
    pass_pct_criterion = max_err <= 5.0
    print(f"\n평균 오차: {avg_err:.2f}p, 최대 오차: {max_err:.2f}p")
    print(f"기준 ①: 모든 후보 ≤5%p {'✓ 통과' if pass_pct_criterion else '✗ 미달'}")

    # 시도별 1위 일치율
    print("\n=== 시도별 1위 후보 일치율 ===")
    matches = 0
    total_sido = 0
    sido_compare = {}
    for sido in gt["sido_winner"]:
        actual_winner = gt["sido_winner"][sido]
        sim_winner = sim_sido_winner.get(sido)
        if not sim_winner:
            sido_compare[sido] = {"actual": actual_winner, "sim": "샘플 없음", "match": False}
            continue
        total_sido += 1
        match = (actual_winner == sim_winner)
        if match:
            matches += 1
        sido_compare[sido] = {"actual": actual_winner, "sim": sim_winner, "match": match}
        flag = "✓" if match else "✗"
        a = actual_winner.split()[-1]  # short name
        s = sim_winner.split()[-1]
        print(f"  {sido:<10} 실제={a:<6} 시뮬={s:<6} {flag}")

    match_rate = matches / total_sido * 100 if total_sido > 0 else 0
    pass_sido_criterion = match_rate >= 80.0
    print(f"\n일치: {matches}/{total_sido} = {match_rate:.1f}%")
    print(f"기준 ②: ≥80% (13개 이상) {'✓ 통과' if pass_sido_criterion else '✗ 미달'}")

    # 권역별 결과 (디버깅·진단용)
    region_votes = defaultdict(Counter)
    region_persona_count = Counter()
    for pr in persona_results:
        sido = normalize_province(pr["demographic"].get("province"))
        prov_short = pr["demographic"].get("province")
        region = get_region(prov_short)
        if not region:
            continue
        region_persona_count[region] += 1
        for s in pr["samples"]:
            parsed = s.get("parsed")
            if not parsed:
                continue
            v = normalize_vote(parsed.get("vote"))
            if v:
                region_votes[region][v] += 1

    print("\n=== 권역별 시뮬 응답 분포 (전체 호출 기준) ===")
    print(f"{'권역':<10}{'페르소나':<10}{'이재명':<10}{'김문수':<10}{'이준석':<10}{'기타':<8}")
    print("-" * 60)
    for region in ["수도권", "영남", "호남", "충청", "강원제주"]:
        n_p = region_persona_count.get(region, 0)
        votes = region_votes.get(region, Counter())
        total = sum(votes.values())
        if total == 0:
            continue
        j = votes.get("더불어민주당 이재명", 0) / total * 100
        k = votes.get("국민의힘 김문수", 0) / total * 100
        p = votes.get("개혁신당 이준석", 0) / total * 100
        rest = 100 - j - k - p
        print(f"{region:<10}{n_p:<10}{j:<10.1f}{k:<10.1f}{p:<10.1f}{rest:<8.1f}")

    # 최종 판정
    print("\n" + "=" * 60)
    if pass_pct_criterion and pass_sido_criterion:
        verdict = "PASS"
        print("🎉 PASS: 0단계 합격! 1단계 진행 가능. PROPOSAL.md Q4 업데이트.")
    elif pass_pct_criterion or pass_sido_criterion:
        verdict = "BORDERLINE"
        print("⚠️  BORDERLINE: 한 기준만 통과. 프롬프트 1회 수정 후 재시도 권장.")
    else:
        verdict = "FAIL"
        print("❌ FAIL: 두 기준 모두 미달. 전략 재설계 필요 (모델 교체 또는 프롬프트 근본 재설계).")
    print("=" * 60)

    # 저장
    analysis = {
        "mode": mode,
        "n_personas": len(persona_results),
        "total_samples": total_samples,
        "unparseable": unparseable,
        "parse_success_rate": round((total_samples - unparseable) / max(total_samples, 1) * 100, 1),
        "national_pct_sim": sim_national_pct,
        "national_pct_actual": gt["national_pct"],
        "national_errors": errors,
        "avg_error": round(avg_err, 2),
        "max_error": round(max_err, 2),
        "sido_compare": sido_compare,
        "match_rate": round(match_rate, 1),
        "verdict": verdict,
        "criteria_pct": pass_pct_criterion,
        "criteria_sido": pass_sido_criterion,
    }
    out_path = base / f"results/analysis_{mode}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"\n분석 결과: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pilot", "full"], default="full")
    args = parser.parse_args()
    main(args.mode)
