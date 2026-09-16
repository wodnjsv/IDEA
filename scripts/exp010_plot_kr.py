# -*- coding: utf-8 -*-
"""EXP-010 한국장 시각화: 문항 3개 × (실제 사람 / 가상 시민-분포발화 / 가상 시민-강제선택).

기존 결과의 재표시(신규 지표 없음). 인구정보 암(DEMO), A형 문구 기준.
SSR은 τ를 이 칸(DEMO·A형)으로 캘리브레이션해 자기채점이 되므로 제외.
산출: data/exp010/fig_kr_distributions.png
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import data_dir, resolve  # noqa: E402

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

D9, D10 = data_dir() / "exp009", data_dir() / "exp010"
ARM, FORM = "DEMO", "A"
items = json.load(open(D9 / "kr_items.json", encoding="utf-8"))
anchor = json.load(open(data_dir() / "exp009_kr_anchor.json", encoding="utf-8"))["ground_truth"]["pooled_A"]

df, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
num = df.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)


def kgss_dist(var, year, keys):
    s = num.loc[df["YEAR"] == year, var].dropna()
    return {k: float((s == k).mean()) for k in keys}, len(s)


def forced(item, keys):
    preds = [r["pred"] for r in map(json.loads, open(D9 / "kr_raw.jsonl", encoding="utf-8"))
             if r.get("pred") is not None and r["item"] == item and r["arm"] == ARM and r["form"] == FORM]
    return {k: preds.count(k) / len(preds) for k in keys}, len(preds)


def dist(item, keys):
    ds = [r["dist"] for r in map(json.loads, open(D10 / "kr_dist_raw.jsonl", encoding="utf-8"))
          if r.get("dist") and r["grp"] == item and r["arm"] == ARM and r["form"] == FORM]
    return {k: float(np.mean([d.get(str(k), 0.0) for d in ds])) for k in keys}, len(ds)


SHORT = {"국정운영을 더 잘하도록 정부와 여당에 힘을 실어줘야 한다.": "여당에 힘을\n(국정 안정)",
         "정부여당을 견제할 수 있도록 야당에 힘을 실어줘야 한다": "야당에 힘을\n(정부 견제)"}


def short(label, n=14):
    label = SHORT.get(label, label)
    return label if len(label) <= n or "\n" in label else label[:n] + "…"


QUESTIONS = [
    ("ANCHOR", "총선 구도 (NBS 문구)", "실제: 한국리서치 웹실험 n=986",
     lambda keys: ({1: anchor["stability_pct"] / 100, 2: anchor["check_pct"] / 100,
                    9: 1 - (anchor["stability_pct"] + anchor["check_pct"]) / 100}, 986)),
    ("SAMPTHOU23", "여론조사로 여론을 알 수 있나 (2023)", "실제: KGSS 2023 A형",
     lambda keys: kgss_dist("SAMPTHOUA", 2023, keys)),
    ("NUKPLT18", "원자력 발전 정책 방향 (2018)", "실제: KGSS 2018 A형",
     lambda keys: kgss_dist("NUKPLT10A", 2018, keys)),
]

fig, axes = plt.subplots(1, 3, figsize=(17, 5.8))
series = [("실제 사람", "#2b2b2b"), ("가상 시민 · 분포 발화 (EXP-010)", "#1f77b4"),
          ("가상 시민 · 강제 선택 (EXP-009)", "#d9a441")]
for ax, (item, title, src, real_fn) in zip(axes, QUESTIONS):
    opts = items[item][FORM]["opts"]
    keys = [o["v"] for o in opts]
    real, n_real = real_fn(keys)
    dv, n_d = dist(item, keys)
    fv, n_f = forced(item, keys)
    x = np.arange(len(keys))
    w = 0.27
    for j, ((name, color), vals) in enumerate(zip(series, [real, dv, fv])):
        ys = [vals[k] * 100 for k in keys]
        bars = ax.bar(x + (j - 1) * w, ys, w, color=color, label=name)
        for b, y in zip(bars, ys):
            ax.text(b.get_x() + b.get_width() / 2, y + 1, f"{y:.0f}", ha="center", va="bottom", fontsize=8)
    tvd_d = 0.5 * sum(abs(real[k] - dv[k]) for k in keys)
    tvd_f = 0.5 * sum(abs(real[k] - fv[k]) for k in keys)
    ax.set_title(f"{title}\n{src} · 가상 {n_d}명", fontsize=11)
    ax.set_xticks(x, [short(o["label"]) for o in opts], fontsize=9)
    ax.set_ylim(0, 122)
    ax.set_ylabel("응답 비율 (%)")
    ax.text(0.02, 0.97, f"분포 오차(TVD)\n분포 발화 {tvd_d:.3f}\n강제 선택 {tvd_f:.3f}",
            transform=ax.transAxes, ha="left", va="top", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="#bbbbbb"))
    ax.spines[["top", "right"]].set_visible(False)

fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=3, frameon=False, fontsize=10)
fig.suptitle("EXP-010 한국장 — 실제 사람 vs 가상 시민 응답 분포 (인구정보 페르소나 300명, A형 문구, gpt-4o-mini)",
             fontsize=13)
fig.tight_layout(rect=(0, 0.07, 1, 0.94))
out = D10 / "fig_kr_distributions.png"
fig.savefig(out, dpi=160)
print(f"저장: {out}")
