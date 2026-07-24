"""뱅크 마진 검증 (v1 대응): weight_bank 가중 집계 vs 가중 모집단.

층화 플로어 설계에서는 무가중 시도 분포가 의도적으로 과대표집(소형 시도) — 집계는 반드시 weight_bank로.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd  # noqa: E402

from engine import harmonize as H  # noqa: E402
from engine.bank import load_pool  # noqa: E402
from engine.registry import data_dir  # noqa: E402


def pool_marginals(df, wcol="인구가중값"):
    d = df.copy()
    d["sex"] = d["성별코드"].map({"1": "남", "2": "여"})
    d["age_g"] = d["만연령"].astype(int).map(H.age_band)
    d["edu4"] = d["교육정도코드"].map(lambda c: H.edu4_census(c) if isinstance(c, str) and c else None)
    out = {}
    for dim in ["sex", "age_g", "edu4"]:
        g = d.groupby(dim)[wcol].sum()
        out[dim] = (g / g.sum() * 100).round(2).to_dict()
    g = d.groupby("행정구역시도코드")[wcol].sum()
    out["sido"] = (g / g.sum() * 100).round(2).to_dict()
    return out


def bank_marginals(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    b = pd.DataFrame([{"sex": r["skeleton"]["sex"], "age_g": r["skeleton"]["age_band"],
                       "edu4": r["skeleton"]["edu4"], "sido": r["skeleton"]["sido"],
                       "ideo": r["drawn"]["ideology_code"], "wb": r.get("weight_bank", 1.0)} for r in rows])
    out = {}
    for dim in ["sex", "age_g", "edu4", "sido"]:
        g = b.groupby(dim)["wb"].sum()
        out[dim] = (g / g.sum() * 100).round(2).to_dict()          # weight_bank 가중
        out[dim + "_unweighted"] = (b[dim].value_counts(normalize=True) * 100).round(2).to_dict()
    g = b.groupby("ideo")["wb"].sum()
    out["ideology"] = (g / g.sum() * 100).round(2).to_dict()
    return out, len(rows)


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "v0"
    pool = load_pool()
    res = {}
    for track, sub in [("national", pool),
                       ("gwangmyeong", pool[(pool["행정구역시도코드"] == "31") & (pool["행정구역시군구코드"] == "060")])]:
        path = data_dir() / "banks" / f"persona_bank_{track}_{tag}.jsonl"
        if not path.exists():
            print(f"[{track}/{tag}] 없음 — 스킵")
            continue
        pm = pool_marginals(sub)
        bm, n = bank_marginals(path)
        diff = {dim: {k: round(bm[dim].get(k, 0) - pm[dim].get(k, 0), 2) for k in pm[dim]}
                for dim in ["sex", "age_g", "edu4", "sido"]}
        maxd = max(abs(v) for dim in ["sex", "age_g", "edu4"] for v in diff[dim].values())
        sido_maxd = max(abs(v) for v in diff["sido"].values())
        res[track] = {"n": n, "pool": pm, "bank": bm, "diff": diff,
                      "maxdiff_weighted": maxd, "sido_maxdiff_weighted": sido_maxd}
        print(f"[{track}/{tag}] n={n} | 가중 maxdiff={maxd}%p | 가중 시도 maxdiff={sido_maxd}%p")
    out = data_dir() / "banks" / f"validation_{tag}.json"
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", out)


if __name__ == "__main__":
    main()
