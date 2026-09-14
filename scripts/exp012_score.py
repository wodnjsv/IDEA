# -*- coding: utf-8 -*-
"""EXP-012 채점 — 분포 채널 21대 대선 재현. weight_bank 가중, 유효표 재정규화, 게이트 H1~H4."""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
GT = json.load(open(ROOT / "phase0" / "data" / "ground_truth_2025.json", encoding="utf-8"))
CANDS = GT["candidates"]
ABST, DK = "투표하지 않음", "누구에게 투표했는지 밝히고 싶지 않음"
SIDO_FULL = {"서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
             "광주": "광주광역시", "대전": "대전광역시", "울산": "울산광역시", "세종": "세종특별자치시",
             "경기": "경기도", "강원": "강원특별자치도", "충북": "충청북도", "충남": "충청남도",
             "전북": "전북특별자치도", "전남": "전라남도", "경북": "경상북도", "경남": "경상남도", "제주": "제주특별자치도"}
EXP004 = {"이재명_유효": 58.49, "잔여": 9.07, "MAE_B": 5.94, "시도1위": 12, "송진호": 6.2}
rng = np.random.default_rng(20260914)

rows = [json.loads(l) for l in open(ROOT / "data/exp012/raw.jsonl", encoding="utf-8")]
rows = [r for r in rows if r.get("dist")]


def valid_share(d):
    v = {c: d.get(c, 0.0) for c in CANDS}
    s = sum(v.values())
    return {c: x / s for c, x in v.items()} if s > 0 else None


for arm in ("D1", "D2"):
    R = [r for r in rows if r["arm"] == arm]
    if not R:
        continue
    W = np.array([r["weight_bank"] for r in R])
    V = np.array([[valid_share(r["dist"])[c] for c in CANDS] for r in R])
    share = (W[:, None] * V).sum(0) / W.sum() * 100
    gt = np.array([GT["national_pct"][c] for c in CANDS])
    # 부트스트랩 CI (페르소나 리샘플)
    idx = rng.integers(0, len(R), (2000, len(R)))
    bs = np.array([(W[i][:, None] * V[i]).sum(0) / W[i].sum() * 100 for i in idx])
    lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
    mae = np.abs(share - gt).mean()
    abst = float((W * np.array([r["dist"].get(ABST, 0) for r in R])).sum() / W.sum() * 100)
    dk = float((W * np.array([r["dist"].get(DK, 0) for r in R])).sum() / W.sum() * 100)
    ent = float(np.mean([-(p := np.array([x for x in r["dist"].values() if x > 0])) @ np.log(p) for r in R]))
    print(f"\n===== {arm} ({'라벨 포함' if arm == 'D1' else '라벨 제거'}) n={len(R)} =====")
    for c, s, l, h, g in zip(CANDS, share, lo, hi, gt):
        print(f"  {c:12} {s:6.2f} [{l:5.1f},{h:5.1f}]  실제 {g:6.2f}  오차 {s-g:+6.2f}")
    resid = share[0] - gt[0]
    print(f"  유효표 MAE {mae:.2f} (EXP-004 B암 5.94) | 이재명 잔여 {resid:+.2f} [{lo[0]-gt[0]:+.1f},{hi[0]-gt[0]:+.1f}] (EXP-004 +9.07)")
    print(f"  기권 {abst:.1f}% / 밝히지 않음 {dk:.1f}% (실제 기권 ≈21%) | 평균 엔트로피 {ent:.3f}")
    # 시도 1위
    sd = defaultdict(lambda: np.zeros(len(CANDS)))
    sw = defaultdict(float)
    for r, w, v in zip(R, W, V):
        sd[r["sido_name"]] += w * v
        sw[r["sido_name"]] += w
    hit = sum(CANDS[int(np.argmax(sd[s]))] == GT["sido_winner"][SIDO_FULL[s]] for s in sd)
    print(f"  시도 1위 적중 {hit}/{len(sd)} (EXP-004 12/17)")
    # 이념 카드별 분포 (H2 결정론)
    for lab in ("진보", "다소 진보", "중도", "다소 보수", "보수"):
        S = [(w, v) for r, w, v in zip(R, W, V) if (r.get("ideology") or "") == lab]
        if len(S) < 10:
            continue
        ww = np.array([w for w, _ in S]); vv = np.array([v for _, v in S])
        sh = (ww[:, None] * vv).sum(0) / ww.sum() * 100
        print(f"  카드 '{lab}' (n={len(S)}): 이재명 {sh[0]:.1f} / 김문수 {sh[1]:.1f} / 이준석 {sh[2]:.1f}")
    g1 = abs(resid) < EXP004["잔여"]; g3 = share[4] < 2 and 4 <= share[2] <= 14
    print(f"  게이트 H1(|잔여|<9.07) {'O' if g1 else 'X'} | H3(송진호<2, 이준석 4~14) {'O' if g3 else 'X'} | MAE<5.94 {'O' if mae < 5.94 else 'X'} | 시도≥13 {'O' if hit >= 13 else 'X'}")
print("\n(개발셋 지표 — 대외 인용 금지, ISS-009)")
