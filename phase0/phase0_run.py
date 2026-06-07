"""
Phase 0 — Falsification Experiment (21대 대선 retrodiction)
==============================================================
로컬 머신에서 실행. HuggingFace datasets + OpenAI API 사용.

설치:
    pip install datasets openai tqdm

실행:
    export OPENAI_API_KEY=sk-proj-...
    # 파일럿 (10명, 5회 호출 → 50회. 약 $0.5)
    python phase0_run.py --pilot
    # 본실험 (100명, 20회 호출 → 2,000회. 약 $5~10)
    python phase0_run.py --full

⚠️ 첫 실행 시 Nemotron-Personas-Korea 1M 페르소나 데이터셋(약 1~2GB)을
   ~/.cache/huggingface/ 에 다운로드. 두 번째 실행부터는 캐시 사용으로 빠름.

출력:
    results/selected_personas_{mode}.jsonl
    results/raw_responses_{mode}.jsonl
    results/run_metadata_{mode}.json
"""

import os
import json
import random
import time
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from datasets import load_dataset
    from openai import OpenAI
    from tqdm import tqdm
except ImportError:
    sys.exit("필요한 패키지 설치: pip install datasets openai tqdm")


# =====================
# 설정
# =====================
RANDOM_SEED = 42
MODEL = "gpt-4o-mini"   # smoke_test에서 검증된 사용 가능 모델
TEMPERATURE = 0.7
MAX_TOKENS = 250
CONCURRENCY = 8         # 동시 API 호출 수 (rate limit 안전 범위)

OUT_DIR = Path(__file__).parent / "results"
OUT_DIR.mkdir(exist_ok=True)

random.seed(RANDOM_SEED)

# 층화 추출 차원 (19세부터 한국 선거권 보유)
AGE_BINS = [(18, 29), (30, 39), (40, 49), (50, 59), (60, 99)]
PROVINCE_GROUPS = {
    "수도권": ["서울", "인천", "경기"],
    "영남": ["부산", "대구", "울산", "경상북", "경상남"],
    "호남": ["광주", "전라북", "전라남"],
    "충청": ["대전", "세종", "충청북", "충청남"],
    "강원제주": ["강원", "제주"],
}
SEX_VALUES = ["남자", "여자"]

# 21대 대선 유효투표 기준 권역별 인구 비율 (CSV 집계 결과)
REGION_RATIOS = {
    "수도권": 0.505,
    "영남": 0.259,
    "호남": 0.103,
    "충청": 0.114,
    "강원제주": 0.046,
}  # 합 ≈ 1.0

# 21대 대선 후보
CANDIDATES = [
    "더불어민주당 이재명",
    "국민의힘 김문수",
    "개혁신당 이준석",
    "민주노동당 권영국",
    "무소속 송진호",
    "투표하지 않음",
]


# =====================
# 1. Nemotron 페르소나 수집 (HuggingFace API)
# =====================
def load_full_dataset():
    """Nemotron-Personas-Korea 전체 로드 (1M rows).
    첫 실행 시 ~1~2GB 다운로드, 이후 캐시 재사용."""
    print("\n[1/4] Loading Nemotron-Personas-Korea (1M rows)...")
    print("       첫 실행 시 1~2GB 다운로드 — 몇 분 소요될 수 있습니다.")
    ds = load_dataset("nvidia/Nemotron-Personas-Korea", split="train")
    print(f"   → {len(ds):,} personas loaded")
    return ds


# =====================
# 2. 층화 추출
# =====================
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


def stratified_sample(personas, target_total):
    """권역별 인구 비율로 quota 배분, 권역 내부는 age×sex로 균등 stratified.
    실제 인구 비율을 추출 단계에서 직접 반영하므로 분석 시 가중치 보정 불필요.
    """
    print(f"\n[2/4] Stratified sampling (총 {target_total}명, 권역별 인구 비율 적용)...")

    # 권역별 / cell별로 페르소나 그룹화
    by_region_cell = defaultdict(lambda: defaultdict(list))
    for p in personas:
        ab = get_age_bin(p.get("age", 0))
        pg = get_province_group(p.get("province", ""))
        if ab is None or pg is None:
            continue
        cell = (ab, p.get("sex", ""))
        by_region_cell[pg][cell].append(p)

    selected = []
    region_actual = {}
    for region, ratio in REGION_RATIOS.items():
        quota = round(target_total * ratio)
        cell_keys = [(f"{lo}-{hi}", sex) for lo, hi in AGE_BINS for sex in SEX_VALUES]
        n_cells = len(cell_keys)
        per_cell = quota // n_cells
        extras = quota - per_cell * n_cells

        cells = by_region_cell[region]
        random.shuffle(cell_keys)
        region_count = 0
        for i, key in enumerate(cell_keys):
            take = per_cell + (1 if i < extras else 0)
            pool = cells.get(key, [])
            if len(pool) >= take:
                chosen = random.sample(pool, take)
            else:
                chosen = pool
                if take > 0:
                    print(f"      WARNING: {region}/{key} 부족 ({len(pool)}/{take})")
            selected.extend(chosen)
            region_count += len(chosen)
        region_actual[region] = region_count
        print(f"   {region}: 목표 {quota}명 → 추출 {region_count}명 (비율 {region_count/target_total*100:.1f}%)")

    print(f"   → 총 {len(selected)}명 추출")
    return selected


