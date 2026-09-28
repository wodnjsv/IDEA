"""ISS-033 A1: v1 뱅크의 통근 오역을 원자료 없이 역변환 재라벨해 새 파일(v2)을 만든다.

    python3 scripts/relabel_bank_commute.py national v1 v2
    python3 scripts/relabel_bank_commute.py gwangmyeong v1 v2
    python3 scripts/compare_bank_versions.py national v1 v2

v1 통근 문장은 코드집 40번의 두 값에 1:1로 대응한다('자기 집'=1, '현재 사는 시군구'=2 — harmonize.V1_COMMUTE_TO_CODE).
바꾸는 것은 skeleton.commute와 card 안의 그 한 문장, provenance(tag·출처·규칙)뿐이다.
persona_id·drawn·weight·나머지 문장은 그대로 둔다 — persona_id가 선택지 순서 난수 키이므로(prompts_t3.persona_order)
ID를 유지해야 v1↔v2가 통근 문장만 다른 paired 쌍이 된다. 41번(타시도 목적지)은 v1에 없어 복원하지 않는다(A2는 원자료 재빌드).
API·원자료·numpy 불요. 출력은 배타 생성(기존 파일 덮어쓰기 거부).
"""
import hashlib
import json
import platform
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import harmonize as H  # noqa: E402
from engine.registry import data_dir  # noqa: E402

V1_PAT = re.compile(r"^직장은 (.+?)에 있(?:고 통근에 약 (\d+)분 걸립니다|습니다)\.$")


def relabel(p):
    """한 페르소나를 A1 규칙으로 재라벨한 사본. 해석 불가·카드 불일치면 ValueError."""
    q = json.loads(json.dumps(p, ensure_ascii=False))
    old = p["skeleton"].get("commute")
    if not old:
        if "직장은 " in p["card"]:
            raise ValueError(f"{p['persona_id']}: 통근 없음인데 card에 '직장은' 문장 존재")
        return q
    m = V1_PAT.match(old)
    if not m or m.group(1) not in H.V1_COMMUTE_TO_CODE:
        raise ValueError(f"{p['persona_id']}: v1 통근 문장 해석 불가 {old!r}")
    if p["card"].count(" " + old) != 1:
        raise ValueError(f"{p['persona_id']}: card 안 통근 문장이 정확히 1회가 아님")
    new = H.commute_label("1", H.V1_COMMUTE_TO_CODE[m.group(1)], "", m.group(2) or "", p["skeleton"]["sido"])
    q["skeleton"]["commute"] = new
    q["card"] = p["card"].replace(" " + old, " " + new, 1)
    return q


def main():
    track, src_tag, dst_tag = sys.argv[1:4]
    src = data_dir() / "banks" / f"persona_bank_{track}_{src_tag}.jsonl"
    dst = data_dir() / "banks" / f"persona_bank_{track}_{dst_tag}.jsonl"
    raw = src.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if not rows:
        sys.exit(f"거부: {src} 비어 있음")
    src_sha = hashlib.sha256(raw).hexdigest()
    out, changed = [], 0
    for p in rows:
        q = relabel(p)
        changed += q["skeleton"].get("commute") != p["skeleton"].get("commute")
        q["provenance"] = dict(p["provenance"], tag=dst_tag, commute_rule=H.COMMUTE_RULE_A1,
                               derived_from={"file": src.name, "sha256": src_sha},
                               relabel={"script": "scripts/relabel_bank_commute.py", "issue": "ISS-033 A1",
                                        "python": platform.python_version()})
        out.append(q)
    try:
        f = open(dst, "x", encoding="utf-8")
    except FileExistsError:
        sys.exit(f"거부: {dst} 이미 존재 — 덮어쓰지 않음")
    with f:
        for q in out:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    print(f"[{track}] {src.name} → {dst.name}: {len(out)}명, 통근 문장 교체 {changed}건 (src sha256 {src_sha[:12]}…)")


if __name__ == "__main__":
    main()
