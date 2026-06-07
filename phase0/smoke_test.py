"""
Phase 0 Smoke Test — 본실험 전 환경 검증
==========================================
HuggingFace 스트리밍으로 1개 row + OpenAI 1회 호출만 수행. 시간 약 30초.
전체 데이터셋 다운로드는 안 함 (streaming=True 사용).

다음을 점검:
1. datasets 라이브러리 + 페르소나 1개 stream 정상인가
2. Nemotron 페르소나 필드 구조 일치 확인
3. OpenAI API 키 유효한가
4. 모델 ID gpt-5.4-mini 사용 가능한가
5. 응답 형식 JSON 파싱 성공하는가

사용법:
    export OPENAI_API_KEY=sk-...
    python smoke_test.py
"""

import os
import sys
import json
import re

try:
    from datasets import load_dataset
    from openai import OpenAI
except ImportError:
    sys.exit("pip install datasets openai")

# 사용할 모델 (실패 시 다른 후보 자동 시도)
MODEL_CANDIDATES = [
    "gpt-5.4-mini",  # 사용자 확정 (1순위)
    "gpt-5-mini",
    "gpt-4o-mini",
    "gpt-4o",
]

print("=" * 60)
print("Phase 0 Smoke Test")
print("=" * 60)

# Test 1: HuggingFace streaming
print("\n[1/4] HuggingFace 스트리밍 1개 페르소나 fetch...")
try:
    ds = load_dataset("nvidia/Nemotron-Personas-Korea", split="train", streaming=True)
    persona = next(iter(ds))
    print("   ✓ HF datasets 스트리밍 정상")
except Exception as e:
    sys.exit(f"   ✗ HF datasets 실패: {e}")

# Test 2: 필드 검증
print("\n[2/4] Nemotron 페르소나 필드 검증...")
required_fields = [
    "persona", "professional_persona", "family_persona", "cultural_background",
    "age", "sex", "province", "district", "occupation", "education_level", "family_type",
]
missing = [f for f in required_fields if f not in persona]
if missing:
    sys.exit(f"   ✗ 누락 필드: {missing}")
print(f"   ✓ 모든 필드 정상 ({len(required_fields)}개)")
print(f"   샘플: {persona['age']}세 {persona['sex']} / {persona['province']} {persona['district']} / {persona['occupation']}")

# Test 3: OpenAI API 키 + 모델
print("\n[3/4] OpenAI API 키 + 사용 가능한 모델 탐색...")
if not os.getenv("OPENAI_API_KEY"):
    sys.exit("   ✗ OPENAI_API_KEY 환경변수 없음")

client = OpenAI()
working_model = None

for model_id in MODEL_CANDIDATES:
    try:
        resp = client.chat.completions.create(
            model=model_id,
            max_tokens=20,
            messages=[{"role": "user", "content": "Hi"}],
        )
        working_model = model_id
        print(f"   ✓ 사용 가능: {model_id}")
        break
    except Exception as e:
        err = str(e)[:80]
        print(f"   ✗ {model_id}: {err}")

if not working_model:
    sys.exit("\n사용 가능한 모델 없음. OpenAI 콘솔에서 본인 계정의 모델 확인 후 phase0_run.py 수정.")

# Test 4: 실제 페르소나 + JSON 응답 1회
print(f"\n[4/4] 실제 페르소나로 1회 추론 + JSON 파싱 테스트 ({working_model})...")
prompt = f"""당신은 다음 인물입니다.
- 나이: {persona['age']}세
- 성별: {persona['sex']}
- 지역: {persona['province']} {persona['district']}
- 직업: {persona['occupation']}
- 페르소나: {persona['persona']}

[질문]
2025년 6월 3일 제21대 대통령선거에서 누구에게 투표했습니까?
선택지: 더불어민주당 이재명, 국민의힘 김문수, 개혁신당 이준석, 민주노동당 권영국, 무소속 송진호, 투표하지 않음

[응답 형식 - 반드시 JSON]
{{"vote": "...", "confidence": 1~5, "reasoning_short": "한 문장"}}"""

try:
    resp = client.chat.completions.create(
        model=working_model,
        temperature=0.7,
        max_tokens=200,
        messages=[
            {"role": "system", "content": "주어진 페르소나로 시뮬레이션 응답. JSON으로만."},
            {"role": "user", "content": prompt},
        ],
    )
    text = resp.choices[0].message.content.strip()
    print(f"   응답 원문:\n   {text}")
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        parsed = json.loads(match.group())
        print(f"\n   ✓ JSON 파싱 성공: vote={parsed.get('vote')}, conf={parsed.get('confidence')}")
    else:
        print(f"\n   ⚠️ JSON 파싱 실패 — 프롬프트 강화 필요할 수 있음")
except Exception as e:
    sys.exit(f"   ✗ 추론 실패: {e}")

print("\n" + "=" * 60)
print(f"✓ 모두 통과. 사용 가능한 모델: {working_model}")
print(f"\n다음 단계:")
print(f"1. phase0_run.py 44번째 줄 MODEL을 '{working_model}'로 수정")
print(f"2. python phase0_run.py --pilot 로 파일럿 진행")
print("=" * 60)
