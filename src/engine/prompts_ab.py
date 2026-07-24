"""EXP-005 카드층 A/B — D암(생각 카드)·E암(후보 프로필).

paired 규약: EXP-004의 B암과 동일 페르소나·동일 선택지 순서(persona_order 재사용).
D암 = B암에서 이념 명찰 문장만 신념 문장으로 교체 (ISS-018 처방)
E암 = B암에서 선택지에만 중립 프로필 추가 (ISS-017 처방 — 직업·경력 사실 한정, 전 후보 동일 형식)
"""
import re

from .prompts_t3 import ABSTAIN, CANDIDATES, JSON_SPEC, SYSTEM_COMMON, persona_order

IDEOLOGY_SENT = re.compile(r"\s*정치적으로는 스스로 '[^']*' 성향이라고 생각합니다\.")

PROFILES = {  # 공보물 수준 사실 (직업·경력 한정, 웹 검증 2026-07-24 — EXP-005 카드 참조)
    "더불어민주당 이재명": "전 경기도지사, 전 더불어민주당 대표",
    "국민의힘 김문수": "전 경기도지사, 전 고용노동부 장관",
    "개혁신당 이준석": "국회의원, 전 국민의힘 당대표",
    "민주노동당 권영국": "변호사, 노동인권 활동",
    "무소속 송진호": "기업인, 사회단체 대표",
}


def strip_ideology(card: str) -> str:
    return IDEOLOGY_SENT.sub("", card).strip()


def build_prompt_ab(arm: str, persona: dict, belief_card: dict | None = None) -> tuple:
    pid = persona["persona_id"]
    base_order = persona_order(pid, CANDIDATES)  # B암과 동일 순서 (paired)
    if arm == "D":
        card = strip_ideology(persona["card"]) + " " + belief_card["sentences"]
        options = base_order + [ABSTAIN]
    elif arm == "E":
        card = persona["card"]
        options = [f"{c} ({PROFILES[c]})" for c in base_order] + [ABSTAIN]
    else:
        raise ValueError(arm)
    body = f"""[페르소나]
{card}

[과제]
Step 1. 이 페르소나로서 자신의 정치 성향을 자기 진단하세요. (보수 / 중도 / 진보 중 하나)

Step 2. 2025년 6월 3일 제21대 대통령선거 당일, 다음 중 누구에게 투표하셨습니까?

선택지:
""" + "\n".join(f"- {o}" for o in options) + f"""

[응답 형식 - 반드시 아래 JSON으로만 출력]
{JSON_SPEC}"""
    return SYSTEM_COMMON, body, options
