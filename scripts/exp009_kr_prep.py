# -*- coding: utf-8 -*-
"""EXP-009 한국장 prep ($0): 웨이브별 페르소나 + 3암 프로필 + 문항 스펙 동결.

산출 (data/exp009/):
  kr_personas.jsonl  웨이브별 300명 × {demo, full_lines} (시드 고정)
  kr_items.json      앵커 + 위약 7쌍의 A/B 렌더 스펙 (질문 틀·선택지 순서 동결)

문항 틀 주의(개정 4에 기록): KGSS 코드북 원문 미확보 — 질문 캐리어 문장은 중립 재구성,
처치 어구(무작위/1천/1만)와 선택지 문구·순서는 .sav 값 라벨 원문 그대로.
프로필: exp009_kr_profile_exclude.csv(200변수) + EXP-008 y-인접 패턴 + 인구·관리 변수 제외.
"""
import io
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

from engine.registry import data_dir, resolve  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = data_dir() / "exp009"
OUT.mkdir(exist_ok=True)
SEED = 20260828
N_PER_WAVE = 300

df, meta = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
labels = meta.column_names_to_labels
vlabels = meta.variable_value_labels

# ── 제외 목록 ──
exclude = set(pd.read_csv(data_dir() / "exp009_kr_profile_exclude.csv")["var"])
Y_PAT = ["투표", "정당", "대선", "대통령", "선거", "지지", "총선"]
y_adj = {n for n in df.columns
         if n in ("PARTYLR", "LEFTRIGT")
         or any(p in (labels.get(n) or "") for p in Y_PAT)
         or any(k in n.upper() for k in ["VOTE", "PRTY", "PARTY", "ELEC", "PRES"])}
ADMIN_PAT = ["ID", "WT", "WEIGHT", "MODE", "INTV", "DATE", "MONTH", "AREA", "SIZE", "YEAR"]
DEMO_VARS = {"SEX", "AGE", "EDUC", "MARITAL", "REGION", "INCOM", "RINCOM", "INCOME",
             "BIRTH", "HOMPOP", "TENURE", "DWELL"}
DEMO_LABEL = re.compile(r"몇 세|만 나이|성별|최종 학력|교육 수준|혼인 상태|태어|출생|가구원|거주")


def is_admin(n):
    return any(p in n.upper() for p in ADMIN_PAT)


def is_demo(n):
    return n in DEMO_VARS or any(n.upper().startswith(v) for v in DEMO_VARS) \
        or bool(DEMO_LABEL.search(labels.get(n) or ""))


def vlabel(var, v):
    m = vlabels.get(var)
    if m and v in m:
        return str(m[v]).strip()
    if m and float(v) in m:
        return str(m[float(v)]).strip()
    return str(int(v))


def render_item(var, v):
    lab = vlabel(var, v)
    m = vlabels.get(var) or {}
    if lab == str(int(v)) and m:
        ks = sorted(k for k in m if isinstance(k, (int, float)) and k >= 0)
        if ks:
            return (f"- {labels.get(var, var)}: {int(v)} "
                    f"({int(ks[0])}={str(m[ks[0]]).strip()} ~ {int(ks[-1])}={str(m[ks[-1]]).strip()})")
    return f"- {labels.get(var, var)}: {lab}"


def demo_text(row):
    sex = "남성" if int(row["SEX"]) == 1 else "여성"
    parts = [f"{int(row['AGE'])}세 {sex}"]
    for var, name in [("REGION", "거주지역"), ("EDUC", "학력"), ("MARITAL", "혼인상태")]:
        if var in row and pd.notna(row[var]) and row[var] >= 0:
            parts.append(f"{name}: {vlabel(var, row[var])}")
    return ", ".join(parts)


# ── 문항 스펙 (동결) ──
def opts_from(var):
    """값 라벨(양수 코드)에서 선택지 순서·문구 원문 그대로."""
    m = vlabels.get(var) or {}
    return [{"v": int(k), "label": str(m[k]).strip()} for k in sorted(m) if k >= 1]


