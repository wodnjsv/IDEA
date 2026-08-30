# -*- coding: utf-8 -*-
"""EXP-009 한국장 채점 (사례검증 — 통계판정 미산입).

앵커(총선 구도 워딩): 정답지 = 격차차 Δ = (지원−견제)_NBS − (지원−견제)_갤럽 = +13%p
  (한국리서치 28057: A −7%p, B −20%p). 판정: 방향 + 크기 [4.3, 39.0]%p + 하위집단 구조
  (무당파에서 |Δ| > 당파층 |Δ| — 원보고서 핵심 주장) + 3암 대조(Q4 프로필 증분).
사후가중: 페르소나 정당지지(PRTYID23, 분석 라벨 전용)를 웹실험 표본 구성
  (민주 36.5 / 국힘 29 / 기타 6.5 / 무당파 28)으로 림가중한 topline 병기.
위약: 강한 2쌍 본판정(정렬 후 최대 |Δ| CI가 인간 CI 상한 내), 약한 5쌍 기술 보고.
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import resolve  # noqa: E402

OUT = ROOT / "data" / "exp009"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rng = np.random.default_rng(20260828)
B = 4000

raw = [json.loads(l) for l in open(OUT / "kr_raw.jsonl", encoding="utf-8")]
raw = [r for r in raw if r.get("pred") is not None]
items = json.load(open(OUT / "kr_items.json", encoding="utf-8"))

# 페르소나 정당지지 (분석 라벨 전용 — 프롬프트 미포함)
df, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
d23 = df[df["YEAR"] == 2023].reset_index(drop=True)
party = {}
for pid in {r["pid"] for r in raw if r["pid"].startswith("k2023_")}:
    i = int(pid.split("_")[1])
    v = d23.loc[i, "PRTYID23"] if i < len(d23) else np.nan
    party[pid] = ("dem" if v == 1 else "ppp" if v == 2 else
                  "none" if v == 77 else "other" if pd.notna(v) and v > 0 else "na")

# item → arm → pid → form → [preds]
data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"A": [], "B": []})))
for r in raw:
    data[r["item"]][r["arm"]][r["pid"]][r["form"]].append(r["pred"])

WEB_COMP = {"dem": 0.365, "ppp": 0.29, "other": 0.065, "none": 0.28}


def gap_stat(pid_map, weight=None, sub=None):
    """앵커: 페르소나별 (지원율−견제율)_A − 동_B → 가중 평균 Δ(%p) + 부트스트랩 CI."""
    rows = []
    for pid, d in pid_map.items():
        if not d["A"] or not d["B"]:
            continue
        if sub and party.get(pid) not in sub:
            continue
        gA = np.mean([v == 1 for v in d["A"]]) - np.mean([v == 2 for v in d["A"]])
        gB = np.mean([v == 1 for v in d["B"]]) - np.mean([v == 2 for v in d["B"]])
        w = weight.get(party.get(pid), 1.0) if weight else 1.0
        rows.append((gA - gB, w))
    if len(rows) < 15:
        return None
    diffs = np.array([x for x, _ in rows])
    ws = np.array([w for _, w in rows])
    delta = np.average(diffs, weights=ws) * 100
    idx = rng.integers(0, len(diffs), (B, len(diffs)))
    bs = (np.take(diffs * ws, idx).sum(axis=1) / np.take(ws, idx).sum(axis=1)) * 100
    return delta, float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), len(diffs)


def placebo_stat(item_name, pid_map):
    """위약: B형 정렬(역순 쌍은 재코딩) 후 범주별 Δ 최대 |Δ| + CI."""
    it = items[item_name]
    la = {o["v"]: o["label"] for o in it["A"]["opts"]}
    lb = {o["v"]: o["label"] for o in it["B"]["opts"]}
    bmap = {}  # B코드 → 같은 라벨의 A코드 (의미 정렬)
    for vb, lab in lb.items():
        match = [va for va, la_ in la.items() if la_.replace(" ", "") == lab.replace(" ", "")]
        bmap[vb] = match[0] if match else vb
    cats = sorted(la)
    per_cat = {c: [] for c in cats}
    for pid, d in pid_map.items():
        if not d["A"] or not d["B"]:
            continue
        for c in cats:
            a = np.mean([v == c for v in d["A"]])
            b = np.mean([bmap[v] == c for v in d["B"]])
            per_cat[c].append(a - b)
    if not per_cat[cats[0]] or len(per_cat[cats[0]]) < 15:
        return None
    best = None
    for c in cats:
        arr = np.array(per_cat[c])
        delta = arr.mean() * 100
        idx = rng.integers(0, len(arr), (B, len(arr)))
        bs = arr[idx].mean(axis=1) * 100
        lo, hi = float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))
        if best is None or abs(delta) > abs(best[1]):
            best = (c, delta, lo, hi, len(arr))
    return best


print("=== 앵커: 총선 구도 워딩 (인간 Δ=+13.0%p, A −7 / B −20) ===")
score = {"anchor": {}, "placebo": {}}
for arm in items["ANCHOR"]["arms"]:
    pm = data["ANCHOR"][arm]
    out = gap_stat(pm)
    if out is None:
        print(f"  {arm}: 미완")
        continue
    d, lo, hi, n = out
    wout = gap_stat(pm, weight=WEB_COMP)
    sub_none = gap_stat(pm, sub={"none"})
    sub_part = gap_stat(pm, sub={"dem", "ppp"})
    ok_dir = d > 0
    ok_size = 13 / 3 <= d <= 13 * 3
    print(f"  {arm:6} Δ={d:+6.2f} [{lo:+.1f},{hi:+.1f}] n={n} | 가중 {wout[0]:+.2f} | "
          f"방향 {'O' if ok_dir else 'X'} 크기[4.3,39] {'O' if ok_size else 'X'}")
    if sub_none and sub_part:
        struct = "O" if abs(sub_none[0]) > abs(sub_part[0]) else "X"
        print(f"         무당파 Δ={sub_none[0]:+.2f} (n={sub_none[3]}) vs "
              f"당파 Δ={sub_part[0]:+.2f} (n={sub_part[3]}) | 무당파 집중 {struct}")
    score["anchor"][arm] = {"delta": round(d, 2), "ci": [round(lo, 2), round(hi, 2)],
                            "weighted": round(wout[0], 2), "n": n,
                            "sub_none": round(sub_none[0], 2) if sub_none else None,
                            "sub_partisan": round(sub_part[0], 2) if sub_part else None}

# 앵커 절대 분포 (부문⑤ 수준 재현 — 기술 보고)
print("\n  절대 분포 (부문⑤, 인간 웹실험: A 38/45/17, B 31/51/18):")
for arm in items["ANCHOR"]["arms"]:
    for form in ("A", "B"):
        preds = [v for d in data["ANCHOR"][arm].values() for v in d[form]]
        if preds:
            p1 = np.mean([v == 1 for v in preds]) * 100
            p2 = np.mean([v == 2 for v in preds]) * 100
            p9 = np.mean([v == 9 for v in preds]) * 100
            print(f"    {arm:6} {form}: 지원 {p1:4.1f} / 견제 {p2:4.1f} / 유보 {p9:4.1f}")

print("\n=== 위약 (정렬 후 최대 |Δ| — 강한 2쌍 본판정 / 약한 5쌍 기술) ===")
HUMAN = {"SAMPTHOU23": -0.5, "NUKPLT18": -1.9, "NUKPLT21": 3.0, "PROUD21": -3.1,
         "ELEFRAUD25": -4.3, "LAWHARSH25": -3.4, "SAMPTNTH25": -4.0}
for name, it in items.items():
    if it["kind"] == "anchor":
        continue
    for arm in it["arms"]:
        out = placebo_stat(name, data[name][arm])
        if out is None:
            print(f"  {name:11} {arm}: 미완")
            continue
        c, d, lo, hi, n = out
        sig = "!" if (lo > 0 or hi < 0) else " "
        print(f"  {sig} {name:11} {arm:6} ({it['kind']:14}) 최대|Δ| 범주{c}: {d:+6.2f} "
              f"[{lo:+.1f},{hi:+.1f}] n={n} | 인간 {HUMAN.get(name, 0):+.1f}")
        score["placebo"][f"{name}|{arm}"] = {"cat": int(c), "delta": round(d, 2),
                                             "ci": [round(lo, 2), round(hi, 2)], "n": n}

json.dump(score, io.open(OUT / "kr_score.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n저장: kr_score.json | 응답 행:", len(raw))
