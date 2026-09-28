# ISS-032: 실험 캐시의 설정 식별 누락과 채점 API 경계

- **상태**: ANALYZED
- **유형**: 코드 | 방법론
- **심각도**: P1
- **발견**: 2026-09-22, 현행 코드 읽기 전용 조사
- **관련**: ISS-002, ISS-012, ISS-014, T1/T4, EXP-008~010

## 문제
통합 엔진 계획과 달리 일부 실험 스크립트의 캐시는 모델·프롬프트 변경을 식별하지 않는다. 또한 일부 scorer는 외부 API를 호출하므로 이름만 보고 $0 재채점으로 취급할 수 없다.

### 소스 근거와 실패 조건
1. `scripts/exp010_run.py`의 `done_keys`는 dist/text 존재와 task key로 완료를 판정한다. 작업 key는 item/arm/form/pid 기반이며 모델·전체 프롬프트 해시가 없다. `--model`은 바꿀 수 있지만 같은 track/channel의 출력 파일은 같다. 기존 결과가 있는 상태에서 모델을 바꾸면 기존 성공을 건너뛰고, 일부만 성공했던 파일에는 다른 모델 응답이 추가될 수 있다. `exp008_run.py`, `exp009_kr_run.py`, `exp009_us_run.py`에도 유사한 task key 재개 구조가 있다. 이는 코드 경로에서 확인한 위험이며 실제 혼합 발생을 이번에 입증한 것은 아니다.
2. `scripts/exp010_kr_score.py`의 `ssr_embed_once`는 `text-embedding-3-small` API를 호출하며 파일 최상위 실행부에서 호출한다(import 때도 실행될 수 있음). 따라서 해당 scorer 실행은 순수 오프라인 집계가 아니다. 이번 조사에서는 실행하지 않았다.
3. `exp011_pre_donor_pool.py`, `exp011_pre_sealed_regions.py` 등은 `C:\dev\idea` 고정 경로를 가진다. 여러 실험 runner는 `ROOT/data`를 직접 사용해 `IDEA_DATA_DIR`을 따르지 않는다. ISS-002 레지스트리의 존재와 전체 실험의 레지스트리 적용을 구별해야 한다.

## 분석
| 옵션 | 장점 | 단점 | 근거 |
|---|---|---|---|
| 실행마다 수동으로 별도 출력 위치·코드 버전 보관 | 즉시 가능 | 실수 방지 강제 없음 | [중] 운영 통제 |
| 모델/프롬프트/설정 fingerprint 검증, 임베딩 생성 단계·캐시 분리, registry 경로 통일 | 재개 혼합 차단·비용 경계 명확 | 관련 EXP 재현성 감사와 코드 테스트 필요 | [강] 코드 대조 |

## 결정
인간 결정 없음. 후자 구현을 제안한다. 이번 인계 요청은 분석·문서화 범위이므로 실행 코드와 기존 캐시를 수정하지 않는다.

## 구현

- 인계 분석·이슈 기록 커밋: `d80350b` (문서만; 실행 코드 수정 아님).
- 인계 동작구조 문서와 빠른 참고 문서에 실행 전 확인 사항 기록.
- 코드 수정 미착수. 분석 기준 커밋 `2e4f3d681f9fe8994b0dc126e00beeee080ac11b`.

## 검증
정적 소스 대조만 수행. 모델 호출·임베딩 호출·캐시 재채점·혼합 재현 실행 없음. 테스트를 통과한 수정으로 오인하지 말 것.

### 조건 식별의 추가 정적 관찰
`scripts/exp012_run.py`는 임의 `--arms` 문자열을 받고 `_3` 접미사 후보축소를 지원하지만 이념 삭제는 `arm == "D2"`에서만 수행한다. 향후 D2_3을 사용하면 이름에서 기대하는 라벨 제거가 적용되지 않는다. 기존 실행 기록은 D1/D2/D1_3이므로 현재 결과 오염의 증거로 확대하지 않는다. 새 암 도입 전 허용 조건과 구성 검증이 필요하다.

### 추기 (2026-09-23, 전체 저장소 팔로업 리뷰)
- 출처: 2026-09-23, 전체 저장소 팔로업 리뷰(Claude 단일 모델 워크플로 — 읽기 전용 교차대조, 교차모델 검토 전). 기준 HEAD `33c73c5`.
- 범위: 정적 소스 대조와 저장 jsonl 필드 계수만 했다. 스크립트 import·실행, 모델·임베딩 호출, 재채점은 없었다. 상태는 ANALYZED를 유지한다.

