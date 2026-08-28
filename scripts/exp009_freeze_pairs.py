# -*- coding: utf-8 -*-
"""EXP-009 사전 체크 ②④: 미국장 최종 동결표 생성 + 쌍당 n 모의계산 (개정 2 ①~④의 산출 코드).

수동 심사 결과(개정 2 ① — 후보 88+60 전수, 자극 diff·원문·조건별 응답분포 대조)를 코드로 고정:
  실측 17(순수 표현·제시형) + 참고 1(정보제공형, 본판정 미산입) + 위약 20.
  구제 3건(yp736/kv3sd/xweq8)은 같은 스터디의 본 문항 좌표로 교체(조작확인·불일치 회피).
  j6xgs는 방향반전 쌍 — 정렬 focal(+5.0%p, B판 8-x 재코딩) 기준.
몬테카를로(2만 회): 민감도 게이트 P(방향일치>=13/17) × 재현율 τ × 쌍당 n → 차등 120/300 채택.
위약 오탐 분포(쌍별 양측 5%) → 특이도 게이트 "오탐<=3/20" 확정.
산출: data/exp009_us_pairs_frozen.csv
"""
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from engine.registry import data_dir

rng = np.random.default_rng(20260828)
OUT = data_dir()
rc = pd.read_csv(OUT / "exp009_us_real_candidates.csv")
nc = pd.read_csv(OUT / "exp009_us_null_candidates.csv")


def from_csv(pool, study, task):
    r = pool[(pool.study == study) & (pool.task == task)].iloc[0]
    return dict(study=study, task=int(task), condA=int(r.condA), condB=int(r.condB),
                focal_cat=int(r.focal_cat), human_pp=float(r.focal_pp),
                nA=int(r.nA), nB=int(r.nB))


REAL = [
    (from_csv(rc, "s43kb", 5), "톤-정중/거침", None),
    (from_csv(rc, "s2rd5", 0), "워딩-정의추가", None),
    (from_csv(rc, "ye2ej", 5), "라벨-인물성별", None),
    (from_csv(rc, "ar9e3", 0), "워딩-질문문구", None),
    (from_csv(rc, "xym9d", 1), "워딩-초당파", None),
    (dict(study="kv3sd", task=1, condA=0, condB=1, focal_cat=5, human_pp=13.0,
          nA=1718, nB=1702), "라벨-채권기관", None),
    (from_csv(rc, "fct42", 1), "라벨-용어(racism)", None),
    (dict(study="yp736", task=0, condA=1, condB=2, focal_cat=0, human_pp=7.0,
          nA=1286, nB=1307), "단서-정파", None),
    (from_csv(rc, "4rqy5", 0), "워딩-묘사추가", None),
    (from_csv(rc, "m52pd", 5), "라벨-이름성별", None),
    (from_csv(rc, "zsekp", 2), "형식-숫자/문자등급", None),
    (from_csv(rc, "j38gd", 0), "워딩-무의견옵션", None),
    (from_csv(rc, "fxcn4", 3), "라벨-인종정체성", None),
    (dict(study="xweq8", task=1, condA=0, condB=3, focal_cat=1, human_pp=-6.5,
          nA=1577, nB=1647), "워딩-집단명시", None),
    (from_csv(rc, "52ymc", 3), "워딩-성별단어", None),
    (from_csv(rc, "xtvu5", 0), "워딩-맥락명시", None),
    (dict(study="j6xgs", task=0, condA=0, condB=1, focal_cat=2, human_pp=5.0,
          nA=1179, nB=1190), "워딩-방향반전", "reverse_B(8-x)"),
]
REF = [(from_csv(rc, "ak35q", 8), "정보-가격공개(참고)", None)]
NULL_LIST = [("nb4xg", 0, "라벨-인종"), ("a7uk3", 4, "라벨-정당"), ("ejms3", 1, "라벨-정당"),
             ("kwfs3", 0, "라벨-집단명"), ("egmxd", 0, "형식-라벨종류"), ("xfmrn", 1, "워딩-리마인더"),
             ("3bzxg", 2, "워딩-주의문구"), ("hz5rt", 0, "내용-논거문장"), ("nj5dx", 5, "프레임-특권/불리"),
             ("e2pyb", 1, "프레임-격차종류"), ("q8ra3", 0, "프레임-국제/미국"), ("rs65g", 0, "내용-가격옵션"),
             ("v6kqy", 1, "내용-차종"), ("dehmv", 0, "내용-후보속성"), ("waq4m", 0, "내용-논거문단"),
             ("c38xe", 2, "내용-후보속성"), ("b3ve6", 0, "내용-프로필속성"), ("ervm8", 0, "워딩-검증안내"),
             ("3jwnf", 2, "프레임-피해자집단"), ("jmtyn", 4, "내용-정책서술")]
