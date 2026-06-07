"""21대 대선 결과 CSV → 정답지 (전국 + 시도별 득표율)"""
import csv
import json
from collections import defaultdict

CSV_PATH = '/sessions/trusting-zen-gates/mnt/uploads/중앙선거관리위원회_대통령선거 개표결과_20250603.csv'

CANDIDATES = [
    '더불어민주당 이재명',
    '국민의힘 김문수',
    '개혁신당 이준석',
    '민주노동당 권영국',
    '무소속 송진호',
]

# 시도별 집계
sido_results = defaultdict(lambda: defaultdict(int))
sido_total = defaultdict(int)
national = defaultdict(int)

with open(CSV_PATH, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        sido = row['시도명']
        candidate = row['후보자']
        try:
            votes = int(row['득표수'])
        except (ValueError, TypeError):
            continue
        if candidate in CANDIDATES:
            sido_results[sido][candidate] += votes
            national[candidate] += votes

# 시도별 득표율
sido_pct = {}
for sido, cand_votes in sido_results.items():
    total = sum(cand_votes.values())
    sido_total[sido] = total
    sido_pct[sido] = {c: round(cand_votes[c] / total * 100, 2) for c in CANDIDATES}

# 전국 득표율
national_total = sum(national.values())
national_pct = {c: round(national[c] / national_total * 100, 2) for c in CANDIDATES}

# 시도별 1위 후보
sido_winner = {sido: max(pcts.items(), key=lambda x: x[1])[0] for sido, pcts in sido_pct.items()}

# 저장
ground_truth = {
    'election': '21대 대통령선거',
    'date': '2025-06-03',
    'candidates': CANDIDATES,
    'national_total_votes': national_total,
    'national_pct': national_pct,
    'sido_pct': sido_pct,
    'sido_winner': sido_winner,
}

with open('/sessions/trusting-zen-gates/mnt/Pluto/Idea/phase0/data/ground_truth_2025.json', 'w', encoding='utf-8') as f:
    json.dump(ground_truth, f, ensure_ascii=False, indent=2)

# 출력
print('=== 21대 대선 전국 득표율 ===')
for c, p in sorted(national_pct.items(), key=lambda x: -x[1]):
    print(f'  {c}: {p:.2f}%')
print(f'  총 유효표: {national_total:,}')
print()
print('=== 17개 시도별 1위 후보 ===')
for sido in sorted(sido_winner.keys()):
    winner = sido_winner[sido].split()[-1]  # 이재명, 김문수 등
    pct = sido_pct[sido][sido_winner[sido]]
    print(f'  {sido}: {winner} ({pct:.1f}%)')

print()
print('정답지 저장 완료: data/ground_truth_2025.json')

