"""통근 라벨(ISS-033) 자체검증 — 원자료·numpy·API 없이 돌아간다.

    python3 scripts/selftest_bank_commute.py

[1] harmonize.commute_label 단위 검사 (코드집 39·40·41번)
[2] 시도 전체명 17개를 코드집 41번 코드표와 전부 대조
[3] 저장 v1 뱅크 재해석: 전체 행·통근 대상 수를 독립 계수하고 고정 기대값과 대조
[4] A1 재라벨(relabel_bank_commute.relabel)과 paired 비교기(compare_bank_versions.compare)의 양성·음성 대조군

한계: bank.py의 load_pool→build_bank 통합 경로(판다스 행·NaN·열 누락)는 여기서 검사하지 않는다 — 원자료·numpy 필요(ISS-039).
"""
import copy
import io
import json
import sys
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from engine import harmonize as H  # noqa: E402  (numpy·pandas 불요)
from engine.registry import data_dir  # noqa: E402
from relabel_bank_commute import relabel  # noqa: E402
from compare_bank_versions import compare  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ((" — " + detail) if detail else ""))
    if not cond:
        FAIL.append(name)


print("[1] 단위 검사 — commute_label(gubun, place, other_sido, minutes, home_sido)")
L = H.commute_label
check("40=1 같은 읍면동", L("1", "1", "", "15", "31") == "직장은 사는 곳과 같은 읍·면·동에 있고 통근에 약 15분 걸립니다.")
check("40=2 + 41=서울 (광명 거주)", L("1", "2", "11", "50", "31") == "직장은 서울특별시에 있고 통근에 약 50분 걸립니다.")
check("40=2 + 41 공란 → 시도 단정 안 함", L("1", "2", "", "30", "31") == "직장은 사는 곳과 다른 읍·면·동에 있고 통근에 약 30분 걸립니다.")
check("40=2 + 41=거주 시도 → 공란 취급", L("1", "2", "31", "30", "31") == "직장은 사는 곳과 다른 읍·면·동에 있고 통근에 약 30분 걸립니다.")
check("40=2 + 41=미지 코드 → 공란 취급", L("1", "2", "99", "30", "31") == "직장은 사는 곳과 다른 읍·면·동에 있고 통근에 약 30분 걸립니다.")
check("40=1이면 41 값이 있어도 무시", L("1", "1", "11", "15", "31") == "직장은 사는 곳과 같은 읍·면·동에 있고 통근에 약 15분 걸립니다.")
check("분 결측 → 시간 생략", L("1", "1", "", "", "11") == "직장은 사는 곳과 같은 읍·면·동에 있습니다.")
check("분 0 → 시간 생략", L("1", "2", "11", "0", "31") == "직장은 서울특별시에 있습니다.")
check("분 소수 문자열", L("1", "1", "", "12.0", "11") == "직장은 사는 곳과 같은 읍·면·동에 있고 통근에 약 12분 걸립니다.")
check("분 비수치 → 시간 생략", L("1", "1", "", "abc", "11") == "직장은 사는 곳과 같은 읍·면·동에 있습니다.")
check("39=2 통학 → None (v1과 같은 범위)", L("2", "1", "", "10", "11") is None)
check("39=3 안함 → None", L("3", "", "", "", "11") is None)
check("39 결측 → None", L("", "1", "", "10", "11") is None)
check("40 결측 → None (v1도 None)", L("1", "", "", "10", "11") is None)
check("40 미지 코드 → None (v1은 '직장은 에 있고' 가능)", L("1", "3", "", "10", "11") is None)
check("COMMUTE_PLACE는 코드집 2값뿐", set(H.COMMUTE_PLACE) == {"1", "2"})
check("오역 문구 부재", not any(w in "".join(H.COMMUTE_PLACE.values()) for w in ["자기 집", "시군구"]))

print("[2] 시도 전체명 — 코드집 41번 코드표(sheet1 162-178행) 전수 대조")
CODEBOOK_41 = {"11": "서울특별시", "21": "부산광역시", "22": "대구광역시", "23": "인천광역시", "24": "광주광역시",
               "25": "대전광역시", "26": "울산광역시", "29": "세종특별자치시", "31": "경기도", "32": "강원도",
               "33": "충청북도", "34": "충청남도", "35": "전라북도", "36": "전라남도", "37": "경상북도",
               "38": "경상남도", "39": "제주특별자치도"}
check("SIDO_FULLNAME == 코드집 41번 17개", H.SIDO_FULLNAME == CODEBOOK_41,
      str({k: (H.SIDO_FULLNAME.get(k), v) for k, v in CODEBOOK_41.items() if H.SIDO_FULLNAME.get(k) != v}))
