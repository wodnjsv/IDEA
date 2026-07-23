"""뱅크 마진 검증: 뱅크 vs 가중 모집단 주변분포 비교 리포트 (T2 게이트 사전 점검)."""
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
        out[dim] = (g / g.sum() * 100).round(1).to_dict()
    g = d.groupby("행정구역시도코드")[wcol].sum()
    out["sido"] = (g / g.sum() * 100).round(1).to_dict()
    return out


def bank_marginals(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    b = pd.DataFrame([{"sex": r["skeleton"]["sex"], "age_g": r["skeleton"]["age_band"],
                       "edu4": r["skeleton"]["edu4"], "sido": r["skeleton"]["sido"],
                       "ideo": r["drawn"]["ideology_code"]} for r in rows])
    out = {dim: (b[dim].value_counts(normalize=True) * 100).round(1).to_dict()
           for dim in ["sex", "age_g", "edu4", "sido"]}
    out["ideology"] = (b["ideo"].value_counts(normalize=True) * 100).round(1).to_dict()
    return out, len(rows)


def main():
    pool = load_pool()
    res = {}
    for track, sub in [("national", pool),
                       ("gwangmyeong", pool[(pool["행정구역시도코드"] == "31") & (pool["행정구역시군구코드"] == "060")])]:
        pm = pool_marginals(sub)
        bm, n = bank_marginals(data_dir() / "banks" / f"persona_bank_{track}_v0.jsonl")
        diff = {dim: {k: round(bm[dim].get(k, 0) - pm[dim].get(k, 0), 1) for k in pm[dim]}
                for dim in ["sex", "age_g", "edu4"]}
        res[track] = {"n": n, "pool": pm, "bank": bm, "diff": diff,
                      "maxdiff": max(abs(v) for d in diff.values() for v in d.values()),
                      "sido_maxdiff": max(abs(bm["sido"].get(k, 0) - pm["sido"].get(k, 0)) for k in pm["sido"])}
        print(f"[{track}] n={n} maxdiff={res[track]['maxdiff']}%p sido_maxdiff={res[track]['sido_maxdiff']:.1f}%p")
    out = data_dir() / "banks" / "validation_v0.json"
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("→", out)


if __name__ == "__main__":
    main()
