# -*- coding: utf-8 -*-
"""EXP-011 사전 체크 6: H4(하류 동등성) 등가마진 검정력 — 분포 채널 실측 분산으로 모의계산.

가짜 살 300 vs 진짜 살 300 (독립 인물 집합). 지표: 집단 분포 TVD ≤ .05, 워딩 델타 차 ≤ 3%p.
분산 소스: EXP-010 kr_dist_raw(인구암 앵커) 개인 분포의 실측 SD.
검정: 부트스트랩 90% CI가 마진 내(TOST 동등) — 참 차이 0/1/2/3/5%p 시나리오별 통과확률.
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
gapA = np.array([d["A"].get(1, 0) - d["A"].get(2, 0) for d in pid.values() if "A" in d and "B" in d])
gapB = np.array([d["B"].get(1, 0) - d["B"].get(2, 0) for d in pid.values() if "A" in d and "B" in d])
delta_i = gapA - gapB
p1A = np.array([d["A"].get(1, 0) for d in pid.values() if "A" in d])
print(f"실측(인구암 앵커 n={len(delta_i)}): 개인 델타 SD={delta_i.std()*100:.1f}%p, 지원확률 SD={p1A.std()*100:.1f}%p")

B, NSIM = 2000, 3000
def power(n, true_shift_pp, margin_pp, sd):
    ok = 0
    for _ in range(NSIM):
        x = rng.normal(0, sd, n)               # 진짜 살 집단
        y = rng.normal(true_shift_pp / 100, sd, n)  # 가짜 살 집단 (참 차이)
        diffs = []
        for _ in range(B):
            diffs.append(rng.choice(y, n).mean() - rng.choice(x, n).mean())
        lo, hi = np.percentile(diffs, [5, 95])
        ok += (lo > -margin_pp / 100) and (hi < margin_pp / 100)
    return ok / NSIM

print(f"\nH4 델타 차 등가마진 ±3%p, n=300/300 (부트스트랩 90% CI ⊂ 마진 = 통과)")
print(f"{'참 차이':>7} {'통과확률':>8}")
for shift in (0, 1, 2, 3, 5):
    print(f"{shift:6d}%p {power(300, shift, 3, delta_i.std()):8.2f}")
print(f"\n(참 차이 0에서의 통과확률 = 검정력, 참 차이 ≥3에서의 통과확률 = 위양성)")
print(f"지원확률 SD {p1A.std():.3f} → 분포 TVD .05 마진은 n=300에서 SE≈{p1A.std()/np.sqrt(300)*np.sqrt(2):.3f}·1.645 = "
      f"{p1A.std()/np.sqrt(300)*np.sqrt(2)*1.645:.3f} 폭 — 마진 대비 {'충분' if p1A.std()/np.sqrt(300)*np.sqrt(2)*1.645 < 0.05 else '부족'}")
