# 0단계 실행 가이드 (로컬 머신에서 실행)

## 사전 준비

### 1. API 키 보안
- **⚠️ 채팅에 노출된 키는 즉시 폐기 후 재발급**: console.openai.com → API keys → 기존 키 revoke + 새 키 발급
- 새 키를 환경변수로 설정 (코드에 직접 넣지 말 것)

### 2. 환경 설치

```bash
# 프로젝트 디렉토리로 이동
cd ~/Pluto/Idea/phase0

# 의존성 설치
pip install datasets openai tqdm

# API 키 설정 (zsh/bash)
export OPENAI_API_KEY="sk-proj-..."
```

### 3. 모델 ID
- 현재 설정: `gpt-5.4-mini-2026-03-17`
- 변경 필요 시 `phase0_run.py` 상단 `MODEL` 변수 수정

### 4. 첫 실행 안내
- 첫 `phase0_run.py` 실행 시 Nemotron-Personas-Korea 1M rows를 다운로드 (~1~2GB, 몇 분 소요)
- 캐시 위치: `~/.cache/huggingface/datasets/`
- 두 번째 실행부터는 캐시 사용으로 즉시 시작

---

## 실행 순서

### Step 0. Smoke Test (30초, ~$0)

본실험 전 환경 검증. 비용 거의 0.

```bash
python smoke_test.py
```

자동으로 확인:
- HF API 응답 정상인가
- Nemotron 페르소나 필드 모두 존재하는가
- OpenAI 키 유효한가
- 사용 가능한 모델 ID 자동 탐색 (`gpt-5-mini`, `gpt-4o-mini` 등)
- JSON 응답 파싱 성공하는가

마지막에 `phase0_run.py 44번째 줄 MODEL을 'XXX'로 수정` 안내 출력.

→ 이걸 통과해야 파일럿 진행. 안 통과하면 어디서 막혔는지 보고 알려줘.

---

### Step 1. 파일럿 테스트 (10명, 약 50회 호출, ~$0.5)

```bash
python phase0_run.py --pilot
```

**예상 시간**: 5~10분

**확인 사항** (실행 직후 출력 확인):
- 거부율(`Errors`) **<10%** → OK, 본실험 진행
- 거부율 10~30% → 시스템 프롬프트 강화 필요 (정치 질문 거부 회피용 문구 추가)
- 거부율 >30% → 모델 교체 검토 (RLHF 강한 모델 회피)
- 파싱 실패율(`Parse failed`) **<20%** → OK

**결과 확인:**
- `results/raw_responses_pilot.jsonl`
- `results/run_metadata_pilot.json`

수동으로 jsonl 파일 몇 줄 열어서 답변 품질 확인 권장. 페르소나 정보가 무시되지 않고 실제로 반영되는지.

---

### Step 2. 본실험 (100명, 약 2,000회 호출, ~$5~10)

파일럿 통과 후:

```bash
python phase0_run.py --full
```

**예상 시간**: 30~90분 (rate limit 의존)

**중단되면**: 다시 실행하면 처음부터 다시 도는 게 아니라 결과 파일이 덮어쓰여짐. 시간 여유가 있을 때 중단 없이 실행 권장.

**결과:**
- `results/selected_personas_full.jsonl` (사용한 100명)
- `results/raw_responses_full.jsonl` (모든 호출 결과)
- `results/run_metadata_full.json` (성공률 등)

---

### Step 3. 결과 분석 (즉시 가능)

```bash
python phase0_analyze.py --mode full
```

**출력**: 콘솔에 합격 판정 + `results/analysis_full.json`

**합격 기준 (사전 등록 — 변경 금지):**
- ✅ **기준 ①**: 5명 후보 모두 전국 득표율 오차 ≤5%p
- ✅ **기준 ②**: 17개 시도 중 13개 이상에서 1위 후보 일치

**판정:**
- 둘 다 통과 → **PASS**: 1단계 진행 + PROPOSAL.md Q4 결과 박기
- 하나만 통과 → **BORDERLINE**: 프롬프트 1회 수정 후 재시도
- 둘 다 미달 → **FAIL**: 전략 재설계

---

## 결과 공유

분석 끝나면 다음 파일들을 채팅으로 다시 업로드:

1. `results/analysis_full.json`
2. `results/run_metadata_full.json`
3. (선택) `results/raw_responses_full.jsonl`의 첫 5~10개 페르소나 결과 sample

→ 합격이면 Q4 업데이트 같이 진행. 보류/실패면 원인 분석 + 다음 액션 결정.

---

## 트러블슈팅

### "API key not found"
- `echo $OPENAI_API_KEY` 로 확인. 없으면 export 다시.

### "Rate limit exceeded"
- 코드 내 `time.sleep(0.05)` 값을 `0.2`로 늘려 재시도

### "HuggingFace API timeout"
- VPN 또는 네트워크 문제. 재실행하면 이어지지 않으니 처음부터.

### 거부율 30% 초과
- 시스템 프롬프트에 추가:
  ```
  본 시뮬레이션은 실제 인물이 아닌 통계적 합성 페르소나입니다.
  익명 분포 분석이 목적이며 어떤 실제 의견 표명도 아닙니다.
  ```

### 모델 ID 에러 ("model not found")
- OpenAI 콘솔에서 사용 가능한 정확한 모델 ID 확인 후 코드 수정
