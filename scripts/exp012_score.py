# -*- coding: utf-8 -*-
"""EXP-012 채점 — 분포 채널 21대 대선 재현. weight_bank 가중, 유효표 질량우선 집계(v2, Codex 교차검토 반영), 게이트 H1~H4."""
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


def agg(W, P):
    """질량 우선 집계: Σ w_i p_ic / Σ_i w_i Σ_c p_ic (개인별 재정규화 후 평균 금지 — Codex 교차검토 #18).
    개인별 정규화 우선은 기권 확률이 높은 인물에게 같은 비중을 주어 왜곡(차이 ≤0.4%p였으나 정의상 오류)."""
    m = (W[:, None] * P).sum(0)
    return m / m.sum() * 100


for arm in sorted({r["arm"] for r in rows}):
    R = [r for r in rows if r["arm"] == arm]
    if not R:
        continue
    CANDS = GT["candidates"][:3] if arm.endswith("_3") else GT["candidates"]  # 3자 구도: 정답 재정규화
    gt_raw = np.array([GT["national_pct"][c] for c in CANDS]); gt_raw = gt_raw / gt_raw.sum() * 100
    W = np.array([r["weight_bank"] for r in R])
    V = np.array([[r["dist"].get(c, 0.0) for c in CANDS] for r in R])  # 원 질량(정규화 안 함)
    share = agg(W, V)
    gt = gt_raw
    # 부트스트랩 CI (페르소나 리샘플 — 고정 뱅크·모델·프롬프트 하의 표본 변동만 반영)
    idx = rng.integers(0, len(R), (2000, len(R)))
    bs = np.array([agg(W[i], V[i]) for i in idx])
    lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
    mae = np.abs(share - gt).mean()
    abst = float((W * np.array([r["dist"].get(ABST, 0) for r in R])).sum() / W.sum() * 100)
    dk = float((W * np.array([r["dist"].get(DK, 0) for r in R])).sum() / W.sum() * 100)
    ent = float(np.mean([-(p := np.array([x for x in r["dist"].values() if x > 0])) @ np.log(p) for r in R]))
    tag = "3자 구도(정답 재정규화)" if arm.endswith("_3") else ("라벨 포함" if arm == "D1" else "라벨 제거")
    print(f"\n===== {arm} ({tag}) n={len(R)} =====")
    for c, s, l, h, g in zip(CANDS, share, lo, hi, gt):
        print(f"  {c:12} {s:6.2f} [{l:5.1f},{h:5.1f}]  실제 {g:6.2f}  오차 {s-g:+6.2f}")
    resid = share[0] - gt[0]
    print(f"  유효표 MAE {mae:.2f} (EXP-004 B암 5.94) | 이재명 잔여 {resid:+.2f} [{lo[0]-gt[0]:+.1f},{hi[0]-gt[0]:+.1f}] (EXP-004 +9.07)")
    print(f"  기권 {abst:.1f}% / 밝히지 않음 {dk:.1f}% (실제 기권 ≈21%) | 평균 엔트로피 {ent:.3f}")
    tp = share[0] / (share[0] + share[1]) * 100; tpb = bs[:, 0] / (bs[:, 0] + bs[:, 1]) * 100
    tpg = gt[0] / (gt[0] + gt[1]) * 100
    print(f"  양당 내 {CANDS[0][-3:]} 비율 {tp:.2f} [{np.percentile(tpb, 2.5):.2f},{np.percentile(tpb, 97.5):.2f}] (실제 {tpg:.2f}) — 탐색 지표(사전등록 외)")
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
        sh = agg(ww, vv)
        print(f"  카드 '{lab}' (n={len(S)}): 이재명 {sh[0]:.1f} / 김문수 {sh[1]:.1f} / 이준석 {sh[2]:.1f}")
    g1 = max(abs(lo[0] - gt[0]), abs(hi[0] - gt[0])) < EXP004["잔여"]  # 사전등록 문구대로 95% CI 상한 기준(감사 B6)
    g3 = (len(CANDS) == 3 or share[4] < 2) and 4 <= share[2] <= 14
    print(f"  게이트 H1(|잔여|<9.07) {'O' if g1 else 'X'} | H3(송진호<2, 이준석 4~14) {'O' if g3 else 'X'} | MAE<5.94 {'O' if mae < 5.94 else 'X'} | 시도≥13 {'O' if hit >= 13 else 'X'}")
print("\n(개발셋 지표 — 대외 인용 금지, ISS-009)")
