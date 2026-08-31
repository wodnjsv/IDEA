# -*- coding: utf-8 -*-
"""EXP-010 사전 분석 1: 자극 쌍 임베딩 거리 ↔ 인간 효과 (카드 등록 후 실행).

38쌍 stimA/stimB → text-embedding-3-small → 코사인 거리.
판정: (a) 실측 vs 위약 분리 AUC + Mann-Whitney (b) 실측 내 거리↔|효과| Spearman.
비용: 76 임베딩 호출 ≈ $0.001.
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu, spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = ROOT / "data" / "exp009"
pairs = [json.loads(l) for l in open(OUT / "us_pairs_runtime.jsonl", encoding="utf-8")]

client, fp = LC.make_client("openai", None)
print(f"[임베딩] text-embedding-3-small key={fp}")

texts, idx = [], []
for p in pairs:
    texts += [p["stimA"][:4000], p["stimB"][:4000]]
    idx.append(p["study"])
r = client.embeddings.create(model="text-embedding-3-small", input=texts)
V = np.array([d.embedding for d in r.data])
V = V / np.linalg.norm(V, axis=1, keepdims=True)

rows = []
for i, p in enumerate(pairs):
    cos_dist = 1 - float(V[2 * i] @ V[2 * i + 1])
    rows.append({"study": p["study"], "role": p["role"], "subtype": p["subtype"],
                 "human_pp": p["human_pp"], "dist": round(cos_dist, 5)})

real = [r for r in rows if r["role"] == "real"]
null = [r for r in rows if r["role"] == "null"]
dr = [r["dist"] for r in real]
dn = [r["dist"] for r in null]

print(f"\n{'역할':4} {'study':8} {'유형':16} {'인간효과':>7} {'임베딩거리':>9}")
for r in sorted(rows, key=lambda x: -x["dist"]):
    print(f"{r['role']:4} {r['study']:8} {r['subtype']:16} {r['human_pp']:+7.1f} {r['dist']:9.5f}")

u, p_mw = mannwhitneyu(dr, dn, alternative="greater")
auc = u / (len(dr) * len(dn))
rho, p_sp = spearmanr(dr, [abs(r["human_pp"]) for r in real])
print(f"\n(a) 실측 vs 위약 분리: AUC={auc:.3f} (Mann-Whitney 단측 p={p_mw:.4f})")
print(f"    거리 중앙값: 실측 {np.median(dr):.4f} vs 위약 {np.median(dn):.4f}")
print(f"(b) 실측 17쌍 내 거리↔|효과| Spearman ρ={rho:.3f} (p={p_sp:.4f})")
json.dump(rows, io.open(OUT / "exp010_pre_embed.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("저장: exp010_pre_embed.json")
