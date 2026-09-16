# -*- coding: utf-8 -*-
"""EXP-010 한국장 시각화: 문항 3개 × (실제 사람 / 가상 시민-분포발화).

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

plt.rcParams["font.family"] = "Pretendard"
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
    ("ANCHOR", "총선 구도 질문", "실제: 한국리서치 웹 조사",
     lambda keys: ({1: anchor["stability_pct"] / 100, 2: anchor["check_pct"] / 100,
                    9: 1 - (anchor["stability_pct"] + anchor["check_pct"]) / 100}, 986)),
    ("SAMPTHOU23", "여론조사로 여론을 알 수 있는가", "실제: 한국종합사회조사 2023",
     lambda keys: kgss_dist("SAMPTHOUA", 2023, keys)),
    ("NUKPLT18", "원자력 발전 정책 방향", "실제: 한국종합사회조사 2018",
     lambda keys: kgss_dist("NUKPLT10A", 2018, keys)),
]

# 사업계획서용 — 3:2 비율, 2×2 배치(네 번째 칸 = 범례·설명)
FS = {"sup": 26, "title": 19, "sub": 14, "tick": 14, "bar": 15, "box": 15, "legend": 18, "note": 14}
fig, grid = plt.subplots(2, 2, figsize=(15, 10))
panels = [grid[0, 0], grid[0, 1], grid[1, 0]]
series = [("실제 사람", "#2b2b2b"), ("IDEA 가상 시민", "#1f77b4")]
for ax, (item, title, src, real_fn) in zip(panels, QUESTIONS):
    opts = items[item][FORM]["opts"]
    keys = [o["v"] for o in opts]
    real, n_real = real_fn(keys)
    dv, n_d = dist(item, keys)
    x = np.arange(len(keys))
    w = 0.38
    for j, ((name, color), vals) in enumerate(zip(series, [real, dv])):
        ys = [vals[k] * 100 for k in keys]
        bars = ax.bar(x + (j - 0.5) * w, ys, w, color=color, label=name)
        for b, y in zip(bars, ys):
            ax.text(b.get_x() + b.get_width() / 2, y + 1, f"{y:.0f}", ha="center", va="bottom",
                    fontsize=FS["bar"], fontweight="semibold")
    gap = 0.5 * sum(abs(real[k] - dv[k]) for k in keys) * 100
    ax.set_title(title, fontsize=FS["title"], fontweight="bold", pad=26)
    ax.text(0.5, 1.02, src, transform=ax.transAxes, ha="center", va="bottom",
            fontsize=FS["sub"], color="#555555")
    ax.set_xticks(x, [short(o["label"]) for o in opts], fontsize=FS["tick"])
    ax.tick_params(axis="y", labelsize=FS["tick"])
    ax.set_ylim(0, 90)
    ax.set_ylabel("응답 비율 (%)", fontsize=FS["tick"])
    ax.text(0.03, 0.96, f"분포 차이 {gap:.1f}%p", transform=ax.transAxes, ha="left", va="top",
            fontsize=FS["box"], fontweight="semibold",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="#bbbbbb"))
    ax.spines[["top", "right"]].set_visible(False)

leg_ax = grid[1, 1]
leg_ax.axis("off")
leg_ax.legend(*panels[0].get_legend_handles_labels(), loc="upper left", frameon=False,
              fontsize=FS["legend"], handlelength=1.6, borderaxespad=0.2)
leg_ax.text(0.02, 0.62,
            "IDEA 가상 시민: 실존 응답자의 인구 정보로 만든 300명\n"
            "각 가상 시민이 선택지별 응답 확률을 답하고,\n"
            "그 확률을 모아 집단 분포를 만들었다.\n\n"
            "분포 차이: 실제 분포와 일치시키려면\n"
            "응답자 몇 %가 다른 선택지로 옮겨야 하는지(%p)",
            transform=leg_ax.transAxes, ha="left", va="top", fontsize=FS["note"],
            color="#333333", linespacing=1.6)

fig.suptitle("실제 사람과 IDEA 가상 시민의 응답 분포 비교", fontsize=FS["sup"], fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=3.0, w_pad=2.5)
out = D10 / "fig_idea_real_vs_synthetic.png"
fig.savefig(out, dpi=200)
print(f"저장: {out}")