anchor = json.load(open(data_dir() / "exp009_kr_anchor.json", encoding="utf-8"))
ITEMS = {
    "ANCHOR": {
        "wave": 2023, "arms": ["NOPROF", "DEMO", "FULL"], "kind": "anchor",
        "date_anchor": "지금은 2023년 여름입니다.",
        "A": {"q": anchor["wording_A_NBS"]["question"],
              "opts": [{"v": int(k), "label": v} for k, v in anchor["wording_A_NBS"]["options"].items()]},
        "B": {"q": anchor["wording_B_Gallup"]["question"],
              "opts": [{"v": int(k), "label": v} for k, v in anchor["wording_B_Gallup"]["options"].items()]},
    },
    "SAMPTHOU23": {
        "wave": 2023, "arms": ["NOPROF", "DEMO", "FULL"], "kind": "strong_placebo",
        "date_anchor": "지금은 2023년입니다.",
        "A": {"q": "우리나라에서 전국 무작위 1,000명을 대상으로 실시한 여론조사를 통해 국민 전체의 여론을 정확히 알 수 있다고 생각하십니까, 아니면 알 수 없다고 생각하십니까?",
              "opts": opts_from("SAMPTHOUA")},
        "B": {"q": "우리나라에서 전국 1,000명을 대상으로 실시한 여론조사를 통해 국민 전체의 여론을 정확히 알 수 있다고 생각하십니까, 아니면 알 수 없다고 생각하십니까?",
              "opts": opts_from("SAMPTHOUB23")},
    },
    "NUKPLT18": {
        "wave": 2018, "arms": ["NOPROF", "DEMO", "FULL"], "kind": "strong_placebo",
        "date_anchor": "지금은 2018년입니다.",
        "A": {"q": "우리나라의 원자력 발전 정책이 앞으로 어떤 방향으로 나아가야 한다고 생각하십니까?",
              "opts": opts_from("NUKPLT10A")},
        "B": {"q": "우리나라의 원자력 발전 정책이 앞으로 어떤 방향으로 나아가야 한다고 생각하십니까?",
              "opts": opts_from("NUKPLT10B")},
    },
    "NUKPLT21": {
        "wave": 2021, "arms": ["DEMO"], "kind": "weak_placebo",
        "date_anchor": "지금은 2021년입니다.",
        "A": {"q": "우리나라의 원자력 발전 정책이 앞으로 어떤 방향으로 나아가야 한다고 생각하십니까?",
              "opts": opts_from("NUKPLT10A")},
        "B": {"q": "우리나라의 원자력 발전 정책이 앞으로 어떤 방향으로 나아가야 한다고 생각하십니까?",
              "opts": opts_from("NUKPLT10B")},
    },
    "PROUD21": {
        "wave": 2021, "arms": ["DEMO"], "kind": "weak_placebo",
        "date_anchor": "지금은 2021년입니다.",
        "A": {"q": "선생님께서는 한국의 민주주의에 대해 어느 정도 자랑스럽게 생각하십니까?",
              "opts": opts_from("PROUDDEM16A")},
        "B": {"q": "선생님께서는 한국의 민주주의에 대해 어느 정도 자랑스럽게 생각하십니까?",
              "opts": opts_from("PROUDDEM16B")},
    },
    "ELEFRAUD25": {
        "wave": 2025, "arms": ["DEMO"], "kind": "weak_placebo",
        "date_anchor": "지금은 2025년입니다.",
        "A": {"q": "최근 제기된 부정선거 의혹에 대해 어떻게 생각하십니까?",
              "opts": opts_from("ELEFRAUDA")},
        "B": {"q": "최근 제기된 부정선거 의혹에 대해 어떻게 생각하십니까?",
              "opts": opts_from("ELEFRAUDB")},
    },
    "LAWHARSH25": {
        "wave": 2025, "arms": ["DEMO"], "kind": "weak_placebo",
        "date_anchor": "지금은 2025년입니다.",
        "A": {"q": "우리나라 법원의 범죄자 처벌에 대해 어떻게 생각하십니까?",
              "opts": opts_from("LAWHARSHA")},
        "B": {"q": "우리나라 법원의 범죄자 처벌에 대해 어떻게 생각하십니까?",
              "opts": opts_from("LAWHARSHB")},
    },
    "SAMPTNTH25": {
        "wave": 2025, "arms": ["DEMO"], "kind": "weak_placebo",
        "date_anchor": "지금은 2025년입니다.",
        "A": {"q": "우리나라에서 전국 무작위 1,000명을 대상으로 실시한 여론조사를 통해 국민 전체의 여론을 정확히 알 수 있다고 생각하십니까, 아니면 알 수 없다고 생각하십니까?",
              "opts": opts_from("SAMPTHOUA")},
        "B": {"q": "우리나라에서 전국 무작위 10,000명을 대상으로 실시한 여론조사를 통해 국민 전체의 여론을 정확히 알 수 있다고 생각하십니까, 아니면 알 수 없다고 생각하십니까?",
              "opts": opts_from("SAMPTNTHB25")},
    },
}
json.dump(ITEMS, io.open(OUT / "kr_items.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ── 웨이브별 페르소나 ──
num_all = df.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)
waves = sorted({it["wave"] for it in ITEMS.values()})
need_full = {it["wave"] for it in ITEMS.values() if "FULL" in it["arms"]}
with io.open(OUT / "kr_personas.jsonl", "w", encoding="utf-8") as f:
    for wv in waves:
        dw = df[df["YEAR"] == wv].reset_index(drop=True)
        numw = num_all[df["YEAR"] == wv].reset_index(drop=True)
        pool_vars = [c for c in dw.columns
                     if not is_admin(c) and not is_demo(c)
                     and c not in exclude and c not in y_adj
                     and numw[c].notna().mean() >= 0.30]
        ok = dw.index[dw["SEX"].notna() & dw["AGE"].notna()
                      & (numw[pool_vars].notna().sum(axis=1) >= 30)].tolist()
        if wv == 2023:
            # 등록 규격: 2023 앵커 페르소나 = EXP-008 평가셋 300명 그대로 (pid e23_{i}, seed 42)
            e8 = [json.loads(l) for l in open(data_dir() / "exp008" / "profiles.jsonl",
                                              encoding="utf-8")]
            pick = sorted(int(p["pid"].split("_")[1]) for p in e8)
            assert len(pick) == N_PER_WAVE, f"EXP-008 평가셋 {len(pick)}명 != {N_PER_WAVE}"
        else:
            rng = random.Random(f"{SEED}-{wv}")
            pick = sorted(rng.sample(ok, min(N_PER_WAVE, len(ok))))
        n_items = []
        for i in pick:
            row = dw.loc[i]
            prng = random.Random(f"{SEED}-{wv}-{i}")
            valid = [c for c in pool_vars if pd.notna(numw.loc[i, c])]
            prng.shuffle(valid)
            full = ([render_item(c, numw.loc[i, c]) for c in valid] if wv in need_full else [])
            n_items.append(len(valid))
            f.write(json.dumps({"pid": f"k{wv}_{i}", "wave": wv, "demo": demo_text(row),
                                "full_lines": full}, ensure_ascii=False) + "\n")
        med = sorted(n_items)[len(n_items) // 2] if n_items else 0
        print(f"{wv}: 풀 {len(pool_vars)}문항, 적격 {len(ok)}명 → {len(pick)}명 "
              f"(프로필 중앙값 {med}문항, FULL렌더 {'O' if wv in need_full else 'X'})")

calls = sum(N_PER_WAVE * len(it["arms"]) * 2 * 3 for it in ITEMS.values())
print(f"예상 호출: {calls:,}콜 (gpt-4o-mini)")
print("DONE")
