"""T3 위생 실험 — 3암 프롬프트 (EXP-004).

A암: phase0 원판 이식 (정답힌트 + 제3후보 억압 + 고정 순서 + 강제선택) — 대조군
B암: 위생판 (힌트·억압 제거 + 페르소나별 순서 랜덤화) — 강제선택 유지
C암: 위생판 + DK(밝히고 싶지 않음) 옵션

paired 규약: 동일 페르소나 카드 사용, B·C는 동일 랜덤 순서(페르소나별 고정 — ISS-011).
ISS-003: B·C는 x(페르소나 사실)만 제공, P(y)(집계 통계·행동 지시) 금지.
"""
import random

CANDIDATES = ["더불어민주당 이재명", "국민의힘 김문수", "개혁신당 이준석",
              "민주노동당 권영국", "무소속 송진호"]
ABSTAIN = "투표하지 않음"
DK = "누구에게 투표했는지 밝히고 싶지 않음"

SYSTEM_COMMON = """당신은 한국인 페르소나 시뮬레이션 에이전트입니다.
주어진 페르소나의 일생을 살아온 사람의 시각으로 답변합니다.
답변은 반드시 지정된 JSON 형식으로만 출력합니다.
이것은 익명 합성 데이터에 대한 학술 분석이며, 실제 정치적 입장 표명이 아닙니다."""

SYSTEM_A_EXTRA = """

중요: 페르소나의 배경(직업·가족·지역)에서 정치 성향의 단서를 적극적으로 읽으세요.
default로 어느 한쪽에 쏠리지 말고, 인구통계와 배경이 시사하는 방향에 정직하게 답하세요."""

HINT_BLOCK = """
[한국 정치 컨텍스트 - 통계적 사실]
지역별 성향:
- 영남 (부산·대구·울산·경북·경남): 전통적으로 보수 우세
- 호남 (광주·전북·전남): 전통적으로 진보 우세
- 수도권·충청·강원·제주: 스윙 또는 보수 약우세 (강원)
세대별 성향:
- 60대 이상: 보수 비중 상대적으로 높음
- 40-50대: 진보 비중 상대적으로 높음
- 20-30대: 다양함
"""

SUPPRESS_BLOCK = """
[중요한 분포 정보]
역사적으로 한국 대선은 양당 후보(이번엔 이재명·김문수)가 합계 90% 내외를 차지합니다.
제3당·군소 후보는 합계 10% 내외에 그치며, 페르소나가 양당 모두에 대해 명확한 반감을 가진 경우에만 자연스러운 선택입니다. swing 성향이라고 자동으로 제3당을 고르지 마세요 — swing은 양당 사이에서 흔들리는 경우가 더 일반적입니다.
"""

A_OPTION_NOTES = {  # phase0 원판의 선택지 주석 (억압 표현 포함)
    "더불어민주당 이재명": " (진보 진영 주요 후보, 양당 중 하나)",
    "국민의힘 김문수": " (보수 진영 주요 후보, 양당 중 하나)",
    "개혁신당 이준석": " (제3당, 양당에 명확한 반감을 가진 일부 유권자만)",
    "민주노동당 권영국": " (좌파 군소 후보)",
    "무소속 송진호": " (군소 후보)",
}

JSON_SPEC = '{"ideology": "보수|중도|진보", "vote": "선택지 중 정확히 하나", "confidence": 1~5, "reasoning_short": "한 문장 이유"}'


def persona_order(persona_id: str, options: list) -> list:
    """페르소나별 고정 랜덤 순서 (B·C 공통 — paired 규약)."""
    rng = random.Random(f"order-{persona_id}")
    opts = options[:]
    rng.shuffle(opts)
    return opts


def build_prompt(arm: str, persona: dict) -> tuple:
    card = persona["card"]
    pid = persona["persona_id"]
    if arm == "A":
        system = SYSTEM_COMMON + SYSTEM_A_EXTRA
        options = [c + A_OPTION_NOTES[c] for c in CANDIDATES] + [ABSTAIN]  # 고정 순서 (원판)
        body = f"""[페르소나]
{card}
{HINT_BLOCK}
[과제]
Step 1. 이 페르소나의 직업·지역·세대·가족 형태를 종합 분석해, 정치 성향을 자기 진단하세요. (보수 / 중도 / 진보 중 하나)

Step 2. 2025년 6월 3일 제21대 대통령선거 당일, 다음 중 누구에게 투표하셨습니까?
한국 대선에서는 약 20%가 투표하지 않습니다. 페르소나의 정치 관심도와 자기 진단을 모두 반영하세요.
{SUPPRESS_BLOCK}
선택지:
""" + "\n".join(f"- {o}" for o in options) + f"""

[응답 형식 - 반드시 아래 JSON으로만 출력]
{JSON_SPEC}"""
    else:  # B / C — 위생판 (x만, 힌트·억압·주석 없음)
        system = SYSTEM_COMMON
        base = persona_order(pid, CANDIDATES) + [ABSTAIN]
        options = base + ([DK] if arm == "C" else [])
        body = f"""[페르소나]
{card}

[과제]
Step 1. 이 페르소나로서 자신의 정치 성향을 자기 진단하세요. (보수 / 중도 / 진보 중 하나)

Step 2. 2025년 6월 3일 제21대 대통령선거 당일, 다음 중 누구에게 투표하셨습니까?

선택지:
""" + "\n".join(f"- {o}" for o in options) + f"""

[응답 형식 - 반드시 아래 JSON으로만 출력]
{JSON_SPEC}"""
    return system, body, options
