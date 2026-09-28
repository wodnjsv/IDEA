# ISS-039: macOS 이관 후 재현 환경 공백 — NFD 경로 중복·파이썬 의존성·원자료 부재·OS 고정 경로

- **상태**: ANALYZED
- **유형**: 코드 | 데이터
- **심각도**: P2
- **발견**: 2026-09-23, 전체 저장소 팔로업 리뷰(Claude 단일 모델 워크플로 — 읽기 전용 교차대조, 교차모델 검토 전)
- **관련**: ISS-002(DECIDED — 결정 2 "경로 해석은 한 곳, 절대경로 금지"), ISS-031(인계서 서술 시점. 같은 리뷰의 추기 6이 `05_자료지도.md:52` 오기를 이 카드로 넘김), ISS-032(#3 `C:\dev\idea` 고정·`ROOT/data` 직접 사용. 같은 리뷰의 추기 `:59`가 ps1 체인의 Windows 전용을 적었고 `:83`이 Windows 경로·체인을 이 카드로 넘김), ISS-034(같은 리뷰의 거버넌스 카드 — §4 KGSS 배치 `.gitignore` 틈, §5 신청서 PDF와 그 NFD 이중 경로), ISS-037(T4 `pyproject`·`tests/` 미착수, `:44` 실행 환경), ISS-038(W1-2 pyproject 미이행 일정), 이 카드를 참조하는 같은 리뷰의 카드·추기(행 번호는 미커밋 작업본 기준) — ISS-024(추기 `:55` ps1 스모크 게이트 Windows 전용), ISS-029(추기 3: EXP-016 부분 캐시와 `data/minsim`이 원 기기에만 있음), ISS-033(`:142` 뱅크 v2 재빌드에 센서스 원자료 필요), ISS-035(`:144` numpy 부재로 채점기 미실행), ISS-040(`:184` selftest의 이 Mac 실행 가능 여부 — §2가 답함), EXP-011(`:5`·§8 `:109` "KGSS 0단계 지금 착수 가능"), EXP-013(KGSS 원자료 ID 재결합), `docs/프로젝트_인계/02_동작구조.md:65,262-270`, `docs/프로젝트_인계/04_판단기준과_남은과제.md:89`, `docs/프로젝트_인계/05_자료지도.md:52`, `docs/2_전략기획/구현계획_v1.md:31`, `CLAUDE.md:7`. **중복 범위**: KGSS 배치 틈과 신청서 PDF의 처리(추적 유지·제거)는 ISS-034가 정본이다. `C:\` 고정·`ROOT/data` 경로 문제는 ISS-032 #3과 인계 02:270이 먼저 기록했다. `05:52` 오기는 ISS-031 추기 6이, ps1 체인의 Windows 전용은 ISS-032 추기가 먼저 짚고 이 카드로 넘겼다. 이 카드는 그 사실들을 다시 판정하지 않고, 이 Mac으로 옮긴 뒤의 재현·이관 절차 관점에서만 다룬다.

## 문제

작업 머신이 바뀌었다. 이전 작업 일부(EXP-007 준비, EXP-010 ps1 체인, EXP-011 사전 스크립트)는 Windows(`C:\dev\idea`, ISSUES.md:84 "이 머신(Windows)")에서 했고, 민심 러너처럼 macOS를 전제한 작업도 있었다(§2). 지금은 이 macOS 클론에서 한다. 그 결과 이 Mac에서는 **저장소만으로 실험을 재현할 수 없다**. 의존성 명세와 원자료가 없다는 사실 일부는 인계서에 있지만(02:267-268), 이 Mac의 상태는 어디에도 기록되지 않았다. 점검 기준은 HEAD `33c73c5`(= origin/main), 2026-09-23, 이 Mac(macOS 26.5.1, git 2.50.1 Apple Git-155)이다.

참고로 인계서(`d80350b`, 작성자 Jaewon)가 점검한 머신에는 KGSS와 `data/minsim`이 있었다(02:268, 04:89). ISSUES.md:84-85는 KGSS `.sav` 보유처를 "재원 맥"으로 적었다. 또 `data/minsim`을 만든 민심 러너는 `fcntl`과 macOS 앱 경로를 전제한다(§2). Windows 고정 스크립트(ps1 체인 3종, exp011_pre 2종)의 커밋 작성자는 모두 jinwoo(`dec13ec`·`8d2a5cc`·`fe5cbf0`·`2962044`)이고, 민심 러너와 인계서의 커밋 작성자는 Jaewon(`2e4f3d6`·`d80350b`)이다. 커밋 작성자가 곧 실행 머신을 뜻하지는 않는다. 따라서 인계 점검 머신은 Windows가 아니라 원 맥이었을 수 있다 **[추측]**. 결국 관련 머신은 최소 셋이다(Windows, 원 맥, 이 Mac).

### 1. NFD 경로 18개가 NFC 이름의 untracked로 보인다 — `git add -A` 시 중복 커밋 위험

| 확인 항목 | 결과 (2026-09-23 재확인) |
|---|---|
| 추적 경로 중 NFD 바이트 경로 | `git ls-files` 330개 중 **18개**. `docs/4_참고자료/데이터/` 아래 MDIS 참고자료(파일설계서·코드집, 조사표, 자료 이용 주의사항 등) 폴더 4개의 17개 파일(`f0b7060`, 2026-07-24 추가)과 `docs/5_ 드림학기제/2026-2_드림학기제_IDEA(이데아)_창업형.pdf` 1개(`2a868db`, 2026-07-04 추가) |
| 원인 설정 | `.git/config`의 `core.precomposeunicode=true`(`git config --show-origin`). 디스크 이름도 NFD(폴더 4개, PDF 1개) |
| 보이는 증상 | `git status --porcelain` → NFD 관련 `??` 5줄(폴더 4, PDF 1). `git ls-files --others --exclude-standard` → NFC 경로 18개. 추적 중인 NFD 18개와 1:1로 대응. (둘 다 이번 리뷰가 새로 만든 ISS 카드 파일은 제외한 수) |
| 내용 동일성 | 각 경로에서 `git ls-files -s`의 blob과 디스크 파일의 `git hash-object`를 비교 → **18/18 동일, 상이 0, 누락 0** |
| 설정만 바꾼 상태 | `git -c core.precomposeunicode=false status --porcelain` → NFD 관련 0줄(이번 리뷰가 만들거나 고친 ISS 카드 줄만 남음) |

- **위험 [강]**: `git ls-files --others --exclude-standard`는 `git add -A`가 새로 추가할 대상과 같다. 따라서 `git add -A`(경로 인자가 없으면 작업 트리 어디서 실행하든 저장소 전체 대상)나 루트·`docs/`·해당 하위 폴더에서의 `git add .`를 실행하면 같은 내용의 NFC 경로 18개가 새 파일로 스테이징된다. 리뷰 단계에서는 임시 인덱스 사본에 `git add -A -n`을 실행해 18줄이 나오는 것을 확인했다(리뷰 발견 G9의 검증 판정). 이 카드를 쓰면서는 add 계열 명령을 실행하지 않았다.
- **커밋 후 결과 [중: git과 파일시스템의 일반 동작, 이번에 재현 안 함]**: NFD와 NFC가 모두 커밋되면 Windows(NTFS)와 Linux에서는 이름이 같아 보이는 폴더가 2벌 생긴다. macOS(APFS는 정규화를 무시하고 조회)에서는 두 경로가 같은 파일로 충돌한다.
- **문서 오기**: `docs/프로젝트_인계/05_자료지도.md:52`는 "MDIS 이용안내·코드집, 드림학기 PDF의 일부 로컬 사본도 미추적"이라고 적었다. 이 Mac 기준으로 해당 폴더·PDF의 파일은 모두 추적 중이고(blob 18/18 동일), 정규화 설정 때문에 미추적으로 보일 뿐이다. 인계 머신에 이것과 다른 로컬 사본이 따로 있었는지는 확인할 수 없어 "오기" 판단은 [중]이다. 같은 문장의 `.sav` 부분(미추적)은 별개로 맞다. HEAD `33c73c5`에 커밋된 문서에는 NFD나 precompose 언급이 없다(`git grep ... HEAD`, `data/t3` LLM 출력의 우연한 문자열 일치는 제외). 같은 리뷰에서 ISS-031 추기 6(미커밋)이 이 오기를 짚어 이 카드로 넘겼고, ISS-034 §5가 PDF 쪽에서 같은 현상을 짧게 적었다.
- **거버넌스와의 순서**: 신청서 PDF에 개인 연락처 등 개인정보 범주가 들어 있다는 점은 ISS-034 §5가 렌더링으로 확인했다(값은 적지 않음). 이 카드 작성·검토 중에는 PDF를 열람하지 않았다. 그 PDF를 계속 추적할지는 ISS-034의 결정 사항이다. 그 결정 전에 정규화 커밋을 하면 PDF를 새 경로로 다시 커밋하게 된다.

### 2. 파이썬 실행 환경이 없고 의존성 명세도 없다

| 확인 항목 | 결과 |
|---|---|
| 인터프리터 | `/usr/bin/python3` 3.9.6, `/opt/homebrew/bin/python3.13` 3.13.15. PATH의 `python3` 명령은 3.9.6을 가리킨다(ISS-037:44의 "3.9.6만"은 이 명령 기준). `.venv/`와 `venv/` 없음 |
| 과학 스택 | 두 인터프리터 모두 `numpy`·`pandas`·`pyreadstat`·`scipy`·`sklearn`·`openai`·`pyarrow`·`matplotlib` import 실패 |
| 의존성 명세 | `git ls-files` 기준 requirements·pyproject·lock·Pipfile·environment.yml·Dockerfile·devcontainer **0건**. `구현계획_v1.md:31`의 "W1 최우선: pyproject+lockfile, pytest"는 이행되지 않았다. 부재 자체는 인계 `02_동작구조.md:267`과 `04_판단기준과_남은과제.md:83`이 먼저 기록했고, 미이행 일정은 ISS-038, T4 게이트 쪽은 ISS-037이 다룬다 |
| 인계 목록 | `02_동작구조.md:264-266`에 의존성 목록은 있지만 `scikit-learn`(`scripts/exp010_kr_individual.py:19`)이 빠졌고 최소 Python 버전도 없다 |
| 사용 규모(정적 grep) | `scripts/*.py` 42개 중 numpy import 21개, pandas 20개, pyreadstat 16개, scipy 8개. 여기에 `src/engine/bank.py`(numpy·pandas, `:60` pyreadstat 지연 import)와 `tables.py`(numpy·pandas)를 더하면 23·22·17개다. `llm_client.py:105`는 openai를 지연 import한다 |

- **3.9 비호환(재현함)**: `src/engine/prompts_ab.py:26`의 `belief_card: dict | None = None`에 `from __future__ import annotations`가 없다. 그래서 `/usr/bin/python3`에서 `import engine.prompts_ab`를 하면 `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`가 난다. 3.13에서는 import에 성공한다. 이 오류는 `scripts/run_ab_cards.py:25`에 영향을 준다. `llm_client.py:11`에는 future import가 있어 문제없다. 검토 단계에서 `scripts/`·`src/engine/`·`민심테스트/scripts/`의 `.py` 전부를 3.9로 컴파일해 보니 문법 오류는 0건이었고, future import 없이 `X | None` 주석을 쓴 곳은 grep 기준 이 1곳뿐이었다. 다른 모듈은 과학 스택이 없어 3.9 import까지 가 보지 못했으므로, 3.9 호환 문제가 이것 하나라고 단정하지는 않는다. 3.11 이상 표준 모듈(`tomllib`)에 기대는 민심 러너는 아래에 따로 적는다.
- **민심 러너 전제**: `민심테스트/scripts/minsim_luna_run.py`에는 다음 전제가 박혀 있다. `:5`와 `:113`의 `fcntl`(Unix 전용이라 Windows에서는 원천적으로 불가), `:11`의 `tomllib`(Python 3.11 이상), `:16-18`의 `openai_codex` 패키지(두 인터프리터 모두 없음), `:148`의 `~/.codex/config.toml`(이 Mac에 있음, 내용은 열람 안 함), `:159`의 `codex_bin="/Applications/ChatGPT.app/Contents/Resources/codex"` 고정 경로(이 Mac에 ChatGPT.app 없음). `minsim_income_run.py:2,19`도 fcntl을 쓴다. 의존 목록 자체는 인계 `02_동작구조.md:266`에 이미 있다. 이 카드가 새로 적는 것은 이 Mac에서의 부재 확인과 앱 고정 경로다.
- **재생성 동일성**: `bank.py:125`는 `np.random.default_rng(seed)`를 쓰고, 추출은 `rng.choice`다(`bank.py:135,146`은 가중 비복원 추출, `tables.py:60`은 가중 범주 추출). NumPy는 BitGenerator의 원시 비트열은 안정적으로 유지하지만, `Generator` 메서드(choice 등)의 출력은 버전 간 동일을 보장하지 않는다 [중: NumPy 호환 정책(NEP 19)에 대한 일반 지식. 원문은 이번에 확인하지 않았고, 버전 간 비교도 하지 않음]. pandas 행 순서도 추출 결과에 들어간다. 그런데 뱅크 provenance(`persona_bank_national_v1.jsonl` 첫 레코드)에는 `seed`·`tag`와 원천 식별자(census·wage·income·kgss)는 있지만 python·numpy·pandas 버전이 없다. 따라서 버전을 고정하지 않고 재생성한 결과를 v1과 같다고 주장할 수 없다.
- **이 Mac에서 실제로 돌아가는 것**: `scripts/selftest_llm_client.py`(stdlib와 스텁만 사용, API 호출 없음)는 3.9와 3.13 모두 ok 23, skip 1(nvidia 키 없음), FAIL 0이었다. stdlib 배선은 동작한다. 과학 스택이 필요한 경로는 하나도 검증하지 못했다.

### 3. 원자료와 키가 없다

`IDEA_DATA_DIR`은 설정돼 있지 않다. `data/raw/`와 `data/minsim/` 디렉터리가 없고, 작업 트리 전체에 `*.sav`는 0건이다(`find`). `docs/4_참고자료/데이터/`에는 코드집·조사표 등 참고 문서만 있고 MDIS 원자료 CSV는 없다(CSV는 선관위 개표 CSV 1개뿐).

| registry 항목 (`data/registry.json`) | 경로 (data_dir 상대) | 이 Mac |
|---|---|---|
| census_2020_2pct_person / _household | `raw/2020_2%_표본_{인구,가구주택}_….csv` | 없음 |
| laf_2025h1_a / sflc_2025_master | `raw/2025_…csv` | 없음 |
| kgss_cum_2003_2025 | `kor_data_CUM0074_V2.sav` (`:33`, data 루트) | 없음 |
| socsci210 | `raw/socsci210` | 없음 |
| minsim_six_questions / minsim_income_question | `minsim/…json` | 없음. 다만 추적 사본 `민심테스트/questions/questions_six_v1.json`·`housework_income_v1.json`의 sha256이 registry와 일치함 |
| minsim_full_personas | `minsim/luna_parent70/personas_full.jsonl` | 없음 |
| minsim_original_personas, minsim_legacy_exclusions, minsim_mde_exp009, minsim_mde_phase0 | `exp009/…`, `exp009_kr_profile_exclude.csv`, `../phase0/…` | 있음, sha256 4/4 일치 |

- 13개 항목 중 9개가 없다. 질문 사본 2종을 빼면 **실제로 없는 자료는 7종**이다(MDIS CSV 4종, KGSS `.sav`, SocSci210, `personas_full.jsonl`).
- **키**: `API.txt`와 `.env`가 없고, `OPENAI_API_KEY`·`NVIDIA_API_KEY`·`NVIDIA_NIM_API_KEY`·`NGC_API_KEY`·`IDEA_KEY_FILE`도 설정돼 있지 않다(탐색 순서는 `llm_client.py:84-97`). 따라서 `llm_client`를 쓰는 스크립트 15개(러너와 임베딩 scorer 포함, selftest 제외)는 의존성을 설치하더라도 키 탐색 단계의 `SystemExit`에서 멈춘다 [정적 판단]. 민심 러너는 API 키 대신 Codex 인증을 쓴다(§2). 외부 호출 자체는 어차피 EXP 승인 사항이다.
- **막히는 범위(정적 판단, 실행하지 않음)**: KGSS를 읽는 파일은 grep 기준 `scripts/` 16개, `src/engine/bank.py`, `민심테스트/scripts/minsim_restore_profiles.py`다. 대표적으로 `bank.load_tables`(뱅크 재생성), exp008·exp009 KR prep·score, `exp011_pre_entropy.py:18`, `exp011_pre_fusion_test.py:28`이 있다. 뒤의 둘은 `resolve()`를 거쳐 `registry.py:28-29`에서 `FileNotFoundError`가 나고, 이 Mac에서는 그 전에 과학 스택 import(numpy·pandas·pyreadstat)가 먼저 실패한다. EXP-013 설정(`EXP-013:19` "KGSS 원자료 ID 재결합")도 KGSS가 필요하다. 반면 생성 러너(exp008_run·exp009_kr_run·exp010_run·exp012_run)는 KGSS 대신 커밋된 프로필·뱅크를 읽으므로 KGSS 부재가 아니라 패키지·키 부재로 막힌다(위 16개 목록에 들어 있지 않음). MDIS가 필요한 것은 뱅크 재생성·검증이다(`docs/5_ 드림학기제/주차보고/W01_1주차_보고서.md:87`의 4~5주차 인구 정합 합격선 "주요 인구 마진 ±1.5%p 이내"를 새 뱅크로 다시 검증하거나 확장할 경우 포함). `data/minsim`이 필요한 것은 민심 재실행이다.
- **EXP-011 문구가 이 머신에서 성립하지 않음**: `EXP-011:5`는 "KGSS 인구 0단계는 데이터 없이 착수 가능", §8 `:109`는 "지금 착수 가능"이라고 적었다. 여기서 "데이터"는 같은 줄의 블로커인 통계청 사회조사(MDIS)를 뜻하며, KGSS 원자료는 있다고 전제한 문구다 [중: 문맥 해석]. 이 Mac에는 KGSS가 없어 불성립한다. exp011_pre 5종의 상태는 다음과 같다. `donor_pool`(`:11,15,36`)과 `sealed_regions`(`:11,21`)는 `C:\dev\idea` 고정 경로라 실행되지 않는다. `entropy`와 `fusion_test`는 KGSS가 없어 실패한다. `mde`는 numpy만 있으면 되고, 입력 `data/exp010/kr_dist_raw.jsonl`은 있다.
- **인계서 시점**: `02_동작구조.md:268`의 "KGSS와 minsim 7개 entry 경로는 존재한다"와 `04:89`의 "KGSS 및 민심테스트 입력 경로들은 있었다"는 인계 작성 머신 기준이다. 04:89에는 "다른 머신·IDEA_DATA_DIR에 따라 달라질 수 있다"는 단서가 있지만, 이 Mac의 상태는 어디에도 기록되지 않았다.
- **복원할 때 배치 함정**: `registry.json:33`은 KGSS를 data 루트에 두게 돼 있다(`2e4f3d6`에서 `raw/` → 루트로 바뀜). 그런데 원자료 관련 무시 규칙은 `.gitignore:8`(`data/raw/`)과 `:9`(`docs/4_참고자료/데이터/*2003-2025*`)뿐이라 data 루트의 `.sav`는 걸리지 않고, `git check-ignore data/kor_data_CUM0074_V2.sav`는 exit 1이다. registry대로 복원한 뒤 `git add -A`를 한 번 실행하면 라이선스 원자료가 스테이징된다. 1번 항목과 같은 "무분별 add" 경로다. `data_manifest.md:4,39`와 `registry.py:29` 오류문은 `data/raw/` 규약을 유지하고 있다. 경로 변경 자체는 인계 `02_동작구조.md:65`가, `.gitignore` 틈과 그 처리안은 ISS-034 §4가 먼저 다룬다. 이 카드에서는 이관 체크리스트에 넣을 배치 규칙으로만 적는다.

### 4. OS 고정 경로와 셸 가정

- `scripts/exp011_pre_donor_pool.py:11,15,36`, `scripts/exp011_pre_sealed_regions.py:11,21`에 `C:\dev\idea\…`가 박혀 있다. ISS-032 #3에 이미 기록돼 있다.
- `scripts/exp010_{kr,us,ssr}_chain.ps1:2`의 `Set-Location C:\dev\idea`와 `exp010_us_chain.ps1:6`, `exp010_ssr_chain.ps1:5`의 `Get-CimInstance Win32_Process`는 Windows 전용이다. 이 Mac에는 `pwsh`가 없다. 같은 사실을 같은 리뷰의 ISS-032 추기(`:59`)가 캐시·러너 관점에서, ISS-024 추기(`:55`)가 스모크 게이트 관점에서 적었다. 이 카드는 이관 관점(이 Mac에서 체인 실행 불가)으로만 다룬다.
- `phase0/build_ground_truth.py:6,59`의 `/sessions/trusting-zen-gates/…`는 Windows 경로가 아니라 과거 샌드박스의 POSIX 경로다. ISS-002 문제 절(`ISS-002:10`)에 이미 기록돼 있다(DECIDED, 카드 구현 절은 "미착수").
- `CLAUDE.md:7`의 "셸 작업은 PowerShell 우선"은 Windows를 전제로 한 문구다. 이 Mac의 셸은 zsh이고 pwsh가 없다. 이번 세션에서 zsh는 한글 경로(`docs/프로젝트_인계/…`, `민심테스트/…`)를 sed·grep·python으로 정상 처리했다. 1번의 NFD/NFC 차이는 셸 문제가 아니라 git 설정 문제다. CLAUDE.md는 규칙 문서이므로 문구 개정은 인간이 판단한다.

### 5. 데이터 경로 이원화 (`data_dir()` 대 `ROOT/data`)

- `src/engine/registry.py:12-13`의 `data_dir()`는 `IDEA_DATA_DIR`을 쓰고, 없으면 `repo/data`를 쓴다. `:16-17`의 `load_registry()`도 `data_dir()/registry.json`을 읽는다.
- `scripts/*.py` 42개 중 `data_dir()`를 쓰는 스크립트는 11개다(build_bank, validate_bank, exp009_kr_prep·us_prep·freeze_pairs·kr_exclude·screen_us, exp010_plot_kr·plot_candidates, exp011_pre_entropy·fusion_test). `ROOT / "data"`를 직접 쓰는 스크립트는 27개(exp008_*, exp009_*_run·score, exp010_run·score 등)다. 두 방식을 섞어 쓰는 스크립트는 0개다.
- 예를 들어 `exp009_kr_prep.py:27`(`OUT = data_dir() / "exp009"`)과 `exp009_kr_run.py:22`·`exp009_kr_score.py:25`(`ROOT / "data" / "exp009"`)는 서로 다른 기준을 쓴다. `exp009_us_prep.py:23`과 `exp009_us_run.py:23`도 같은 관계다. `IDEA_DATA_DIR`을 저장소 밖으로 설정하면 prep 출력과 run 입력이 **오류 없이** 갈라진다. 지금은 설정돼 있지 않아서 실제로 어긋난 적은 없다.
- `IDEA_DATA_DIR`을 설정하면 registry도 외부 사본을 읽는다. 그러면 추적 중인 `data/registry.json`과 해시 정본이 분리된다. 또 `registry.json:66`의 `minsim_mde_phase0` 경로 `../phase0/…`는 data_dir 기준 상대경로라서 외부 디렉터리에서는 깨진다.
- 이 상태는 ISS-002 결정 2(`ISS-002:18`)와 AGENTS.md:49 코드 컨벤션에 어긋난다. ISS-032 #3과 인계 `02_동작구조.md:270`은 이를 원칙 차원에서 기록했다. 이 카드는 이관 운영 제약으로 기록한다. 경로를 통일하기 전에는 원자료를 외부 폴더에 두고 `IDEA_DATA_DIR`로 연결하는 방식을 쓸 수 없다.

## 분석

원인은 다섯 갈래다. (a) 설계 단계의 인프라(W1 pyproject·lock)를 이행하지 않았다. (b) 머신별 로컬 상태(원자료·키·앱)가 기록 없이 흩어져 있다. (c) 스크립트가 특정 OS에 묶여 있다. (d) 클론마다 git 유니코드 정규화 설정이 다르다. (e) 경로 규약이 둘로 나뉘어 있다. 과거 결과(캐시·뱅크 v1)는 커밋돼 있어서 재채점 일부는 의존성만 설치하면 가능할 수 있다(외부 API를 부르는 scorer는 제외 — ISS-032 #2. `exp008_score`·`exp009_kr_score`처럼 KGSS를 읽는 채점기도 제외 — §3. 재채점도 EXP 카드 대상 — AGENTS 규칙 6). 반면 뱅크 재생성, KGSS 기반 prep, 민심 재실행은 원자료가 이관돼야만 가능하다.

### 전체 방향

| 옵션 | 내용 | 장점 | 단점 | 근거 등급 |
|---|---|---|---|---|
| A | Python 3.11 이상 venv, `pyproject.toml`과 해시 포함 lock, 선택 그룹 분리(민심 `openai_codex`, phase0 레거시). 원자료 이관 체크리스트(registry 항목별 출처·권한 보유자·배치 경로·sha256). 이관 스모크(`resolve(verify=True)` 전 항목, selftest, 전 모듈 import). NFD 정규화 커밋. OS 고정 경로 제거. 경로 통일 | 구현계획:31(W1 인프라)과 ISS-002 결정 2에 정합. 비용 $0. Windows와 macOS 모두 적용 가능 | 과거 실행 당시의 패키지 버전을 알 수 없어서 "과거 환경 복원"이 아니라 "현행 환경 고정"에 그친다. 원자료 전송은 사람이 해야 한다(권한·라이선스). 코드 변경분은 적대적 감사와 교차모델 검토 대상이다 | [강] 이번 점검 증거 + 구현계획:31 |
| B | 컨테이너(Docker/devcontainer)로 실행 환경 고정 | OS 차이를 흡수하고 버전을 완전히 고정한다 | 원자료와 키는 여전히 볼륨 마운트가 필요해 핵심 공백(3번)이 해소되지 않는다. 민심 러너는 macOS ChatGPT.app과 Codex 인증에 의존해 컨테이너 밖에 남으므로 이원 운영이 된다. 이 Mac에 `docker` CLI는 있으나 데몬 상태는 확인하지 않았다. 학기 잔여 일정에 비해 과투자다 | [중] |
| C | 현상 유지(각자 머신에서 수동 설치, 구두 공유) | 당장 비용 없음 | ISS-002 DECIDED 결정 2와 AGENTS.md:49 경로 규약과의 불일치가 계속된다. `git add -A` 한 번으로 NFD 중복 18건이나 KGSS 원자료가 커밋될 수 있다. 재생성 동일성을 주장할 수 없고, 다음 이관 때 같은 조사를 반복해야 한다 | [강] |

### NFD 처리 하위 옵션 (A 안에서)

| 옵션 | 내용 | 장점 | 단점 | 근거 등급 |
|---|---|---|---|---|
| N1 | 운영 수칙: `git add -A`(실행 위치 무관)와 상위 폴더에서의 `git add .` 금지, 파일을 명시해 스테이징 | 즉시 적용 가능하고 위험이 없다. KGSS 배치 함정도 함께 막는다 | 사람의 주의에만 의존한다 | [강] |
| N2 | 이 클론만 `core.precomposeunicode=false`로 설정 | status가 즉시 깨끗해진다(`-c` 임시 적용으로 0줄 확인) | 이후 macOS 앱이 만든 한글 파일명이 NFD로 커밋될 수 있어 재발 경로가 된다. 클론별 설정이라 다른 클론에 전파되지 않는다 | [중] |
| N3 | 정규화 커밋: 인덱스의 NFD 18경로를 NFC 이름으로 바꾼다(blob 불변, 이름만 변경) | 영구 해결. 모든 OS에서 한 벌로 보인다 | 다른 클론(Windows `C:\dev\idea`, 원 맥)에서 pull할 때 경로가 교체되므로 로컬 수정이 없는지 확인하고 동시에 조율해야 한다. `precomposeunicode=true`에서는 git이 명령 인자를 NFC로 바꾸기 때문에 `git mv <NFD 경로>` 지정이 실패할 수 있다. `-c core.precomposeunicode=false`로 NFD를 `rm --cached`한 뒤 NFC를 add하는 등의 절차를 임시 클론에서 드라이런으로 확정해야 한다 [미검증]. 신청서 PDF를 추적 해제하기로 결정되면(ISS-034 §5) 그 파일은 개명이 아니라 제거 대상이다 | [중] |
| N4 | 재발 방지: NFD 경로를 거부하는 점검 스크립트나 pre-commit 훅 | 재발을 기계적으로 차단한다 | 훅은 클론마다 설치해야 하고 CI가 없다 | [약] |

## 결정

**미결 — 인간 결정 대기.** 에이전트는 DECIDED를 선언할 수 없다(AGENTS 규칙 8).

**제안 (에이전트, 비구속):** A를 채택하고, NFD는 N1 → N3(+N4) 순서로 처리한다. N2는 새 NFD 이름이 다시 커밋되는 재발 경로를 열기 때문에 상시 설정으로는 제안하지 않는다(상태 확인용 `-c` 임시 적용만). B는 원자료·키 공백을 해소하지 못하고 민심 러너가 macOS 앱에 의존하므로 보류한다(학기 후 재검토, 기각은 아님). C는 ISS-002 DECIDED 결정 2와 충돌하므로 기각을 제안한다. 적용 순서는 다음과 같다.

1. **무후회 운영 수칙(제안 — 채택·공지는 인간 판단)**: N1 적용. 경로가 통일될 때까지 `IDEA_DATA_DIR`은 설정하지 않는다. 원자료는 ignore되는 위치에만 둔다. 단 KGSS는 registry가 `.gitignore` 밖인 data 루트를 가리키므로(§3), ⓐ 결정 전에는 registry대로 배치하면 이 수칙과 충돌한다. 그 사이에는 배치 전에 이 클론의 `.git/info/exclude`로 해당 파일을 무시 처리하는 방법이 있다 [중: git 일반 동작, 이번에 시험 안 함].
2. **인간 결정이 필요한 것**
   - ⓐ KGSS 정본 배치: `data/raw/`로 되돌릴지, data 루트를 유지하고 ignore 규칙을 추가할지. ISS-034 제안 2(`.gitignore`에 `*.sav`, `registry.py:29` 오류문·data_manifest 규약 통일)와 같은 결정이므로 그 카드에서 함께 정한다.
   - ⓑ 원자료 이관 담당자와 경로. 보유자는 원 맥으로 추정된다(ISSUES.md:84-85) [추측]. 이관 전송 경로와 보관 위치는 ISS-034의 약관·재배포 검토(D) 결론을 따라야 한다. 원 기기에만 있는 EXP-016 부분 캐시의 sha256 회수(ISS-029 추기 3의 제안 3)도 같은 담당자가 함께 처리하는 편이 효율적이다.
   - ⓒ N3 정규화 커밋의 시점과 클론 조율 담당자. ISS-034의 PDF 추적 여부 결정 뒤에 한다.
   - ⓓ Python 3.13 venv와 의존성 설치 승인.
   - ⓔ `CLAUDE.md:7` 문구 개정 여부. 예: "Windows는 PowerShell, macOS는 zsh 사용 가능. 한글 경로 정규화 차이는 git 설정 문제."
3. **코드 변경(구현 규율상 설계 감사, 결과 감사, 교차모델 검토 대상)**: pyproject와 lock 추가. `prompts_ab.py`에 future import 추가. 경로를 `data_dir()` 기준으로 통일(ISS-002). exp011_pre 2종의 `C:\` 경로 제거. ps1 체인은 크로스플랫폼 py로 바꾸거나 "Windows 전용"으로 명시한다.
4. **문서 정정(append 방식)**: `05_자료지도.md:52`의 "미추적 사본" 오기. `02:268`과 `04:89`에 "작성 머신 기준이며, 2026-09-23 이 Mac에서는 부재" 추기. EXP-011 `:5`(블로커 줄)와 §8 `:109`의 "착수 가능"을 "KGSS 원자료가 있는 머신에서"로 한정한다(EXP 카드 개정 절차에 따름).

## 구현

**미착수.** 이 카드는 문서만 추가한다. 코드·설정·git 인덱스는 변경하지 않았다. ISSUES.md 동기화는 별도로 한다.

> **TODO (2026-09-23, 보류)**: 사용자가 Mac 환경 복구를 "나중에" 하기로 했다. 아래 체크리스트는 착수 전까지 대기한다. 그동안 적용할 수칙은 두 가지다. `git add -A`나 `git add .`를 쓰지 않고 파일을 명시해 스테이징한다. 원자료·의존성이 필요한 실행(뱅크 재생성, 실험, 채점)은 이 Mac에서 시도하지 않는다. 영향: ISS-033 뱅크 v2 재생성이 이 항목에 막혀 있다.

완료 모습(체크리스트):
- [ ] `pyproject.toml`과 해시 포함 lock을 추가한다. `requires-python >= 3.11`로 둔다. 기본 의존성은 numpy, pandas, pyreadstat, scipy, scikit-learn, pyarrow, matplotlib, openai다. 선택 그룹으로 민심(`openai_codex`)과 phase0 레거시(datasets·tqdm·anthropic, `02:265`)를 둔다. 설치 절차를 README나 인계 02 §6에 적는다.
- [ ] 이관 체크리스트 문서를 만든다. registry 13항목마다 출처, 권한 보유자, 배치 경로, sha256, 머신별 존재 여부를 적는다. 키 파일 위치 규칙과 민심 러너 전제(macOS, ChatGPT.app, Codex 인증)도 포함한다.
- [ ] 이관 스모크 로그를 남긴다. `resolve(name, verify=True)` 전 항목 통과(또는 부재 항목의 명시 목록), `selftest_llm_client.py` 통과, `import engine.*` 전 모듈 성공이다.
- [ ] N3를 실행한 뒤 `git ls-files` 기준 NFD 0건, 이 Mac에서 `git status` 깨끗함, 다른 클론에서 pull 후 status 깨끗함을 확인한다. N4 점검 스크립트를 추가한다.
- [ ] 코드 변경분(future import, 경로 통일, `C:\` 제거, ps1 처리)에 대한 설계 감사와 결과 감사를 `audits/`에 남기고 교차모델 검토(ISS-026)를 받는다.
- [ ] 뱅크 provenance에 python·numpy·pandas 버전을 기록한다(향후 재생성분부터, v1 덮어쓰기 금지).

## 검증

### 이번에 한 것 (2026-09-23, HEAD `33c73c5`, 읽기 전용)
- `git ls-files`와 유니코드 정규화를 비교해 NFD 18건을 찾았다(docs/4_참고자료/데이터 17, 드림학기 PDF 1). 추가 커밋은 `git log --diff-filter=A`로 확인했다(`f0b7060` 17건, `2a868db` 1건).
- blob 대조: `git ls-files -s`와 `git hash-object`를 비교해 18/18 동일했다. `git ls-files --others --exclude-standard`는 NFC 18건이었고, `git -c core.precomposeunicode=false status --porcelain`은 NFD 관련 0줄이었다(둘 다 리뷰 중 새로 생긴 ISS 카드 파일 제외).
- 인터프리터 두 개에서 모듈 import를 점검했다. 3.9에서 `import engine.prompts_ab`를 실행해 TypeError를 재현했고, 3.13에서는 성공했다. 리뷰 중 `src/engine/__pycache__/`에 cpython-313 pyc 3개(`__init__`·`prompts_ab`·`prompts_t3`, 16:24)가 생겼다. 이 3.13 import 점검에서 생긴 것으로 보인다. `.gitignore:2`로 무시되는 경로라 추적 파일은 바뀌지 않았다. 따라서 "파일 쓰기 전무"는 아니다.
- registry 13항목의 존재 여부를 확인했고, 존재하는 4항목과 민심 질문 사본 2개의 sha256을 로컬에서 계산해 대조했다(모두 일치). `git check-ignore data/kor_data_CUM0074_V2.sav`는 exit 1이었다. `API.txt`와 `.env`는 없고, 키 환경변수는 설정 여부만 확인했다(값은 출력하지 않음).
- `scripts/selftest_llm_client.py`를 오프라인 스텁으로 두 인터프리터에서 1회씩 실행했다(`-B`, 파일 쓰기 없음). 결과는 ok 23, skip 1, FAIL 0이었다(검토 단계에서 같은 방식으로 재실행해 같은 결과를 확인). 지표 산출이나 외부 호출은 없었다. 실행 전후 `git status --porcelain`의 NFD 관련 줄은 똑같이 5줄이었다(리뷰 중 새로 생긴 ISS 카드 파일은 제외).
- grep으로 정적 대조한 것: 스크립트별 import와 경로 기준(`data_dir()` 11개, `ROOT/data` 27개), 고정 경로의 행 번호, 인계서·EXP-011·EXP-013·ISSUES·CLAUDE.md의 해당 행.
- 적대적 검토(같은 날, Claude 단일 모델): 인용 행과 수치를 다시 열어 대조했다. 스크립트별 import 수(23·22·17 → `scripts/` 기준 21·20·16), registry 항목 경로, 키 탐색 행 범위(`:84-97`), provenance 필드 서술, NumPy 호환 범위 서술을 바로잡았다. ISS-034·ISS-037·ISS-038, 인계 02:65·266·270과 겹치는 부분에 교차 참조를 달았다.
- 2차 적대적 검토(같은 날, Claude 단일 모델, 읽기 전용): 인용 행·수치를 모두 다시 열어 대조했다(NFD 18건과 추가 커밋, blob 18/18, status 5줄·`--others` 18줄·`-c` 0줄, 인터프리터·패키지 부재, 의존성 명세 0건, import 수 21·20·16·8, registry 13항목과 sha256 6건, 키 탐색 행, llm_client 사용 스크립트 15개, KGSS 읽는 스크립트 16개, `data_dir()` 11개·`ROOT/data` 27개·혼용 0개, 고정 경로 행, EXP-011·EXP-013·ISS-002·W01 인용 행). selftest도 두 인터프리터에서 `-B`로 다시 돌려 ok 23, skip 1, FAIL 0을 확인했다. 고친 것: `precomposeunicode=false` 상태의 잔여 줄 서술, `git add -A`의 실행 위치 범위(경로 인자가 없으면 저장소 전체), 인계서 인용 문구, `.gitignore` 무시 규칙 서술(`:9` 포함), W01:87을 산출물이 아닌 합격선으로 정정, 생성 러너가 KGSS 없이도 패키지·키 때문에 막힌다는 구분 추가, 3.9 전체 컴파일 결과 추가. 같은 리뷰의 미커밋 추기(ISS-031 추기 6, ISS-032·ISS-024 추기, ISS-029 추기 3)와 이 카드를 참조하는 ISS-033·035·037·040에 교차 참조를 달았다. 인계 점검 머신 추정에 커밋 작성자 근거를 보탰지만 등급은 [추측]으로 유지했다.

### VERIFIED로 올리려면 필요한 증거
1. 인간 결정 기명(ⓐ~ⓔ).
2. lock 기반으로 새로 설치한 환경의 로그와 이관 스모크 결과(`resolve(verify=True)` 항목별 결과, selftest, 전 모듈 import).
3. N3 적용 뒤 NFD 0건과 두 OS 클론에서 status가 깨끗함을 보여주는 출력.
4. 경로 통일 코드의 감사 기록과 교차모델 검토 기록.
5. (선택) 원자료를 이관한 뒤 뱅크 재생성 동일성 점검. 새 파일로 출력하고 v1과 레코드 단위로 대조하며, 다르면 버전 차이로 기록한다. 마진 오차 등 지표를 산출하면 경량 EXP 카드를 먼저 만든다(AGENTS 규칙 6).

### 미검증 잔여물
- NFD·NFC 이중 커밋이 각 OS에서 실제로 어떻게 동작하는지는 재현하지 않았다(일반 동작에 근거한 [중]).
- N3의 구체 명령 절차(특히 `precomposeunicode=true`에서 `git mv` 실패 여부)는 임시 클론 드라이런이 필요하다.
- 뱅크 v1을 생성할 당시의 numpy·pandas·Python 버전을 모른다. Generator 스트림이 버전에 따라 달라지는지 이 저장소 기준으로 확인하지 않았다.
- 다른 머신(Windows `C:\dev\idea`, 원 맥)의 현재 상태, 원자료 보유 여부, sha256, git 정규화 설정을 확인하지 않았다. 인계 점검 머신이 원 맥이라는 판단은 [추측]이다.
- 신청서 PDF의 내용은 열람하지 않았다(개인정보 범주는 ISS-034 §5 인용).
- selftest를 뺀 스크립트의 실행 실패 범위는 import와 경로를 정적으로 분석해 판단했다. 실제 실행은 하지 않았다.
- Docker 데몬과 Docker Desktop의 상태를 확인하지 않았다.
- ISS-026 교차모델 검토 전이다. 이 카드는 Claude 단일 모델의 분석이다.
