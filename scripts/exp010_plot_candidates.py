# -*- coding: utf-8 -*-
"""사업계획서용 시각화 후보 4종 — 실제 사람 vs 이데아 가상 시민 응답 분포 (기존 결과 재표시).

A. 100% 누적 가로 막대 (여론조사 보도 표준)
B. 덤벨 차트 (선택지별 두 값의 간격)
C. 차이 막대 (가상 − 실제, %p)
D. 대각선 산점도 (x=실제, y=가상, 모든 선택지)
공통: 3:2 (3000×2000), Pretendard, 인구정보 페르소나 300명·첫 번째 문구 기준.
산출: data/exp010/fig_cand_{A,B,C,D}_*.png
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

# ── 색 (dataviz 기준 팔레트, 검증 통과) ──
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
REAL_C, IDEA_C = "#52514e", "#2a78d6"            # 두 계열 정체성
POS, NEU, NEG = "#2a78d6", "#c9c8c3", "#e34948"  # 발산: 파랑 ↔ 회색 중립 ↔ 빨강
Q_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]      # 문항 정체성(산점도, 3슬롯 all-pairs 통과)
FS = {"sup": 30, "sub": 17, "title": 20, "tick": 16, "val": 16, "leg": 18}
W, H, DPI = 15, 10, 200


def kgss(var, year, keys):
    s = num.loc[df["YEAR"] == year, var].dropna()
    return {k: float((s == k).mean()) for k in keys}


def idea(item, keys):
    ds = [r["dist"] for r in map(json.loads, open(D10 / "kr_dist_raw.jsonl", encoding="utf-8"))
          if r.get("dist") and r["grp"] == item and r["arm"] == ARM and r["form"] == FORM]
    return {k: float(np.mean([d.get(str(k), 0.0) for d in ds])) for k in keys}


# 문항: (id, 제목, 출처, 실제분포 함수, 선택지 짧은 이름, 선택지 극성 색)
Q = [
    ("ANCHOR", "총선 구도 질문", "한국리서치 웹 조사",
     lambda k: {1: anchor["stability_pct"] / 100, 2: anchor["check_pct"] / 100,
                9: 1 - (anchor["stability_pct"] + anchor["check_pct"]) / 100},
     {1: "여당에 힘(국정 안정)", 2: "야당에 힘(정부 견제)", 9: "응답 유보"},
     {1: POS, 2: NEG, 9: NEU}, [1, 9, 2]),
    ("SAMPTHOU23", "여론조사로 여론을 알 수 있는가", "한국종합사회조사 2023",
     lambda k: kgss("SAMPTHOUA", 2023, k),
     {1: "알 수 있다", 2: "알 수 없다"}, {1: POS, 2: NEG}, [1, 2]),
    ("NUKPLT18", "원자력 발전 정책 방향", "한국종합사회조사 2018",
     lambda k: kgss("NUKPLT10A", 2018, k),
     {1: "확대", 2: "현상 유지", 3: "축소"}, {1: POS, 2: NEU, 3: NEG}, [1, 2, 3]),
]
DATA = []
for item, title, src, real_fn, names, colors, order in Q:
    keys = [o["v"] for o in items[item][FORM]["opts"]]
    DATA.append(dict(item=item, title=title, src=src, keys=order, names=names, colors=colors,
                     real=real_fn(keys), idea=idea(item, keys)))


def gap(d):
    return 0.5 * sum(abs(d["real"][k] - d["idea"][k]) for k in d["keys"]) * 100


def frame(title, subtitle):
    fig = plt.figure(figsize=(W, H), facecolor=SURF)
    fig.suptitle(title, fontsize=FS["sup"], fontweight="bold", color=INK, y=0.965)
    fig.text(0.5, 0.905, subtitle, ha="center", fontsize=FS["sub"], color=INK2)
    return fig


def style(ax):
    ax.set_facecolor(SURF)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=FS["tick"], length=0)


SUB = "인구 정보 기반 이데아 가상 시민 300명 · 선택지별 응답 확률을 모아 집단 분포 산출"
TINT = {POS: "#aac9ee", NEG: "#f2a7a6", NEU: "#e6e5e1"}  # 실제 분포용 옅은 색(같은 색상, 명도만 올림)


# ── A. 100% 누적 가로 막대 ──
def cand_A():
    fig = frame("실제 사람과 이데아 가상 시민의 응답 분포", SUB)
    gs = fig.add_gridspec(3, 1, left=0.2, right=0.96, top=0.76, bottom=0.07, hspace=1.2)
    axes_A = []
    for i, d in enumerate(DATA):
        ax = fig.add_subplot(gs[i])
        style(ax)
        for row, dist in enumerate([d["real"], d["idea"]]):
            is_real = row == 0
            left = 0
            for k in d["keys"]:
                v = dist[k] * 100
                base = d["colors"][k]
                fc = TINT[base] if is_real else base
                ax.barh(row, v, left=left, height=0.62, color=fc, edgecolor=SURF, linewidth=2)
                if v >= 6:
                    tc = INK if (is_real or base == NEU) else "white"
                    ax.text(left + v / 2, row, f"{v:.0f}%", ha="center", va="center",
                            fontsize=FS["val"], fontweight="semibold", color=tc)
                left += v
        ax.set_yticks([0, 1], ["실제 사람", "이데아 가상 시민"], fontsize=FS["tick"])
        ax.tick_params(axis="y", pad=16)
        real_lab, idea_lab = ax.get_yticklabels()
        real_lab.set_color(INK2)
        idea_lab.set_color(INK)
        idea_lab.set_fontweight("bold")
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.set_title(f"{d['title']}   ", loc="left", fontsize=FS["title"], fontweight="bold",
                     color=INK, pad=50, x=-0.17)
        ax.text(1.0, 1.36, f"분포 차이 {gap(d):.1f}%p", transform=ax.transAxes, ha="right",
                va="bottom", fontsize=FS["tick"], fontweight="semibold", color=INK)
        # 범례(선택지): 제목 아래 한 줄, 막대와 간격 확보
        xpos = 0.0
        for k in d["keys"]:
            ax.add_patch(plt.Rectangle((xpos, 1.15), 0.014, 0.09, transform=ax.transAxes,
                                       color=d["colors"][k], clip_on=False))
            ax.text(xpos + 0.02, 1.195, d["names"][k], transform=ax.transAxes, va="center",
                    fontsize=FS["tick"] - 1, color=INK2)
            xpos += 0.03 + 0.0125 * len(d["names"][k]) + 0.02
        axes_A.append(ax)
    # 질문 사이 구분선: 위 판 아래끝과 아래 판 제목 윗끝의 중간
    for upper, lower in zip(axes_A, axes_A[1:]):
        ub, lb = upper.get_position(), lower.get_position()
        title_top = lb.y1 + lb.height * 0.62
        y = (ub.y0 + title_top) / 2
        fig.add_artist(plt.Line2D([0.05, 0.96], [y, y], transform=fig.transFigure,
                                  color="#d6d5d0", linewidth=1.4))
    fig.text(0.02, 0.015, "실제 분포 출처: 한국리서치 웹 조사(총선 구도), 한국종합사회조사 2023·2018",
             fontsize=FS["tick"] - 3, color=INK2)
    fig.savefig(D10 / "fig_cand_A_stacked.png", dpi=DPI, facecolor=SURF)


# ── B. 덤벨 차트 ──
def cand_B():
    fig = frame("선택지별 실제 비율과 이데아 가상 시민 비율", SUB)
    rows, labels, groups = [], [], []
    y = 0
    for d in DATA:
        groups.append((y, d))
        for k in d["keys"]:
            rows.append((y, d["real"][k] * 100, d["idea"][k] * 100))
            labels.append((y, d["names"][k]))
            y += 1
        y += 1.3
    ax = fig.add_axes([0.28, 0.08, 0.66, 0.70])
    style(ax)
    ax.set_xlim(0, 80)
    ax.set_xticks(range(0, 81, 20), [f"{t}%" for t in range(0, 81, 20)])
    ax.xaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)
    for yy, r, s in rows:
        ax.plot([r, s], [yy, yy], color="#bdbcb8", linewidth=4, solid_capstyle="round", zorder=1)
        ax.scatter([r], [yy], s=260, color=REAL_C, zorder=3, edgecolor=SURF, linewidth=2)
        ax.scatter([s], [yy], s=260, color=IDEA_C, zorder=3, edgecolor=SURF, linewidth=2)
        lo, hi = (r, s) if r <= s else (s, r)
        ax.text(lo - 1.8, yy, f"{lo:.0f}", ha="right", va="center", fontsize=FS["val"] - 1, color=INK2)
        ax.text(hi + 1.8, yy, f"{hi:.0f}", ha="left", va="center", fontsize=FS["val"] - 1, color=INK2)
    ax.set_yticks([l[0] for l in labels], [l[1] for l in labels], fontsize=FS["tick"], color=INK)
    ax.set_ylim(y - 1.0, -1.6)
    for gy, d in groups:
        ax.text(-0.40, gy - 0.95, f"{d['title']}", transform=ax.get_yaxis_transform(),
                fontsize=FS["title"] - 1, fontweight="bold", color=INK, va="center")
        ax.text(1.0, gy - 0.95, f"분포 차이 {gap(d):.1f}%p", transform=ax.get_yaxis_transform(),
                ha="right", fontsize=FS["tick"], fontweight="semibold", color=INK, va="center")
    ax.scatter([], [], s=260, color=REAL_C, label="실제 사람")
    ax.scatter([], [], s=260, color=IDEA_C, label="이데아 가상 시민")
    ax.legend(loc="lower right", fontsize=FS["leg"], frameon=False, bbox_to_anchor=(1.0, 1.0), ncol=2,
              handletextpad=0.3, columnspacing=1.5, borderaxespad=0.1)
    fig.savefig(D10 / "fig_cand_B_dumbbell.png", dpi=DPI, facecolor=SURF)


# ── C. 차이 막대 ──
def cand_C():
    fig = frame("이데아 가상 시민은 실제보다 몇 %p 높거나 낮았나", SUB)
    ax = fig.add_axes([0.3, 0.1, 0.64, 0.72])
    style(ax)
    y, ticks, labels, heads = 0, [], [], []
    for d in DATA:
        heads.append((y, d))
        for k in d["keys"]:
            diff = (d["idea"][k] - d["real"][k]) * 100
            ax.barh(y, diff, height=0.62, color=POS if diff >= 0 else NEG)
            ax.text(diff + (0.3 if diff >= 0 else -0.3), y, f"{diff:+.1f}",
                    ha="left" if diff >= 0 else "right", va="center", fontsize=FS["val"], color=INK)
            ticks.append(y)
            labels.append(d["names"][k])
            y += 1
        y += 1.3
    ax.axvline(0, color=INK2, linewidth=1.5)
    ax.set_xlim(-10, 10)
    ax.set_xticks(range(-10, 11, 5), [f"{t:+d}" if t else "0" for t in range(-10, 11, 5)])
    ax.xaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.set_yticks(ticks, labels, fontsize=FS["tick"], color=INK)
    ax.set_ylim(y - 1.0, -1.6)
    for gy, d in heads:
        ax.text(-0.44, gy - 0.95, d["title"], transform=ax.get_yaxis_transform(),
                fontsize=FS["title"] - 1, fontweight="bold", color=INK, va="center")
    ax.set_xlabel("← 실제보다 낮게 추정        차이(%p)        실제보다 높게 추정 →",
                  fontsize=FS["tick"], color=INK2, labelpad=12)
    fig.savefig(D10 / "fig_cand_C_diff.png", dpi=DPI, facecolor=SURF)


# ── D. 대각선 산점도 ──
def cand_D():
    fig = frame("모든 선택지: 실제 비율 대비 이데아 가상 시민 비율", SUB)
    ax = fig.add_axes([0.26, 0.08, 0.48, 0.72])
    style(ax)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color(GRID)
    ax.plot([0, 80], [0, 80], color=INK2, linewidth=1.5, linestyle=(0, (4, 4)), zorder=1)
    ax.fill_between([0, 80], [-5, 75], [5, 85], color=GRID, alpha=0.5, zorder=0, linewidth=0)
    # 라벨 위치(데이터 좌표, 정렬) — 겹침 없게 수동 배치
    place = {("ANCHOR", 1): (40.5, 36.0, "left"), ("ANCHOR", 2): (42.5, 44.0, "right"),
             ("ANCHOR", 9): (19.5, 13.5, "left"),
             ("SAMPTHOU23", 1): (35.0, 30.5, "left"), ("SAMPTHOU23", 2): (65.0, 71.5, "right"),
             ("NUKPLT18", 1): (17.0, 29.5, "right"), ("NUKPLT18", 2): (52.5, 45.6, "left"),
             ("NUKPLT18", 3): (29.0, 23.0, "right")}
    for c, d in zip(Q_COLORS, DATA):
        for k in d["keys"]:
            r, s = d["real"][k] * 100, d["idea"][k] * 100
            ax.scatter(r, s, s=320, color=c, edgecolor=SURF, linewidth=2, zorder=3)
            tx, ty, ha = place[(d["item"], k)]
            ax.text(tx, ty, d["names"][k], fontsize=FS["tick"] - 2, color=INK, ha=ha, va="center",
                    zorder=4)
        ax.scatter([], [], s=320, color=c, label=f"{d['title']} · 분포 차이 {gap(d):.1f}%p")
    ax.text(79, 3, "점선: 완전 일치 · 회색 띠: ±5%p", ha="right", fontsize=FS["tick"] - 2, color=INK2)
    ax.set_xlim(0, 80)
    ax.set_ylim(0, 80)
    ax.set_aspect("equal")
    ax.set_xticks(range(0, 81, 20), [f"{t}%" for t in range(0, 81, 20)])
    ax.set_yticks(range(0, 81, 20), [f"{t}%" for t in range(0, 81, 20)])
    ax.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.set_xlabel("실제 사람 응답 비율", fontsize=FS["tick"], color=INK, labelpad=10)
    ax.set_ylabel("이데아 가상 시민 응답 비율", fontsize=FS["tick"], color=INK, labelpad=10)
    ax.legend(loc="upper left", fontsize=FS["leg"] - 4, frameon=True, facecolor=SURF, edgecolor=GRID,
              labelspacing=0.9, borderpad=0.8)
    fig.savefig(D10 / "fig_cand_D_scatter.png", dpi=DPI, facecolor=SURF)


for fn in (cand_A, cand_B, cand_C, cand_D):
    fn()
    print("완료:", fn.__name__)