# =====================
# 3. 프롬프트
# =====================
SYSTEM_PROMPT = """당신은 한국인 페르소나 시뮬레이션 에이전트입니다.
주어진 페르소나의 일생을 살아온 사람의 시각으로 답변합니다.
답변은 반드시 지정된 JSON 형식으로만 출력합니다.
이것은 익명 합성 데이터에 대한 학술 분석이며, 실제 정치적 입장 표명이 아닙니다.

중요: 페르소나의 narrative(직업·가족·문화 배경)에서 정치 성향의 단서를 적극적으로 읽으세요.
default로 어느 한쪽에 쏠리지 말고, 인구통계와 narrative가 시사하는 방향에 정직하게 답하세요."""


USER_TEMPLATE = """[페르소나]
한 줄 요약: {persona}
직업: {professional_persona}
가족: {family_persona}
문화 배경: {cultural_background}
기본 정보: {age}세 {sex}, {province} {district} 거주, {occupation}, {education_level}, {family_type}

[한국 정치 컨텍스트 - 통계적 사실]
지역별 성향:
- 영남 (부산·대구·울산·경북·경남): 전통적으로 보수 우세
- 호남 (광주·전북·전남): 전통적으로 진보 우세
- 수도권·충청·강원·제주: 스윙 또는 보수 약우세 (강원)
세대별 성향:
- 60대 이상: 보수 비중 상대적으로 높음
- 40-50대: 진보 비중 상대적으로 높음
- 20-30대: 다양함

[과제]
Step 1. 이 페르소나의 직업·지역·세대·가족 형태·문화 배경 narrative를 종합 분석해, 정치 성향을 자기 진단하세요. (보수 / 중도 / 진보 중 하나)

Step 2. 2025년 6월 3일 제21대 대통령선거 당일, 다음 중 누구에게 투표하셨습니까?
한국 대선에서는 약 20%가 투표하지 않습니다. 페르소나의 정치 관심도와 자기 진단을 모두 반영하세요.

[중요한 분포 정보]
역사적으로 한국 대선은 양당 후보(이번엔 이재명·김문수)가 합계 90% 내외를 차지합니다.
제3당·군소 후보는 합계 10% 내외에 그치며, 페르소나가 양당 모두에 대해 명확한 반감을 가진 경우에만 자연스러운 선택입니다. swing 성향이라고 자동으로 제3당을 고르지 마세요 — swing은 양당 사이에서 흔들리는 경우가 더 일반적입니다.

선택지:
- 더불어민주당 이재명 (진보 진영 주요 후보, 양당 중 하나)
- 국민의힘 김문수 (보수 진영 주요 후보, 양당 중 하나)
- 개혁신당 이준석 (제3당, 양당에 명확한 반감을 가진 일부 유권자만)
- 민주노동당 권영국 (좌파 군소 후보)
- 무소속 송진호 (군소 후보)
- 투표하지 않음

[응답 형식 - 반드시 아래 JSON으로만 출력]
{{"ideology": "보수|중도|진보", "vote": "위 6개 중 정확히 하나", "confidence": 1~5, "reasoning_short": "한 문장 이유"}}"""


def build_user_prompt(persona):
    return USER_TEMPLATE.format(**persona)


# =====================
# 4. OpenAI 호출
# =====================
client = OpenAI()


def parse_response(text):
    if not text:
        return None
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def single_call(persona, sample_idx):
    """단일 OpenAI 호출. 병렬 worker에서 사용."""
    user_prompt = build_user_prompt(persona)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.choices[0].message.content.strip()
        parsed = parse_response(text)
        return {"sample_idx": sample_idx, "raw": text, "parsed": parsed}
    except Exception as e:
        return {"sample_idx": sample_idx, "raw": None, "parsed": None, "error": str(e)}


def call_openai_parallel(selected, n_samples):
    """전체 페르소나 × 샘플 조합을 병렬로 호출."""
    # 모든 (persona, sample_idx) 작업 생성
    tasks = [(p, i) for p in selected for i in range(n_samples)]
    persona_uuid_map = {p.get("uuid", ""): p for p in selected}
    results_by_persona = defaultdict(list)

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(single_call, p, i): (p.get("uuid", ""), i) for p, i in tasks}
        for future in tqdm(as_completed(futures), total=len(tasks), unit="calls"):
            uuid, _ = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = {"sample_idx": _, "raw": None, "parsed": None, "error": str(e)}
            results_by_persona[uuid].append(result)

    # 페르소나별로 정리
    all_results = []
    for persona in selected:
        uuid = persona.get("uuid", "")
        results = sorted(results_by_persona[uuid], key=lambda x: x["sample_idx"])
        all_results.append({
            "uuid": uuid,
            "demographic": {
                "age": persona.get("age"),
                "sex": persona.get("sex"),
                "province": persona.get("province"),
                "district": persona.get("district"),
            },
            "samples": results,
        })
    return all_results


