"""Restore EXP-009's same 1,200 people with FULL profiles in every wave (ISS-028)."""
import ast
import hashlib
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import data_dir, resolve


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source = resolve("kgss_cum_2003_2025", verify=True)
    original = resolve("minsim_original_personas", verify=True)
    before = sha(original)
    people = [json.loads(line) for line in original.open()]
    assert len(people) == len({p["pid"] for p in people}) == 1200
    df, meta = pyreadstat.read_sav(str(source))
    labels, vlabels = meta.column_names_to_labels, meta.variable_value_labels
    # Execute only reviewed pure helpers/constants, never the original prep's top-level I/O.
    legacy = ROOT / "scripts/exp009_kr_prep.py"
    tree = ast.parse(legacy.read_text())
    names = {"ADMIN_PAT", "DEMO_VARS", "DEMO_LABEL"}
    funcs = {"is_admin", "is_demo", "vlabel", "render_item", "demo_text"}
    nodes = [n for n in tree.body if
             (isinstance(n, ast.FunctionDef) and n.name in funcs) or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names
                                               for t in n.targets))]
    ns = dict(pd=pd, re=re, labels=labels, vlabels=vlabels)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(legacy), "exec"), ns)
    excluded = set(pd.read_csv(resolve("minsim_legacy_exclusions"))["var"])
    political = {n for n in df.columns if n in ("PARTYLR", "LEFTRIGT") or
                 any(s in (labels.get(n) or "") for s in
                     ["투표", "정당", "대선", "대통령", "선거", "지지", "총선"]) or
                 any(s in n.upper() for s in ["VOTE", "PRTY", "PARTY", "ELEC", "PRES"])}
    out = data_dir() / "minsim/luna_parent70"
    out.mkdir(parents=True, exist_ok=True)
    restored, schema, checks = [], {}, []
    for wave in sorted({p["wave"] for p in people}):
        frame = df[df.YEAR == wave].reset_index(drop=True)
        numbers = frame.apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0)
        pool = [n for n in frame if not ns["is_admin"](n) and not ns["is_demo"](n)
                and n not in excluded | political and numbers[n].notna().mean() >= .30]
        for per in (p for p in people if p["wave"] == wave):
            idx = int(per["pid"].split("_")[1])
            assert per["demo"] == ns["demo_text"](frame.loc[idx]), per["pid"]
            valid = [n for n in pool if pd.notna(numbers.loc[idx, n])]
            random.Random(f"20260828-{wave}-{idx}").shuffle(valid)
            lines = [ns["render_item"](n, numbers.loc[idx, n]) for n in valid]
            if per["full_lines"]:
                assert lines == per["full_lines"], per["pid"]
            # Household numbering is an administrative artifact, not persona evidence.
            valid = [n for n in valid if "가구번호" not in (labels.get(n) or "")]
            answers = [{"var": n, "label": labels.get(n, n),
                        "value": float(numbers.loc[idx, n]),
                        "text": ns["render_item"](n, numbers.loc[idx, n])} for n in valid]
            assert len(answers) >= 30
            restored.append({**per, "full_lines": [a["text"] for a in answers],
                             "answers": answers,
                             "age": int(frame.loc[idx, "AGE"]),
                             "sex": int(frame.loc[idx, "SEX"])})
            for a in answers:
                schema[a["var"]] = a["label"]
        rows = [p for p in restored if p["wave"] == wave]
        checks.append({"wave": wave, "n": len(rows),
                       "min_answers": min(len(p["answers"]) for p in rows),
                       "max_answers": max(len(p["answers"]) for p in rows)})
    assert sha(original) == before
    assert {p["pid"] for p in restored} == {p["pid"] for p in people}
    target = out / "personas_full.jsonl"
    target.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in restored))
    (out / "profile_variables.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2))
    report = dict(source_sha256=sha(source), original_sha256=before,
                  restored_sha256=sha(target), legacy_prep_sha256=sha(legacy),
                  original_unchanged=True, same_1200_ids=True, waves=checks,
                  rule="legacy FULL pool (wave coverage >=30%); administrative household number removed")
    (out / "restore_checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
