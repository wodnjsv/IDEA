"""뱅크 두 판의 paired 동일성 검사 (ISS-033): 통근 문장 외 전 필드가 행 단위로 같은지 확인한다.

    python3 scripts/compare_bank_versions.py national v1 v2
    python3 scripts/compare_bank_versions.py --paths A.jsonl B.jsonl

검사 규칙 (Codex 교차검토 2026-09-23 #1~#3 반영):
- 입력 비어 있음·행 수 불일치·필수 키 누락·weight_bank ≤0·persona_id 중복 → FAIL
- persona_id는 행별로 **같아야** 한다. persona_id는 선택지 순서 난수 키(prompts_t3.persona_order)라서
  다르면 통근 문장만 다른 paired 비교가 성립하지 않는다(--allow-id-change: 태그 구간만 다른 경우 허용·경고).
- skeleton·drawn·weight 등 나머지 필드: 키 집합과 값이 모두 같아야 한다(누락과 null을 구분).
- card: 통근 문장이 있으면 독립 문장으로 정확히 1회 있어야 하고, 없으면 '직장은' 문장이 없어야 한다.
  그 한 곳만 제거한 나머지 card가 같아야 한다.
- provenance: 허용 키(tag·id_tag·commute_rule·libs·derived_from·relabel)만 달라도 된다. 공통 설정(seed·floor 등)은 비교.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import data_dir  # noqa: E402

REQUIRED = {"persona_id", "track", "skeleton", "drawn", "weight_person", "weight_bank", "card", "provenance"}
IGNORED_TOP = {"persona_id", "provenance", "card", "skeleton"}   # 각각 아래에서 별도 규칙으로 검사
PROV_ALLOWED = {"tag", "id_tag", "commute_rule", "libs", "derived_from", "relabel"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def validate(rows, name):
    errs = []
    if not rows:
        return [f"{name}: 입력 비어 있음"]
    ids = [r.get("persona_id") for r in rows]
    if len(set(ids)) != len(ids):
        errs.append(f"{name}: persona_id 중복 {len(ids) - len(set(ids))}건")
    for i, r in enumerate(rows):
        miss = REQUIRED - set(r)
        if miss:
            errs.append(f"{name} #{i}: 필수 키 누락 {sorted(miss)}")
            continue
        w = r["weight_bank"]
        if not isinstance(w, (int, float)) or not w > 0:
            errs.append(f"{name} #{i}: weight_bank 비정상 {w!r}")
        if not isinstance(r["skeleton"], dict) or not isinstance(r["drawn"], dict):
            errs.append(f"{name} #{i}: skeleton/drawn 타입 오류")
    return errs


def card_without_commute(p):
    """통근 문장이 독립 문장으로 정확히 1회 있는지 확인하고 그 한 곳만 제거. 위반 시 (None, 사유)."""
    card, s = p["card"], p["skeleton"].get("commute")
    if not s:
        return (card, None) if "직장은 " not in card else (None, "통근 없음인데 card에 '직장은' 문장")
    token = " " + s
    n = card.count(token)
    if n != 1:
        return None, f"card 안 통근 문장 {n}회"
    pos = card.index(token)
    end = pos + len(token)
    if end != len(card) and card[end] != " ":
        return None, "통근 문장이 문장 경계에서 끝나지 않음"
    return card[:pos] + card[end:], None


def id_tagless(pid):
    parts = pid.split("-")
    return "-".join(parts[:1] + parts[2:]) if len(parts) >= 4 else pid


def compare(a, b, allow_id_change=False):
    errors = validate(a, "A") + validate(b, "B")
    if errors:
        return errors, 0
    if len(a) != len(b):
        return [f"행 수 다름: {len(a)} vs {len(b)}"], 0
    changed, id_changed = 0, 0
    for i, (x, y) in enumerate(zip(a, b)):
        if x["persona_id"] != y["persona_id"]:
            if allow_id_change and id_tagless(x["persona_id"]) == id_tagless(y["persona_id"]):
                id_changed += 1
            else:
                errors.append(f"#{i} persona_id 다름: {x['persona_id']} vs {y['persona_id']} "
                              "(선택지 순서 난수 키가 바뀜 — paired 불가)")
        for k in sorted((set(x) | set(y)) - IGNORED_TOP):
            if (k in x) != (k in y) or x.get(k) != y.get(k):
                errors.append(f"#{i} {k}: {x.get(k, '<없음>')!r} vs {y.get(k, '<없음>')!r}")
        sx = {k: v for k, v in x["skeleton"].items() if k != "commute"}
        sy = {k: v for k, v in y["skeleton"].items() if k != "commute"}
        if sx != sy:
            errors.append(f"#{i} skeleton(통근 외) 다름")
        if bool(x["skeleton"].get("commute")) != bool(y["skeleton"].get("commute")):
            errors.append(f"#{i} 통근 유무 다름")
        cx, ex = card_without_commute(x)
        cy, ey = card_without_commute(y)
        if ex or ey:
            errors.append(f"#{i} card 규칙 위반: A={ex} B={ey}")
        elif cx != cy:
            errors.append(f"#{i} card(통근 문장 제외) 다름")
        px, py = x["provenance"], y["provenance"]
        for k in sorted(set(px) | set(py)):
            if k in PROV_ALLOWED:
                continue
            if (k in px) != (k in py) or px.get(k) != py.get(k):
                errors.append(f"#{i} provenance.{k}: {px.get(k, '<없음>')!r} vs {py.get(k, '<없음>')!r}")
        changed += x["skeleton"].get("commute") != y["skeleton"].get("commute")
        if len(errors) > 20:
            errors.append("… (20건 초과, 중단)")
            break
    prov_a, prov_b = a[0]["provenance"], b[0]["provenance"]
    only = sorted((set(prov_a) ^ set(prov_b)) & PROV_ALLOWED)
    print(f"행 {len(a)} · 통근 문장이 바뀐 행 {changed} · persona_id 동일 {len(a) - id_changed}/{len(a)}"
          + (f" (태그만 다른 ID {id_changed} — 선택지 순서 키 변경 경고)" if id_changed else ""))
    if only:
        print(f"  참고: 한쪽에만 있는 provenance 키 {only} — 구판 환경 정보는 '미확인'")
    return errors, changed


def main():
    args = [a for a in sys.argv[1:] if a != "--allow-id-change"]
    allow = "--allow-id-change" in sys.argv
    if args[:1] == ["--paths"]:
        pa, pb = Path(args[1]), Path(args[2])
    else:
        track, ta, tb = args
        pa = data_dir() / "banks" / f"persona_bank_{track}_{ta}.jsonl"
        pb = data_dir() / "banks" / f"persona_bank_{track}_{tb}.jsonl"
    print(f"A={pa}\nB={pb}")
    errors, _ = compare(load(pa), load(pb), allow_id_change=allow)
    for e in errors:
        print("  DIFF", e)
    print("PASS — paired 동일(통근 문장 외)" if not errors else f"FAIL — {len(errors)}건")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