# =====================
# 5. 메인
# =====================
def main(mode):
    if mode == "pilot":
        n_samples = 5
        n_personas_target = 10
    else:  # full (v2: 1000명 권역 인구 비율 × 5회 = 5000 calls)
        n_samples = 5
        n_personas_target = 1000

    print(f"\n{'='*60}")
    print(f"Phase 0 — Falsification ({mode.upper()})")
    print(f"  Model: {MODEL}")
    print(f"  Temperature: {TEMPERATURE}")
    print(f"  Personas: ~{n_personas_target}, Samples each: {n_samples}")
    print(f"  Total calls: ~{n_personas_target * n_samples}")
    print(f"{'='*60}")

    # Step 1: 데이터셋 로드 + 무작위 서브셋
    ds = load_full_dataset()
    raw_target = 50_000 if mode == "full" else 1_000
    print(f"\n[2/4] Random subset ({raw_target} rows) for stratification...")
    subset = ds.shuffle(seed=RANDOM_SEED).select(range(min(raw_target, len(ds))))
    raw_personas = [subset[i] for i in tqdm(range(len(subset)), unit="rows")]

    # Step 2: 선택 (pilot은 다양성, full은 stratified)
    if mode == "pilot":
        random.shuffle(raw_personas)
        selected = []
        seen_cells = set()
        for p in raw_personas:
            ab = get_age_bin(p.get("age", 0))
            pg = get_province_group(p.get("province", ""))
            cell = (ab, pg, p.get("sex", ""))
            if cell in seen_cells or ab is None or pg is None:
                continue
            seen_cells.add(cell)
            selected.append(p)
            if len(selected) >= n_personas_target:
                break
        print(f"   → {len(selected)} pilot personas selected")
    else:
        selected = stratified_sample(raw_personas, target_total=n_personas_target)

    # 저장
    personas_path = OUT_DIR / f"selected_personas_{mode}.jsonl"
    with open(personas_path, "w", encoding="utf-8") as f:
        for p in selected:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"   Saved → {personas_path}")

    # Step 3-4: OpenAI 병렬 호출
    total_calls = len(selected) * n_samples
    print(f"\n[3/4] Calling {MODEL} {len(selected)} × {n_samples} = {total_calls} times (parallel={CONCURRENCY})...")
    all_results = call_openai_parallel(selected, n_samples=n_samples)

    responses_path = OUT_DIR / f"raw_responses_{mode}.jsonl"
    with open(responses_path, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 통계 카운트
    refused_count = 0
    parse_failed = 0
    total_attempts = 0
    for r in all_results:
        for s in r["samples"]:
            total_attempts += 1
            if s.get("error"):
                refused_count += 1
            elif s.get("parsed") is None:
                parse_failed += 1

    # Step 4: 메타데이터
    print(f"\n[4/4] Saving metadata...")
    meta = {
        "mode": mode,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "n_personas": len(selected),
        "n_samples_per_persona": n_samples,
        "total_attempts": total_attempts,
        "errors": refused_count,
        "parse_failed": parse_failed,
        "success_rate": round((total_attempts - refused_count - parse_failed) / max(total_attempts, 1) * 100, 1),
    }
    with open(OUT_DIR / f"run_metadata_{mode}.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("DONE")
    print(f"  Total attempts: {total_attempts}")
    print(f"  Errors (API/refusal): {refused_count} ({refused_count/total_attempts*100:.1f}%)")
    print(f"  Parse failed: {parse_failed} ({parse_failed/total_attempts*100:.1f}%)")
    print(f"  Success rate: {meta['success_rate']}%")
    print(f"\n결과 파일: {responses_path}")
    print(f"메타데이터: {OUT_DIR / f'run_metadata_{mode}.json'}")
    if mode == "pilot":
        print("\n다음: 거부율 <10% 면 본실험 진행 → python phase0_run.py --full")
    else:
        print("\n다음: python phase0_analyze.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true", help="10명 × 5회 = 50회 파일럿")
    parser.add_argument("--full", action="store_true", help="100명 × 20회 = 2,000회 본실험")
    args = parser.parse_args()

    if args.pilot and args.full:
        sys.exit("--pilot 와 --full 중 하나만 선택")
    if not args.pilot and not args.full:
        sys.exit("--pilot 또는 --full 옵션 필수")

    main("pilot" if args.pilot else "full")