NULL = [(from_csv(nc, s, t), f"{typ}(위약)", None) for s, t, typ in NULL_LIST]

top10 = {d["study"] for d, _, _ in
         sorted(REAL, key=lambda x: -abs(x[0]["human_pp"]))[:10]}  # 무프로필판(개정 1-3): |Δ| 상위 10쌍
rows = []
for role, items in [("real", REAL), ("ref", REF), ("null", NULL)]:
    for d, typ, align in items:
        n_llm = 120 if (role != "real" or abs(d["human_pp"]) >= 10) else 300
        rows.append({**d, "role": role, "subtype": typ, "align_rule": align or "",
                     "n_llm_per_cond": n_llm,
                     "noprofile_arm": role == "real" and d["study"] in top10})
F = pd.DataFrame(rows)[["role", "study", "task", "condA", "condB", "subtype", "focal_cat",
                        "human_pp", "nA", "nB", "align_rule", "n_llm_per_cond", "noprofile_arm"]]
assert len(F) == 38 and F.study.nunique() == 38, f"쌍 수/중복 오류: {len(F)}/{F.study.nunique()}"
F.to_csv(OUT / "exp009_us_pairs_frozen.csv", index=False, encoding="utf-8-sig")
print(f"동결표 저장: 실측 {sum(F.role=='real')} + 참고 {sum(F.role=='ref')} + 위약 {sum(F.role=='null')}"
      f" | 무프로필판 {int(F.noprofile_arm.sum())}쌍")

# ---------- 몬테카를로 (개정 2 ③) ----------
d_real = F[F.role == "real"]["human_pp"].abs().values
P0, NSIM, GATE = 0.5, 20000, 13


def sim_pass(n_small, n_big, tau, split=10.0):
    ns = np.where(d_real >= split, n_small, n_big)
    hits = np.zeros(NSIM)
    for d, n in zip(d_real, ns):
        pa = np.clip(P0 + tau * d / 200, 0.01, 0.99)
        pb = np.clip(P0 - tau * d / 200, 0.01, 0.99)
        hits += (rng.binomial(n, pa, NSIM) - rng.binomial(n, pb, NSIM)) > 0
    return (hits >= GATE).mean()


print("\n민감도 게이트(>=13/17) 통과확률:")
print(f"{'설계':16} τ=0.3  τ=0.5  τ=0.7  τ=1.0")
for name, ns_, nb_ in [("균일 80(원안)", 80, 80), ("균일 120", 120, 120),
                       ("균일 300", 300, 300), ("차등 120/300", 120, 300)]:
    r = [sim_pass(ns_, nb_, t) for t in (0.3, 0.5, 0.7, 1.0)]
    print(f"{name:16} {r[0]:.2f}   {r[1]:.2f}   {r[2]:.2f}   {r[3]:.2f}")

n = 120
pa = rng.binomial(n, P0, (NSIM, 20)) / n
pb = rng.binomial(n, P0, (NSIM, 20)) / n
fp = (np.abs((pa - pb) / np.sqrt(2 * P0 * (1 - P0) / n)) > norm.ppf(0.975)).sum(axis=1)
print(f"\n위약 오탐(n=120, 참효과 0): 평균 {fp.mean():.2f}개, P(<=3)={np.mean(fp<=3):.3f} → 게이트 '오탐<=3'")

ns = np.where(d_real >= 10, 120, 300)
calls = ns.sum() * 6 + 120 * 6 + 20 * 120 * 6 + int(F.noprofile_arm.sum()) * 120 * 6
print(f"총 호출(2조건×k3): {calls:,}콜 → 12rpm {calls/720:.0f}h / 20rpm {calls/1200:.0f}h")
print("DONE")
