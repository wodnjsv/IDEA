# -*- coding: utf-8 -*-
"""EXP-008 1단 채점기 — 사전등록 판정의 기계적 실행.

  H1 개인신호: FULL vs SHUF — Δ Fisher-z(사람 부트스트랩 95% CI>0) AND Δz>=0.10
  H2 LLM증분:  FULL vs 베이스라인 {릿지회귀(서열근사)·kNN·행렬완성} 전승 (사람 단위 paired, α=.05)
  H3 정보량(예비): FULL vs K5 동일 규격
베이스라인은 참조셋(비평가)에서만 학습 — 평가 300명의 배터리 정답 미접촉 (Codex #3·#4 반영).
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402
from scipy import stats  # noqa: E402

from engine import harmonize as H  # noqa: E402
from engine.registry import resolve  # noqa: E402

OUT = ROOT / "data" / "exp008"
SEED = 42
rng = np.random.default_rng(SEED)

meta_p = json.load(open(OUT / "prep_meta.json", encoding="utf-8"))
BATTERY = meta_p["battery"]
profiles = [json.loads(l) for l in open(OUT / "profiles.jsonl", encoding="utf-8")]
raw = [json.loads(l) for l in open(OUT / "raw.jsonl", encoding="utf-8")]

# ── LLM 예측 적재 (마지막 성공 우선) ──
pred = {}
for r in raw:
    if r.get("pred") is not None:
        pred[(r["pid"], r["arm"], r["var"])] = r["pred"]
n_err = sum(1 for r in raw if r.get("pred") is None)

# ── 원자료 재적재 (베이스라인 입력용 수치 벡터) ──
df, _ = pyreadstat.read_sav(str(resolve("kgss_cum_2003_2025")))
d23 = df[df["YEAR"] == 2023].reset_index(drop=True)
num23 = d23.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)
eval_rows = {p["pid"]: int(p["pid"].split("_")[1]) for p in profiles}
# profile_pool은 reference.parquet 열에서 복원 (prep과 단일 진실원 공유)
ref = pd.read_parquet(OUT / "reference.parquet")
POOL = [c for c in ref.columns if c not in ("src", "SEX", "AGE") and c not in BATTERY]

ref_X = ref[POOL].astype(float)
ref_B = ref[BATTERY].astype(float)
mu, sd = ref_X.mean(), ref_X.std().replace(0, 1.0)

def scale_of(var):
    for p in profiles:
        for it in p["battery"]:
            if it["var"] == var:
                return [o["v"] for o in it["options"]]
    return []

def clip_round(var, x):
    opts = scale_of(var)
    return int(min(opts, key=lambda o: abs(o - x))) if opts else int(round(x))

# ── 베이스라인 학습 (참조셋 전용) ──
# ① 릿지 회귀 (카드 '순서형 로지스틱'의 근사 — 서열을 수치로 보고 회귀 후 반올림. 편차 기록)
ridge_models = {}
for b in BATTERY:
    y = ref_B[b]
    ok = y.notna()
    corr = ref_X[ok].corrwith(y[ok]).abs().sort_values(ascending=False)
    feats = corr.head(20).index.tolist()
    Xz = ((ref_X[feats] - mu[feats]) / sd[feats]).fillna(0.0)[ok].values
    yv = y[ok].values
    lam = 10.0
    A = Xz.T @ Xz + lam * np.eye(len(feats))
    w = np.linalg.solve(A, Xz.T @ (yv - yv.mean()))
    ridge_models[b] = (feats, w, yv.mean())

# ③ 행렬완성 (반복 SVD rank20 — 평가행의 배터리 칸은 마스킹 상태로 함께 적합)
eval_X = pd.DataFrame({c: [num23.loc[eval_rows[p["pid"]], c] for p in profiles] for c in POOL},
                      index=[p["pid"] for p in profiles]).astype(float)
M = pd.concat([pd.concat([ref_X, ref_B], axis=1),
               pd.concat([eval_X, pd.DataFrame(np.nan, index=eval_X.index, columns=BATTERY)], axis=1)])
allmu, allsd = M.mean(), M.std().replace(0, 1.0)   # 주의: 평가 배터리칸은 NaN이라 통계 오염 없음
Z = ((M - allmu) / allsd).values
mask = ~np.isnan(Z)
F = np.where(mask, Z, 0.0)
for _ in range(10):
    U, S, Vt = np.linalg.svd(F, full_matrices=False)
    L = (U[:, :20] * S[:20]) @ Vt[:20]
    F = np.where(mask, Z, L)
mc = pd.DataFrame(L, index=M.index, columns=M.columns)

# ② kNN (참조셋에서 프로필 z-거리 최근접 10명의 최빈답)
refZ = ((ref_X - mu) / sd).values
def knn_predict(pid, b):
    xz = ((eval_X.loc[pid] - mu) / sd).values.astype(float)
    valid = ~np.isnan(xz)
    if valid.sum() < 10:
        return None
    diff = np.abs(refZ[:, valid] - xz[valid])
    dist = np.nanmean(diff, axis=1)
    y = ref_B[b].values
    order = np.argsort(np.where(np.isnan(y), np.inf, dist))
    top = [y[i] for i in order if not np.isnan(y[i])][:10]
    return clip_round(b, float(pd.Series(top).mode().iloc[0])) if top else None

# ④ 셀 최빈값 (성×연령대)
ref_cellmode = {}
band = ref["AGE"].dropna().apply(lambda a: H.age_band(int(a)))
for b in BATTERY:
    g = pd.DataFrame({"sex": ref["SEX"], "band": band, "y": ref_B[b]}).dropna()
    for (sx, bd), grp in g.groupby(["sex", "band"]):
        ref_cellmode[(b, sx, bd)] = int(grp["y"].mode().iloc[0])
    ref_cellmode[(b, None, None)] = int(g["y"].mode().iloc[0])

def cellmode_predict(p, b):
    row = d23.loc[eval_rows[p["pid"]]]
    key = (b, float(row["SEX"]), H.age_band(int(row["AGE"])))
    return ref_cellmode.get(key, ref_cellmode[(b, None, None)])

# ── 예측표 구성 ──
rows = []
for p in profiles:
    pid = p["pid"]
    for it in p["battery"]:
        if it["actual"] is None:
            continue
        b = it["var"]
        feats, w, y0 = ridge_models[b]
        xz = ((eval_X.loc[pid, feats] - mu[feats]) / sd[feats]).fillna(0.0).values
        rows.append({
            "pid": pid, "var": b, "actual": it["actual"],
            "K0": pred.get((pid, "K0", b)), "K5": pred.get((pid, "K5", b)),
            "FULL": pred.get((pid, "FULL", b)), "SHUF": pred.get((pid, "SHUF", b)),
            "B_ridge": clip_round(b, float(xz @ w + y0)),
            "B_knn": knn_predict(pid, b),
            "B_mc": clip_round(b, float(mc.loc[pid, b] * allsd[b] + allmu[b])),
            "B_cell": cellmode_predict(p, b),
        })
T = pd.DataFrame(rows)
ARMS = ["K0", "K5", "FULL", "SHUF", "B_ridge", "B_knn", "B_mc", "B_cell"]

def acc(col, adj=False):
    s = T[[col, "actual"]].dropna()
    d = (s[col] - s["actual"]).abs()
    return float((d <= (1 if adj else 0)).mean()), len(s)

def item_z(col):
    zs = []
    for b in BATTERY:
        s = T[T["var"] == b][[col, "actual"]].dropna()
        if len(s) >= 30 and s[col].std() > 0 and s["actual"].std() > 0:
            r = stats.spearmanr(s[col], s["actual"]).statistic
            zs.append(np.arctanh(np.clip(r, -0.999, 0.999)))
    return float(np.mean(zs)) if zs else np.nan

def person_acc(col):
    s = T[[col, "actual", "pid"]].dropna()
    return (s[col] == s["actual"]).groupby(s["pid"]).mean()

def boot_dz(a, bcol, n=2000):
    pids = T["pid"].unique()
    diffs = []
    for _ in range(n):
        samp = rng.choice(pids, len(pids), replace=True)
        sub = pd.concat([T[T["pid"] == p] for p in samp])
        za, zb = [], []
        for bt in BATTERY:
            s = sub[sub["var"] == bt]
            for col, acc_z in ((a, za), (bcol, zb)):
                ss = s[[col, "actual"]].dropna()
                if len(ss) >= 30 and ss[col].std() > 0 and ss["actual"].std() > 0:
                    acc_z.append(np.arctanh(np.clip(stats.spearmanr(ss[col], ss["actual"]).statistic, -0.999, 0.999)))
        if za and zb:
            diffs.append(np.mean(za) - np.mean(zb))
    return float(np.mean(diffs)), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))

rep = {"n_rows": len(T), "n_err": n_err, "arms": {}}
for c in ARMS:
    e, n = acc(c)
    a1, _ = acc(c, adj=True)
    rep["arms"][c] = {"n": n, "acc": round(e, 4), "acc_adj1": round(a1, 4), "fisher_z": round(item_z(c), 4)}

dz, lo, hi = boot_dz("FULL", "SHUF")
rep["H1"] = {"dz_full_minus_shuf": round(dz, 4), "ci": [round(lo, 4), round(hi, 4)],
             "pass": bool(lo > 0 and dz >= 0.10)}
h2 = {}
pa_full = person_acc("FULL")
for bl in ["B_ridge", "B_knn", "B_mc"]:
    pa_b = person_acc(bl)
    common = pa_full.index.intersection(pa_b.index)
    diff = pa_full[common] - pa_b[common]
    w = stats.wilcoxon(diff, alternative="greater") if diff.abs().sum() > 0 else None
    h2[bl] = {"mean_diff": round(float(diff.mean()), 4),
              "p": round(float(w.pvalue), 5) if w else None,
              "win": bool(w and w.pvalue < 0.05 and diff.mean() > 0)}
rep["H2"] = {**h2, "pass": all(v["win"] for v in h2.values())}
dz3, lo3, hi3 = boot_dz("FULL", "K5")
rep["H3"] = {"dz_full_minus_k5": round(dz3, 4), "ci": [round(lo3, 4), round(hi3, 4)]}

json.dump(rep, io.open(OUT / "score_exp008.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(rep, ensure_ascii=False, indent=1))
