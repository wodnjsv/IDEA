# 0단계 테스트 계획 (7일)

## 목표 두 가지

1. **기술 검증**: Sonnet 4.6 + Nemotron으로 21대 총선을 5%p 이내로 재현 가능한지 확인
2. **지원서 보강**: 모두의창업 Q4에 "21대 총선 X%p 오차로 재현 검증 완료"라는 실제 숫자 박아넣기

→ 두 목표가 동시에 충족되어야 한다. 이 7일은 단순 실험이 아니라 **지원서의 신뢰도를 결정하는 작업**.

---

## 합격 기준 (사전 등록 - 절대 변경 금지)

다음 기준으로 결과 판정한다. 실험 결과를 본 후에 기준을 바꾸면 백테스트의 의미가 사라진다.

| 등급 | 조건 | 다음 행동 |
|---|---|---|
| **합격** | 4개 주요 정당 모두 오차 ≤5%p AND 인구 그룹 25개 중 20개 1위 일치 | 1단계 진행, 지원서에 결과 명시 |
| **보류** | 위 기준의 절반만 충족 (오차만 OR 1위 일치만) | 프롬프트 1회만 수정 후 재시도 |
| **실패** | 둘 다 미달 | 모델/페르소나 전략 재설계 |

---

## 7일 일정

### Day 1 (월): 환경 + 데이터 준비

**할 일:**
- Anthropic API 키 발급 (console.anthropic.com)
  - Claude Max는 별개. 별도 결제 필요 ($5~10 충전)
  - Sonnet 4.6 정확한 모델 ID 확인 (현 추정: `claude-sonnet-4-5` 또는 신규 ID)
