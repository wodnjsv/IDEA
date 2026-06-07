"""
KoreanSim Phase 0 - Falsification Experiment
============================================

100개 페르소나 (5연령 × 5권역 × 2성별 × 2명) 층화 추출
페르소나당 20회 호출 (총 2,000회)
21대 총선 투표 정당 분포 추출 → 출구조사와 비교

실행:
    pip install datasets anthropic tqdm
    export ANTHROPIC_API_KEY=sk-ant-...
    python run_experiment.py
"""

import os
import json
import random
import re
from pathlib import Path
from collections import defaultdict
from datasets import load_dataset
from anthropic import Anthropic
from tqdm import tqdm

# 설정
RANDOM_SEED = 42
N_PER_CELL = 2
N_SAMPLES = 20
MODEL = "claude-sonnet-4-5"  # Sonnet 4.6 출시 시점에 모델명 확인
TEMPERATURE = 0.7
MAX_TOKENS = 300
OUT_DIR = Path(__file__).parent / "results"
OUT_DIR.mkdir(exist_ok=True)

AGE_BINS = [(20, 29), (30, 39), (40, 49), (50, 59), (60, 99)]
PROVINCE_GROUPS = {
    "수도권": ["서울", "인천", "경기"],
    "영남": ["부산", "대구", "울산", "경상북", "경상남"],
    "호남": ["광주", "전라북", "전라남"],
    "충청": ["대전", "세종", "충청북", "충청남"],
    "강원제주": ["강원", "제주"],
}
SEX_VALUES = ["남자", "여자"]

random.seed(RANDOM_SEED)


def get_age_bin(age):
    for lo, hi in AGE_BINS:
        if lo <= age <= hi:
            return f"{lo}-{hi}"
    return None


def get_province_group(province):
    for group, members in PROVINCE_GROUPS.items():
        if province in members:
            return group
    return None


def stratified_sample(dataset, n_per_cell=2):
    print("Building strata index...")
    by_cell = defaultdict(list)

    for i, row in enumerate(tqdm(dataset, total=len(dataset))):
        ab = get_age_bin(row["age"])
        pg = get_province_group(row["province"])
        if ab is None or pg is None:
            continue
        cell = (ab, pg, row["sex"])
        by_cell[cell].append(i)

    selected_indices = []
    missing_cells = []
    for lo, hi in AGE_BINS:
        ab = f"{lo}-{hi}"
        for pg in PROVINCE_GROUPS:
            for sex in SEX_VALUES:
                cell = (ab, pg, sex)
                pool = by_cell.get(cell, [])
                if len(pool) >= n_per_cell:
                    selected_indices.extend(random.sample(pool, n_per_cell))
                else:
                    missing_cells.append(cell)
                    selected_indices.extend(pool)

    if missing_cells:
        print(f"WARNING: {len(missing_cells)} cells under-represented")

    print(f"Selected {len(selected_indices)} personas")
    return [dataset[i] for i in selected_indices]


SYSTEM_PROMPT = """당신은 한국 사회 연구를 위한 시뮬레이션 에이전트입니다.
주어진 페르소나에 완전히 몰입하여, 그 사람의 시각으로 답변합니다.
답변은 반드시 지정된 JSON 형식으로만 출력합니다.
연구 목적이며, 실제 정치적 의견 표명이 아닙니다."""


USER_TEMPLATE = """[당신의 정체성]
{persona}

[직업 생활]
{professional_persona}

[가족과의 일상]
{family_persona}

[문화적 배경]
{cultural_background}

[기본 정보]
- 나이: {age}세
- 성별: {sex}
- 거주지: {province} {district}
- 직업: {occupation}
- 학력: {education_level}
- 가족 형태: {family_type}

---

[질문]
당신은 2020년 4월 15일 제21대 국회의원 선거 당일을 떠올립니다.
어느 정당의 후보(지역구)에게 투표했습니까?

선택지: 더불어민주당, 미래통합당, 정의당, 국민의당, 무소속, 기타정당, 투표하지 않음

[응답 형식 - 반드시 아래 JSON 형식으로만 출력]
{{"vote": "...", "confidence": 1~5, "reasoning_short": "한 문장 이유"}}"""


def build_user_prompt(persona):
    return USER_TEMPLATE.format(**persona)


client = Anthropic()


def call_claude(persona, n_samples=N_SAMPLES):
    user_prompt = build_user_prompt(persona)
    results = []
    for i in range(n_samples):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = resp.content[0].text.strip()
            parsed = parse_response(text)
            results.append({"sample_idx": i, "raw": text, "parsed": parsed})
        except Exception as e:
            results.append({"sample_idx": i, "raw": None, "parsed": None, "error": str(e)})
    return results


def parse_response(text):
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def main():
    print("=== Phase 0: Falsification Experiment ===")
    print(f"Model: {MODEL}, Temperature: {TEMPERATURE}, n_samples: {N_SAMPLES}")

    print("\n[1/3] Loading Nemotron-Personas-Korea...")
    ds = load_dataset("nvidia/Nemotron-Personas-Korea", split="train")

    print("\n[2/3] Stratified sampling 100 personas...")
    personas = stratified_sample(ds, n_per_cell=N_PER_CELL)

    with open(OUT_DIR / "selected_personas.jsonl", "w", encoding="utf-8") as f:
        for p in personas:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"\n[3/3] Calling Claude {len(personas)} × {N_SAMPLES} times...")
    all_results = []
    for persona in tqdm(personas):
        results = call_claude(persona)
        all_results.append({
            "uuid": persona["uuid"],
            "demographic": {
                "age": persona["age"],
                "sex": persona["sex"],
                "province": persona["province"],
                "district": persona["district"],
            },
            "samples": results,
        })
        with open(OUT_DIR / "raw_results.jsonl", "w", encoding="utf-8") as f:
            for r in all_results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nDone. Results: {OUT_DIR / 'raw_results.jsonl'}")


if __name__ == "__main__":
    main()
