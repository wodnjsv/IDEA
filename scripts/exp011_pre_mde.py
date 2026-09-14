# -*- coding: utf-8 -*-
"""EXP-011 사전 체크 6: H4(하류 동등성) 등가마진 검정력 — 분포 채널 실측 분산으로 모의계산 (벡터화).

가짜 살 n vs 진짜 살 n (독립 인물 집합). 지표: 워딩 델타 차 ≤ 3%p, 집단 분포 TVD ≤ .05.
분산 소스: EXP-010 kr_dist_raw(인구암 앵커) 개인 분포 실측 SD. TOST: 부트스트랩 90% CI ⊂ 마진.
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rng = np.random.default_rng(20260914)

pid = defaultdict(dict)
for l in open(ROOT / "data/exp010/kr_dist_raw.jsonl", encoding="utf-8"):
    r = json.loads(l)
    if r["grp"] == "ANCHOR" and r["arm"] == "DEMO" and r.get("dist"):
        pid[r["pid"]][r["form"]] = {int(k): v for k, v in r["dist"].items()}
both = [d for d in pid.values() if "A" in d and "B" in d]
delta_i = np.array([(d["A"].get(1, 0) - d["A"].get(2, 0)) - (d["B"].get(1, 0) - d["B"].get(2, 0)) for d in both])
p1 = np.array([d["A"].get(1, 0) for d in both])
sd_d, sd_p = delta_i.std(), p1.std()
print(f"실측(인구암 앵커 n={len(both)}): 개인 델타 SD={sd_d*100:.1f}%p, 지원확률 SD={sd_p*100:.1f}%p")

NSIM, B = 2000, 1000
def power(n, shift, margin, sd):
    x = rng.normal(0, sd, (NSIM, n))
    y = rng.normal(shift / 100, sd, (NSIM, n))
    # 부트스트랩 평균차 분포: 정규 근사 대신 실제 리샘플(벡터화)
    idx = rng.integers(0, n, (NSIM, B, n))
    bx = np.take_along_axis(x[:, None, :], idx, axis=2).mean(axis=2)
    by = np.take_along_axis(y[:, None, :], idx, axis=2).mean(axis=2)
    diff = by - bx
    lo, hi = np.percentile(diff, 5, axis=1), np.percentile(diff, 95, axis=1)
    return float(np.mean((lo > -margin / 100) & (hi < margin / 100)))

for n in (300, 500):
    print(f"\n[델타 차 등가마진 ±3%p, n={n}/{n}] 참 차이 → 통과확률 (0=검정력, ≥3=위양성)")
    for s in (0, 1, 2, 3, 5):
        print(f"  {s}%p: {power(n, s, 3, sd_d):.2f}")
print(f"\n[분포 TVD ≤ .05] 지원확률 SE(n=300, 두 집단)≈{sd_p*np.sqrt(2/300):.3f} → 90% CI 반폭 {1.645*sd_p*np.sqrt(2/300):.3f}"
      f" (3범주 TVD로는 ≈{1.5*1.645*sd_p*np.sqrt(2/300):.3f}) — 마진 .05 대비 {'충분' if 1.5*1.645*sd_p*np.sqrt(2/300) < 0.05 else '부족'}")
