# -*- coding: utf-8 -*-
"""EXP-011 사전 체크 7: 블록 간 결합(data fusion)의 CIA 위반 크기 — KGSS 내부 자기검증 ($0).

KGSS 2023 응답자는 정치 블록과 신뢰 블록에 모두 답했다(진짜 결합 = 정답).
가짜 결합: 각 사람의 신뢰 블록을 '다른 사람'(도너)에게서 가져와 붙인다.
  M0 무작위 도너(하한) · M1 인구셀(성×연령10×학력) 매칭 · M2 인구셀+일반 태도(고분산 임의) ·
  M3 인구셀+표적 다리변수(이념·계층의식·정치관심·생활만족·종교 — 프롬프트 미노출, 매칭 전용) ·
  M4 상한: 인구셀 + 신뢰 블록 자체 3문항(부분 관측 가정 — 완벽한 다리의 근사)
지표: 정치×신뢰 블록 간 상관행렬의 보존율(|r|가짜/|r|진짜), |Δr| 평균, 부호 일치율.
"""
import io
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import harmonize as H  # noqa: E402
from engine.registry import data_dir, resolve  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rng = np.random.default_rng(20260914)

df, meta = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
labels = meta.column_names_to_labels
d = df[df["YEAR"] == 2023].reset_index(drop=True)
num = d.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)
inv = pd.read_csv(data_dir() / "kgss_item_inventory.csv")
inv = inv[inv.c2023 >= 0.85]


def ordinal(c):
    if c not in num.columns:
        return False
    s = num[c].dropna()
    return 3 <= s.nunique() <= 10 and s.max() <= 10 and s.std() > 0.5


B1 = [c for c in inv[inv.dom == "정치·정부·민주주의"]["var"] if ordinal(c)][:12]
B2 = [c for c in inv[inv.dom == "신뢰·기관·사회자본"]["var"] if ordinal(c)][:12]
POOL = [c for c in inv[inv.dom.isin(["건강·생활·행복", "기타", "경제·복지·세금·불평등"])]["var"]
        if ordinal(c) and c not in B1 + B2]
GENERIC = sorted(POOL, key=lambda c: -num[c].std())[:6]
BRIDGE_PAT = r"진보.*보수|보수.*진보|계층|정치.*관심|관심.*정치|생활만족|삶.*만족|종교.*(참석|빈도|중요)"
BRIDGE = [c for c in num.columns if c not in B1 + B2 and ordinal(c)
          and re.search(BRIDGE_PAT, labels.get(c) or "")][:6]
print(f"정치 {len(B1)} / 신뢰 {len(B2)} / 일반 매칭 {[labels[c][:12] for c in GENERIC]}")
print(f"표적 다리변수 {[labels[c][:14] for c in BRIDGE]}")

X = num[B1 + B2 + GENERIC + BRIDGE].copy()
ok = X[B1 + B2].notna().sum(axis=1) >= 0.8 * (len(B1) + len(B2))
X = X[ok]
d = d.loc[X.index]
X = X.apply(lambda s: s.fillna(s.median()))
Z = ((X - X.mean()) / X.std()).reset_index(drop=True)
n = len(Z)
cell = np.array([f"{int(r['SEX'])}-{int(r['AGE'])//10}-{H.edu4_kgss(r['EDUC'])}" for _, r in d.iterrows()])
groups = {c: np.where(cell == c)[0] for c in np.unique(cell)}
print(f"분석 대상 {n}명, 인구셀 {len(groups)}개")


def cross_corr(b1, b2):
    return np.corrcoef(np.hstack([b1, b2]).T)[:len(B1), len(B1):]


true_C = cross_corr(Z[B1].values, Z[B2].values)


def fuse(mode, match_cols=None):
    donors = np.empty(n, int)
    M = Z[match_cols].values if match_cols else None
    for i in range(n):
        cand = np.arange(n) if mode == "random" else groups[cell[i]]
        cand = cand[cand != i]
        if len(cand) < 5:
            cand = np.delete(np.arange(n), i)
        if M is not None:
            dist = np.linalg.norm(M[cand] - M[i], axis=1)
            cand = cand[np.argsort(dist)[:5]]  # 최근접 5명 중 무작위 (분산 보존)
        donors[i] = rng.choice(cand)
    return cross_corr(Z[B1].values, Z[B2].values[donors])


print(f"\n진짜 결합: 정치×신뢰 블록 간 |r| 평균 {np.abs(true_C).mean():.3f}, 최대 {np.abs(true_C).max():.3f}")
print(f"{'결합 방식':28} {'|r|평균':>7} {'보존율':>6} {'|Δr|':>6} {'부호일치':>7}")
runs = [("M0 무작위 도너", "random", None), ("M1 인구셀 매칭", "cell", None),
        ("M2 +일반 태도 6", "cell", GENERIC), ("M3 +표적 다리변수", "cell", BRIDGE),
        ("M4 상한: +신뢰블록 자체 3", "cell", B2[:3])]
for name, mode, cols in runs:
    Cs = np.mean([fuse(mode, cols) for _ in range(5)], axis=0)
    print(f"{name:28} {np.abs(Cs).mean():7.3f} {np.abs(Cs).mean()/np.abs(true_C).mean():6.0%} "
          f"{np.abs(true_C-Cs).mean():6.3f} {np.mean(np.sign(true_C)==np.sign(Cs)):7.0%}")
print("\n해석: 보존율 = 가짜 결합이 진짜 블록 간 상관을 얼마나 남기나. M4는 이음매 블록을 일부 관측한 상한.")
