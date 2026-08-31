# -*- coding: utf-8 -*-
"""EXP-009 미국장 prep: 동결표 38쌍 → 런타임 쌍 스펙 + 페르소나 샘플.

산출 (data/exp009/):
  us_pairs_runtime.jsonl  쌍별 자극 전문(A/B)·유효 응답범위·역할·n·무프로필 여부
  us_personas.jsonl       쌍별 시드 고정 샘플 페르소나(원연구 응답자 demographic 16속성)
설계(개정 2): paired — 같은 페르소나에게 A/B 자극 각각 독립 호출 × k3.
유효범위 = 인간 응답 관측 범주(0~20 내) — 파서 검증용.
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.registry import data_dir, resolve

SEED = 20260828
OUT = data_dir() / "exp009"
OUT.mkdir(exist_ok=True)

F = pd.read_csv(data_dir() / "exp009_us_pairs_frozen.csv", keep_default_na=False)  # role="null" 문자열 보존
SRC = resolve("socsci210")
shards = sorted(SRC.rglob("*.parquet"))
cols = ["study_id", "task_num", "condition_num", "response", "stimuli", "participant", "demographic"]
df = pd.concat([pd.read_parquet(p, columns=cols) for p in shards], ignore_index=True)
df = df[df.study_id.isin(set(F.study))]
print(f"대상 스터디 행: {len(df):,}")

rng = np.random.default_rng(SEED)
DEMO_ORDER = ["age", "gender", "ethnicity", "education", "employment", "income", "location",
              "metro_status", "marital_status", "household_size", "housing_type",
              "housing_ownership", "internet_access", "phone_service", "ideology", "party_id"]


def demo_str(d):
    if isinstance(d, str):
        d = json.loads(d.replace("'", '"')) if d.startswith("{") else {}
    parts = []
    for k in DEMO_ORDER:
        v = d.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        parts.append(f"{k.replace('_', ' ')}: {v}")
    return "; ".join(parts)


pairs_f = open(OUT / "us_pairs_runtime.jsonl", "w", encoding="utf-8")
pers_f = open(OUT / "us_personas.jsonl", "w", encoding="utf-8")
n_pers_total = 0
for _, r in F.iterrows():
    g = df[(df.study_id == r.study) & (df.task_num == r.task)]
    A = g[g.condition_num == r.condA]
    B = g[g.condition_num == r.condB]
    stimA, stimB = str(A["stimuli"].iloc[0]), str(B["stimuli"].iloc[0])
    resp = pd.concat([A["response"], B["response"]]).dropna()
    cats = sorted(v for v in resp.unique() if 0 <= v <= 20)
    lo, hi = int(min(cats)), int(max(cats))
    pairs_f.write(json.dumps({
        "study": r.study, "task": int(r.task), "condA": int(r.condA), "condB": int(r.condB),
        "role": r.role, "subtype": r.subtype, "focal_cat": int(r.focal_cat),
        "human_pp": float(r.human_pp), "align_rule": r.align_rule if isinstance(r.align_rule, str) else "",
        "valid_lo": lo, "valid_hi": hi, "n_llm": int(r.n_llm_per_cond),
        "noprofile_arm": bool(r.noprofile_arm), "stimA": stimA, "stimB": stimB,
    }, ensure_ascii=False) + "\n")

    # 페르소나: 스터디 전체 응답자(조건 무관 — 배정 독립) 중 시드 고정 샘플
    pool = df[df.study_id == r.study][["participant", "demographic"]].drop_duplicates("participant")
    n = min(int(r.n_llm_per_cond), len(pool))
    idx = rng.choice(len(pool), size=n, replace=False)
    for pid, d in pool.iloc[idx].itertuples(index=False):
        pers_f.write(json.dumps({"study": r.study, "persona_id": f"p{pid}",
                                 "demo": demo_str(d)}, ensure_ascii=False) + "\n")
    n_pers_total += n
    if n < int(r.n_llm_per_cond):
        print(f"  주의: {r.study} 풀 {len(pool)}명 < 목표 {r.n_llm_per_cond} → 전원 사용")
pairs_f.close()
pers_f.close()

K = 3
n_np = int(F.noprofile_arm.sum())
calls = n_pers_total * 2 * K + n_np * 120 * 2 * K
print(f"쌍 38개 저장 | 페르소나 총 {n_pers_total}명 | 예상 호출 {calls:,}콜 "
      f"(프로필판 {n_pers_total*2*K:,} + 무프로필판 {n_np*120*2*K:,})")
print("DONE")