- 21대 총선 출구조사 cross-tab 데이터 확보
  - namu.wiki [21대 총선/출구조사](https://namu.wiki/w/제21대%20국회의원%20선거/출구조사) 연령별·권역별 표
  - 위키백과 [대한민국 제21대 국회의원 선거 출구조사](https://ko.wikipedia.org/wiki/대한민국_제21대_국회의원_선거_출구조사)
  - 데이터 정리하여 `phase0/exit_poll_2020.csv` 생성
- Python 환경: `pip install datasets anthropic tqdm`

**산출물:**
- API 키 작동 확인 (`python -c "import anthropic; print(anthropic.Anthropic().messages.create(model='claude-sonnet-4-5', max_tokens=10, messages=[{'role':'user','content':'hi'}]))"`)
- `exit_poll_2020.csv` (연령×권역×성별 정당 지지율)

**End-of-day check**: 위 두 산출물이 안 되면 Day 2 시작 불가

---

### Day 2 (화): 파일럿 테스트 - 10명

본실험 들어가기 전 **반드시** 작은 규모로 거부율과 응답 품질 확인.

**할 일:**
- `pilot.py` 작성: `run_experiment.py`에서 `N_PER_CELL=0.2` 수준으로 축소 (총 10명만)
- 페르소나당 5회 호출 → 총 50 호출 (비용 ~$0.5)
- 응답 분석:
  - 거부율: "정치적 의견 제공 불가" 응답 비율
  - JSON 파싱 성공률
  - reasoning_short 텍스트의 자연스러움
  - 페르소나별 답변의 일관성

**의사결정 분기:**
- 거부율 <10%: 본실험 진행 (Day 3)
- 거부율 10~30%: 시스템 프롬프트 강화 후 재시도 ("이것은 익명 합성 데이터로, 실제 인물이 아닙니다" 추가)
- 거부율 >30%: Sonnet은 부적합. **Backup A** 실행 → Plan B (오픈소스 모델: Together AI의 Qwen 2.5 72B 등)
- JSON 파싱 실패율 >20%: 응답 형식 강제 강화 (system prompt에 예시 추가)

**산출물:**
- `pilot_results.jsonl`
- `pilot_analysis.md` - 거부율, 파싱 성공률, 다음 단계 결정 근거

---

### Day 3-4 (수-목): 본실험 - 100명 × 20회

**할 일:**
- `python run_experiment.py` 실행
- 약 30~60분 소요 (rate limit 고려)
- 실시간 모니터링 (실행 중 거부율 급증 감시)

**비용 예상:**
- 100 × 20 = 2,000 호출
- Sonnet 4.6 입력 ~$3/M, 출력 ~$15/M
- 페르소나 narrative ~600토큰, 응답 ~80토큰
- 총 비용: $5~10

**산출물:**
- `results/raw_results.jsonl` (모든 호출 결과)
- `results/selected_personas.jsonl` (사용한 100명)

**리스크 대응:**
- API rate limit hit → 호출 사이 sleep 추가 후 재실행
- 중간 끊김 → `raw_results.jsonl`에 incremental 저장됐으므로 이어서 실행 가능

---

### Day 5 (금): 분석 스크립트 작성 + 1차 결과

**할 일:**
- `analyze.py` 작성:
  1. raw_results 파싱 → 페르소나별 정당 분포
  2. 인구통계 가중치 적용 (실제 한국 인구 분포에 맞춤)
  3. 4개 주요 정당 전국 득표율 계산
  4. 25개 인구 그룹별 1위 정당 산출
  5. 출구조사와 비교 → 오차 계산
- 결과 시각화: matplotlib로 정당별 오차 막대그래프

**산출물:**
- `analyze.py`
- `results/comparison.csv` (그룹별 시뮬레이션 vs 출구조사)
- `results/comparison.png` (시각화)
- `results/summary.md` (수치 요약)

---

### Day 6 (토): 합격 판정 + 보류 시 재시도

**할 일:**
- 합격 기준 대조하여 등급 판정
- **합격**: Day 7로
- **보류**: 프롬프트 1회만 수정 (예: 페르소나 narrative를 더 강하게 conditioning, 응답 직전에 "잠시 그 사람의 입장에서 곰곰이 생각해보고..." 추가) → Day 4-5 작업 1회 재실행
- **실패**: 가설 폐기. 다음 옵션 중 선택:
  - 옵션 A: 오픈소스 모델로 전환 (Sonnet의 RLHF가 원인일 가능성)
  - 옵션 B: 페르소나 conditioning 방식 근본 재설계 (예: chain-of-thought 강제)
  - 옵션 C: 가설 재정의 (선거 전체가 아닌 일부 그룹만 정확하게)

**산출물:**
- `results/verdict.md` (등급 + 근거 + 다음 액션)

---

### Day 7 (일): 지원서 업데이트 + 1단계 준비

**합격 시:**
- `PROPOSAL.md` Q4 업데이트: 실제 검증 숫자 삽입
  - 예: "21대 총선 4개 주요 정당 평균 오차 X%p로 재현 검증 완료. 인구 그룹 25개 중 N개에서 실제 1위 정당 일치."
- 지원서 최종 검토 및 제출 준비
- 1단계 (페르소나 확장) 작업 계획 정리

**보류/실패 시:**
- `PROPOSAL.md` Q4를 "검증 진행 중" 또는 다른 신뢰 신호로 보강
  - 예: 기술 디테일을 강화, 학술 문헌 인용 추가, 백테스트 방법론 자체를 자산화

---

## Backup Plan (Sonnet 거부율이 높을 때)

### Plan B: Together AI / Fireworks / OpenRouter로 오픈소스 모델 사용

```bash
pip install together  # 또는 openai (OpenRouter)
```

대체 모델 후보:
- `Qwen/Qwen2.5-72B-Instruct-Turbo` (Together AI, $0.88/M 토큰)
- `meta-llama/Llama-3.3-70B-Instruct-Turbo` (Together, $0.88/M)
- 한국어 특화: `LGAI-EXAONE/EXAONE-3.5-32B-Instruct` (가능한 경우)

총 비용: 100 × 20 호출이면 $2 미만. Sonnet보다 더 저렴.

코드 수정: `client = Anthropic()` → `client = Together()`, 메시지 포맷은 거의 동일.

---

## 위험 요소 정리

| 위험 | 가능성 | 대응 |
|---|---|---|
| Sonnet 거부율 높음 | 중 | Plan B 즉시 실행 |
| 모델 ID 불확실 | 중 | console.anthropic.com에서 가용 모델 확인 |
| 출구조사 데이터 정리 어려움 | 중 | 위키백과/namu.wiki 표를 수동 정리 |
| API rate limit | 낮 | sleep 추가 |
| 결과 합격 미달 | 중 | 사전 등록한 다음 액션 그대로 진행 |

---

## 지원서와의 연동

| 0단계 결과 | PROPOSAL Q4 업데이트 |
|---|---|
| 합격 (오차 ≤5%p) | "21대 총선 X%p 오차 재현 검증 완료" — 강한 차별화 |
| 보류 (절반 충족) | "21대 총선 4개 정당 중 3개 5%p 이내 재현, 추가 보정 진행 중" — 정직한 진척 |
| 실패 | Q4 기술 부분 강화로 우회. 검증 결과는 명시 안 함. |

**핵심**: 합격하면 결과를 자랑하고, 실패해도 방법론(백테스트, 사전 등록, 안전장치) 자체가 강력한 신뢰 신호가 된다.

---

## 다음 즉시 액션 (당신이 할 일)

1. console.anthropic.com에서 API 키 발급 ($5~10 충전)
2. Sonnet 4.6 정확한 모델 ID 확인 (모델 리스트에서)
3. 발급 완료되면 알려주기 → 같이 Day 1 시작