1. **import 시점에 외부 API를 호출하는 스크립트(#2 범위 확장).** #2의 `exp010_kr_score.py` 외에 아래 4개도 `__main__` 보호 없이 모듈 최상위 실행부에서 OpenAI를 호출한다. 그래서 import만 해도 과금 호출이 날 수 있다. 이 스크립트로 "재채점"하면 임베딩·LLM 채점을 새로 받게 되므로, 저장값 집계가 아니라 새 측정이다(규칙 6 EXP 카드 대상, 결과 동일성 비보장).
   - `scripts/exp010_kr_individual.py:100`: 최상위의 `channels = {... load_ssr()}`가 `load_ssr`(:69-)를 실행하고, 그 안에서 `make_client("openai")`(:72)와 `text-embedding-3-small`(:77)을 캐시 없이 호출한다.
   - `scripts/exp010_kr_leveled.py:115`: 최상위 `ssr = load_ssr_tau()`가 :72 `make_client`와 :77 임베딩을 호출한다.
   - `scripts/exp010_meter_compare.py`: :68에서 최상위 `make_client`를 만들고, :75 임베딩(`embed`, 최상위 :89 등에서 호출)과 :134의 `gpt-4o-mini-2024-07-18` 채점자 chat(최상위 `ThreadPoolExecutor` :164에서 실행)을 호출한다.
   - `scripts/exp010_pre_embed.py:24`(`make_client`), `:31`(임베딩).
   - `scripts/exp010_ssr_rate.py`는 `__main__` 보호(:120)가 있다. 다만 실행하면 채점 캐시에 없는 키에 대해 chat을 호출한다.
   - EXP-010 카드는 individual($0.02, :118)과 meter_compare($0.20, :83)의 비용을 적어 API 사용을 간접적으로 드러낸다. 그러나 "캐시 재채점과 다르다"는 경고는 없다.
2. **`exp010_ssr_rate` 채점 캐시에 식별 정보가 없다.** `scripts/exp010_ssr_rate.py:57-66`은 출력 파일의 `key`만으로 완료를 판정한다. 채점자 모델은 `LC.MODELS["gpt-4o-mini"]`로 고정(:67)돼 있고, 출력 행에는 채점자 모델·프롬프트 식별이 없다. 실제로 저장된 `data/exp010/us_ssr_scored.jsonl` 9,119행에는 `model` 키가 하나도 없다. 채점자 SYS 프롬프트를 바꾼 뒤 재개하면 기존 채점과 조용히 섞이고, 사후에도 탐지할 수 없다.
3. **채점기가 raw의 `model` 필드를 검사하지 않는다.** `scripts/score_ab.py:59`만 암별 `model`을 모아 혼재를 경고한다(ISS-019). 다음 7개 채점기는 raw의 `model` 필드를 읽지 않는다(grep 0건): `exp008_score.py`, `exp009_kr_score.py`, `exp009_us_score.py`, `exp010_kr_score.py`, `exp010_us_score.py`, `exp012_score.py`, `score_t3.py`. 러너 재개로 혼합이 생겨도 채점 단계에서 걸러지지 않는다.
4. **`__main__` 보호 부재.** `scripts/*.py` 42개 중 26개에 `__main__` 문자열이 없다(grep 계수). `민심테스트/scripts/*.py` 7개는 모두 보호가 있다. 26개 중 외부 API 호출 코드를 가진 것은 위 4개와 `exp010_kr_score.py`를 더한 5개다. 26개 목록:
   - exp008: `exp008_prepare`, `exp008_score`
   - exp009: `exp009_freeze_pairs`, `exp009_kgss_placebo`, `exp009_kr_exclude`, `exp009_kr_prep`, `exp009_kr_score`, `exp009_screen_us`, `exp009_us_prep`, `exp009_us_score`
   - exp010: `exp010_kr_individual`, `exp010_kr_leveled`, `exp010_kr_score`, `exp010_level_fidelity`, `exp010_meter_compare`, `exp010_plot_candidates`, `exp010_plot_kr`, `exp010_pre_embed`, `exp010_us_score`
   - exp011: `exp011_pre_donor_pool`, `exp011_pre_entropy`, `exp011_pre_fusion_test`, `exp011_pre_mde`, `exp011_pre_sealed_regions`
   - 기타: `exp012_score`, `selftest_llm_client`
5. **존재하지 않는 오케스트레이터 참조와 느슨한 체인 임계.**
   - EXP-010:28은 `scripts/exp010_orchestrate.ps1`(EXP-009 미국장 완료 감지 → 자동 채점 → EXP-010 미국장 발사)을 실행 하네스로 적었다. 그러나 이 파일은 git 이력 전체에 없다(`git log --all -- scripts/exp010_orchestrate.ps1` 0건).
   - 실제 체인은 `exp010_us_chain.ps1`·`exp010_kr_chain.ps1`·`exp010_ssr_chain.ps1`이다. 셋 다 `Set-Location C:\dev\idea`(:2)에 고정된 Windows 전용이고, us·ssr 체인은 Win32_Process에도 의존한다(→ ISS-039).
   - 완료 임계도 느슨하다. `exp010_us_chain.ps1:11`은 `$ok -ge 45200`(총 45,360), `exp010_ssr_chain.ps1:13`은 `$n -ge 9050`(총 9,120)이라 미완료 상태에서도 채점으로 넘어갈 수 있다.
   - 실제 저장값은 `data/exp009/us_raw.jsonl` 유효 고유 키 45,360, `data/exp010/us_ssr_raw.jsonl` text 행 9,119로, 피해는 없었다.
6. **부속 분석의 산출물 부재.**
   - `exp010_kr_leveled.py`·`exp010_kr_individual.py`·`exp010_level_fidelity.py`는 결과 JSON을 쓰지 않는다(파일 쓰기 코드 0건).
   - `exp010_level_fidelity.py:57-63`은 kr_leveled의 콘솔 출력값을 `LEVELED` 상수로 하드코딩한다. :50-54의 `kr_leveled.json` 로드는 파일이 없어 쓰이지 않는 죽은 코드다.
   - 따라서 EXP-010 부속 검증 3·4 수치 일부는 저장 산출물과 대조할 수 없다.
7. **과거 캐시의 모델 혼합 여부(점검 결과).** task-key 재개 러너(#1)의 저장 raw 7종에서 레코드별 `model` 값을 계수했다. 각 파일은 단일 모델이다.

   | 파일 | 행 수 | model |
   |---|---|---|
   | `data/exp008/raw.jsonl` | 14,236 | `meta/llama-3.1-70b-instruct` |
   | `data/exp009/kr_raw.jsonl` | 25,200 | `gpt-4o-mini-2024-07-18` |
   | `data/exp009/us_raw.jsonl` | 45,897 | `meta/llama-3.2-90b-vision-instruct` |
   | `data/exp010/kr_dist_raw.jsonl` | 5,400 | `gpt-4o-mini-2024-07-18` |
   | `data/exp010/kr_ssr_raw.jsonl` | 3,600 | `gpt-4o-mini-2024-07-18` |
   | `data/exp010/us_dist_raw.jsonl` | 9,120 | `meta/llama-3.2-90b-vision-instruct` |
   | `data/exp010/us_ssr_raw.jsonl` | 9,133 | `meta/llama-3.2-90b-vision-instruct` |

   참고로 `data/exp012/raw.jsonl` 3,000행도 gpt-4o-mini 단일이다. 따라서 **저장 캐시에 과거 모델 혼합은 없었다.**
   - 검증 방법: 각 jsonl을 한 줄씩 읽어 `model` 키 값을 계수했다. 모델 호출과 채점기 실행은 하지 않았다.
   - 한계 (a): 프롬프트 변경 혼합은 레코드에 프롬프트 해시가 없어 같은 방법으로 탐지할 수 없다.
   - 한계 (b): `data/t3/raw_{A..E}.jsonl`(gpt 원판)은 레코드에 `model` 필드가 없어 파일명 규약(태그 없음 = gpt-4o-mini, ISS-019)으로만 식별된다.
   - 한계 (c): `data/t3/raw_{B,D2A,D2B}_llama-3.1-70b.jsonl`의 `model` 없는 행(189·173·143)은 `error` 키만 있는 오류 행이다.
- 관련: 410 즉시 정지와 모델 태그 검증(ISS-024 옵션 B)은 이 카드의 fingerprint 검증과 같은 공통 러너층에서 설계할 수 있다. Windows 경로와 체인은 ISS-039에서 다룬다.
- 제안(에이전트, 인간 결정 대기): 공통 러너층에 다음을 둔다. (i) 모델 id·프롬프트 해시·코드 커밋 fingerprint를 재개 키와 레코드에 기록. (ii) 채점기 입력 단계에서 model·fingerprint 단일성을 assert. (iii) API를 호출하는 분석 스크립트에 `__main__` 보호를 넣고 임베딩 캐시를 분리. (iv) EXP-010:28의 오케스트레이터 참조를 append로 정정. `src/`·러너 변경은 비자명 변경이므로 착수 전 설계 감사, 결과 감사, 교차모델 검토(ISS-026)를 거친다.
