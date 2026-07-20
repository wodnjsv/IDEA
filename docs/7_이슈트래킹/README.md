# 이슈 트래킹 시스템 — 이슈 → 해결 → 구현 → 검증

> 이 프로젝트의 모든 비자명한 문제·결정·실험을 **한 곳에서, 하나의 생애주기로** 기록한다.
> 형식은 MADR(Markdown Any Decision Records)의 "검토한 옵션 + 근거" 구조를 이슈 생애주기와 합친 것.
> 에이전트(Claude/Codex)와 팀원 모두 이 규칙을 따른다 — 규칙 정본은 저장소 루트 `AGENTS.md`.

## 왜 이 구조인가
- **재론 방지**: 결정된 것을 매 세션 다시 논쟁하지 않는다. 에이전트는 작업 전 [ISSUES.md](ISSUES.md) 인덱스를 확인한다.
- **검증 없는 완료 금지**: 이 프로젝트의 제품 철학("정확도 리포트 — 어디서 얼마나 틀렸는지 공개")을 문서 관리에도 적용한다. 증거 없이 VERIFIED 없다.
- **연구 루프 지원**: 실험(EXP)이 이슈(ISS)의 증거가 되고, 이슈의 결정이 구현이 되는 흐름을 링크로 추적한다.

## 레코드 2종

| 종류 | ID | 위치 | 용도 |
|---|---|---|---|
| 이슈 카드 | `ISS-NNN` | `issues/ISS-NNN-슬러그.md` | 문제·리스크·설계 결정 (생애주기 전체) |
| 실험 카드 | `EXP-NNN` | `experiments/EXP-NNN-슬러그.md` | 가설→설정→결과→판정 (재현 가능 기록) |

템플릿: [_templates/TEMPLATE_ISS.md](_templates/TEMPLATE_ISS.md) · [_templates/TEMPLATE_EXP.md](_templates/TEMPLATE_EXP.md)

## 이슈 상태 기계

```
OPEN ──→ ANALYZED ──→ DECIDED ──→ IMPLEMENTED ──→ VERIFIED
  │          │            │
  └──────────┴────────────┴──→ CLOSED-WONTFIX / SUPERSEDED(by ISS-xxx)
```

- **OPEN**: 문제 인지·기록됨. 분석 전.
- **ANALYZED**: 원인 분해·옵션 정리됨. 결정 전.
- **DECIDED**: 결정 확정. 결정 섹션은 이후 **append-only** — 뒤집으려면 새 이슈를 만들고 원 이슈를 `SUPERSEDED`로.
- **IMPLEMENTED**: 코드/문서로 반영됨(커밋 해시 링크 필수).
- **VERIFIED**: 검증 증거(수치·테스트·게이트 통과) 기록됨.

## 운영 규칙 (요약 — 정본은 AGENTS.md)
1. 작업 시작 전 ISSUES.md를 확인한다. DECIDED 이슈와 충돌하는 작업은 supersede 절차 없이 하지 않는다.
2. 구현·리뷰·실험 중 발견한 비자명한 문제는 즉시 ISS 카드로 만든다(OPEN이라도).
3. 결정 섹션에는 반드시 검토한 옵션·근거(가능하면 근거 등급 [강/중/약/추측])·기각 사유를 남긴다.
4. 이슈 관련 커밋 메시지에 `(ISS-NNN)`을 붙이고, 카드의 구현 섹션에 커밋 해시를 역링크한다.
5. 카드 생성·상태 변경 시 같은 커밋에서 ISSUES.md 인덱스를 갱신한다.
6. 실험은 EXP 카드 없이 돌리지 않는다. 재현 정보(모델·버전·시드·데이터 스냅샷·비용) 필수.

## 참고 레퍼런스
- MADR 4.0 (adr.github.io/madr) — 옵션·장단·결정 구조의 원형
- Nygard ADR — status/context/decision/consequences 생애주기
- AGENTS.md 표준 (agents.md) — 에이전트 규칙 파일 관행