check("SIDO_NAME과 같은 코드 집합", set(H.SIDO_FULLNAME) == set(H.SIDO_NAME))

print("[3] 저장 v1 재해석 — 독립 계수 + 고정 기대값 (AUDIT-2026-09-23-ISS033 §1.1)")
EXPECT = {"national": {"rows": 5000, "commuters": 2768, "자기 집": 1542, "현재 사는 시군구": 1226},
          "gwangmyeong": {"rows": 4568, "commuters": 2606, "자기 집": 882, "현재 사는 시군구": 1724}}
banks = {}
for track, exp in EXPECT.items():
    path = data_dir() / "banks" / f"persona_bank_{track}_v1.jsonl"
    print(f"  경로: {path}")
    if not path.exists():
        check(f"{track} v1 파일 존재", False)
        continue
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    banks[track] = rows
    commuters = sum(1 for p in rows if p["skeleton"].get("commute"))            # 독립 계수 1
    labels = Counter(p["skeleton"]["commute"].split("에 있")[0].replace("직장은 ", "")
                     for p in rows if p["skeleton"].get("commute"))             # 독립 계수 2
    check(f"{track}: 행 수 {exp['rows']}", len(rows) == exp["rows"], str(len(rows)))
    check(f"{track}: 통근 대상 {exp['commuters']}", commuters == exp["commuters"], str(commuters))
    check(f"{track}: v1 라벨 분포 고정값", labels == Counter({k: exp[k] for k in ("자기 집", "현재 사는 시군구")}),
          str(dict(labels)))
    ok, bad = 0, 0
    for p in rows:
        try:
            q = relabel(p)
            ok += bool(q["skeleton"].get("commute"))
        except ValueError:
            bad += 1
    check(f"{track}: A1 재라벨 성공 {exp['commuters']}건·실패 0", ok == exp["commuters"] and bad == 0, f"성공 {ok} 실패 {bad}")

print("[4] 재라벨 + 비교기 — 양성·음성 대조군 (v1 앞 60행 사본, 파일 쓰기 없음)")
if "national" in banks:
    a = banks["national"][:60]
    b = [relabel(p) for p in a]
    for q in b:
        q["provenance"] = dict(q["provenance"], tag="v2", commute_rule=H.COMMUTE_RULE_A1)

    def run(x, y, **kw):
        with redirect_stdout(io.StringIO()):
            errs, changed = compare(x, y, **kw)
        return errs, changed

    errs, changed = run(a, b)
    check("양성: 재라벨본은 PASS", not errs and changed == sum(bool(p["skeleton"]["commute"]) for p in a),
          f"오류 {errs[:2]} 교체 {changed}")
    check("재라벨본에 오역 문구 없음", not any(("자기 집" in q["card"] or "시군구에" in q["card"]) for q in b))

    def neg(label, mutate, **kw):
        y = copy.deepcopy(b)
        mutate(y)
        errs, _ = run(a, y, **kw)
        check(f"음성: {label} → FAIL", bool(errs), errs[0] if errs else "통과해 버림")

    i = next(k for k, p in enumerate(b) if p["skeleton"]["commute"])
    neg("drawn 값 변경", lambda y: y[3]["drawn"].__setitem__("hh_income_decile", -1))
    neg("통근 외 card 문구 변경", lambda y: y[5].__setitem__("card", y[5]["card"] + " 추가"))
    neg("card에서 통근 문장 누락", lambda y: y[i].__setitem__("card", y[i]["card"].replace(" " + y[i]["skeleton"]["commute"], "")))
    neg("card에 통근 문장 중복", lambda y: y[i].__setitem__("card", y[i]["card"] + " " + y[i]["skeleton"]["commute"]))
    neg("persona_id 태그 변경", lambda y: y[0].__setitem__("persona_id", y[0]["persona_id"].replace("-v1-", "-v2-")))
    neg("provenance.seed 변경", lambda y: y[0]["provenance"].__setitem__("seed", 7))
    neg("weight_bank 누락", lambda y: [p.pop("weight_bank") for p in y])
    neg("행 누락", lambda y: y.pop())
    errs, _ = run([], [])
    check("음성: 빈 입력 → FAIL", bool(errs))
    y = copy.deepcopy(b)
    y[0]["persona_id"] = y[0]["persona_id"].replace("-v1-", "-v2-")
    errs, _ = run(a, y, allow_id_change=True)
    check("--allow-id-change: 태그만 다른 ID는 허용", not errs, str(errs[:1]))

print(f"\n{'PASS' if not FAIL else 'FAIL'} — 실패 {len(FAIL)}건" + (f": {FAIL}" if FAIL else ""))
sys.exit(1 if FAIL else 0)
