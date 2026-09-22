"""EXP-016 preregistered planning only; proxies do not validate target power."""
import json
from collections import Counter, defaultdict
from math import sqrt
from statistics import NormalDist, mean, stdev, variance

from minsim_luna_run import data_dir, resolve, digest


def main():
    out = data_dir() / "minsim/luna_housework_income"
    out.mkdir(parents=True, exist_ok=True)
    source = resolve("minsim_mde_exp009", verify=True)
    groups = defaultdict(lambda: defaultdict(list))
    for r in map(json.loads, source.open()):
        if r["arm"] == "FULL":
            target = 3 if r["item"] == "NUKPLT18" and r["form"] == "B" else 1
            groups[r["item"]][(r["pid"], r["form"])].append(float(r["pred"] == target))
    proxies = []
    for item, cells in sorted(groups.items()):
        ids = sorted({pid for pid, form in cells})
        assert all(len(cells[pid, form]) == 3 for pid in ids for form in ("A", "B"))
        delta = [mean(cells[pid, "B"]) - mean(cells[pid, "A"]) for pid in ids]
        proxies.append({"item": item, "n": len(ids), "k": 3,
                        "outcome": "NUKPLT18: expansion A1/B3; others A1/B1", "delta_sd": stdev(delta),
                        "within_variance": mean(variance(v) for v in cells.values())})
    phase_source = resolve("minsim_mde_phase0", verify=True)
    within = []
    invalid_people = 0
    for r in map(json.loads, phase_source.open()):
        votes = [s["parsed"].get("vote") for s in r["samples"] if isinstance(s.get("parsed"), dict)]
        votes = [v for v in votes if v is not None]
        if len(votes) < 2:
            invalid_people += 1
            continue
        counts = Counter(votes)
        within.append(len(votes) / (len(votes)-1) * (1 - sum((n/len(votes))**2 for n in counts.values())))
    people = list(map(json.loads, resolve("minsim_full_personas", verify=True).open()))
    sizes = {"전체": len(people)}
    sizes.update({f"연도{w}": sum(p["wave"] == w for p in people) for w in (2018, 2021, 2023, 2025)})
    sizes.update({label: sum(p["sex"] == code for p in people) for code, label in ((1, "남성"), (2, "여성"))})
    sizes.update({label: sum(lo <= p["age"] < hi for p in people) for lo, hi, label in
                  ((18, 30, "18~29세"), (30, 40, "30대"), (40, 50, "40대"), (50, 60, "50대"), (60, 200, "60세이상"))})
    table = []
    for label, n in sizes.items():
        for comparisons in (2, 4):
            factor = (NormalDist().inv_cdf(1-.05/(2*comparisons)) + NormalDist().inv_cdf(.8)) / sqrt(n)
            table.append({"group": label, "n": n, "k": 1, "comparisons": comparisons,
                          "upper_sd": 1, "upper_mde_pp": factor*100,
                          "target_mde_pp": 10, "planning_target_met": factor <= .1,
                          "proxy_mde_pp": {p["item"]: factor*p["delta_sd"]*100 for p in proxies}})
    result = {"primary": "paired change in P50 probability", "family_alpha": .05,
              "power_target": .8, "correction": "Bonferroni", "planning_only": True,
              "formula": "(z(1-alpha/(2*m))+z(power))*SD(delta)/sqrt(n)",
              "proxies": proxies, "phase0": {"valid_people": len(within), "invalid_people": invalid_people,
              "mean_sum_of_within_onehot_variances": mean(within), "paired_delta_available": False},
              "tables": table,
              "source_sha256": {"exp009": digest(source.read_text()), "phase0": digest(phase_source.read_text())}}
    (out / "mde_plan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"proxies": proxies, "phase0": result["phase0"], "overall": table[:2]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
