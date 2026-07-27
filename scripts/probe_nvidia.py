"""NVIDIA NIM 무료 백엔드 모델 프로브 — 실제 EXP 프롬프트로 후보 모델을 실측 비교.

    python scripts/probe_nvidia.py              # 컷오프 통과 후보만 (기본 7종)
    python scripts/probe_nvidia.py --list       # 카탈로그 전체 ID만 덤프
    python scripts/probe_nvidia.py --models llama-3.3-70b gemma-3-27b

측정 항목 (모델당 3회 시행 + n 지원 1회):
  hosted        무료 엔드포인트 응답 여부
  n_batch       n=K 1콜 지원 여부  ← 지원 안 하면 총 요청 수가 K배 → 벽시계 K배
  latency_s     1콜 중앙값 지연
  json_ok       JSON 형식 준수율
  vote_ok       선택지 정규화 성공률
  ko            한국어 응답 여부
왜 최신 대형 모델을 고르지 않는가: 무료 카탈로그의 2025년 이후 학습 모델은 21대 대선 결과를
이미 알고 있어 ISS-012 컷오프 게이트에서 차단된다. 후보는 전부 '선거 전 컷오프' 모델이다.
"""
import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC          # noqa: E402
from engine.prompts_t3 import build_prompt   # noqa: E402

OUT = ROOT / "data" / "t3"
BANK = ROOT / "data" / "banks" / "persona_bank_national_v1.jsonl"
GT = json.load(open(ROOT / "phase0" / "data" / "ground_truth_2025.json", encoding="utf-8"))
CANDS = GT["candidates"]
HANGUL = re.compile(r"[가-힣]")
TRIALS = 3


def parse(t):
    m = re.search(r"\{.*?\}", t or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def norm(v):
    if not isinstance(v, str):
        return None
    for c in CANDS + ["투표하지 않음"]:
        if c in v or c.split()[-1] in v:
            return c
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="카탈로그 ID만 출력하고 종료")
    ap.add_argument("--models", nargs="*", default=None, help="MODELS 키 목록")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--rpm", type=int, default=35)
    ap.add_argument("--key-file", default=None)
    args = ap.parse_args()

    client, fp = LC.make_client("nvidia", args.key_file)
    print(f"백엔드 {LC.PROVIDERS['nvidia']['base_url']} | 키 {fp}")

    try:
        catalog = sorted(m.id for m in client.models.list().data)
    except Exception as e:                     # noqa: BLE001
        print(f"카탈로그 조회 실패({e}) — 프로브는 계속 진행")
        catalog = []
    print(f"카탈로그 {len(catalog)}종")
    if args.list:
        for m in catalog:
            print(" ", m)
        return

    keys = args.models or LC.PROBE_SHORTLIST
    persona = json.loads(open(BANK, encoding="utf-8").readline())
    system, user, _ = build_prompt("B", persona)   # 실제 실험과 동일한 프롬프트 부하
    limiter = LC.RateLimiter(args.rpm)

    rows = []
    for key in keys:
        spec = LC.MODELS[key]
        try:
            gate = LC.assert_cutoff(spec)
        except SystemExit as e:
            rows.append({"key": key, "id": spec.id, "gate": "BLOCKED", "why": str(e)})
            print(f"[{key}] 컷오프 게이트 차단 — 건너뜀")
            continue
        r = {"key": key, "id": spec.id, "cutoff": spec.cutoff, "gate": gate,
             "in_catalog": (spec.id in catalog) if catalog else None,
             "hosted": False, "n_batch": None, "latency_s": None,
             "json_ok": 0.0, "vote_ok": 0.0, "ko": False, "err": None}
        s = LC.Sampler(client=client, model_id=spec.id, k=1, limiter=limiter, retries=2)
        lat, jok, vok, ko = [], 0, 0, False
        for _ in range(TRIALS):
            t0 = time.monotonic()
            try:
                outs, _u = s.sample(system, user)
            except Exception as e:              # noqa: BLE001
                r["err"] = str(e)[:200]
                break
            lat.append(time.monotonic() - t0)
            txt = outs[0]
            r["hosted"] = True
            ko = ko or bool(HANGUL.search(txt))
            p = parse(txt)
            if p:
                jok += 1
                if norm(p.get("vote")):
                    vok += 1
        if lat:
            r.update(latency_s=round(statistics.median(lat), 2),
                     json_ok=round(jok / len(lat), 2), vote_ok=round(vok / len(lat), 2), ko=ko)
            sk = LC.Sampler(client=client, model_id=spec.id, k=args.k, limiter=limiter, retries=1)
            try:
                outs, _u = sk.sample(system, user)
                r["n_batch"] = (sk.n_mode == "batch")
            except Exception as e:              # noqa: BLE001
                r["n_batch"] = False
                r["err"] = r["err"] or str(e)[:200]
        rows.append(r)
        print(f"[{key:<18}] hosted={r['hosted']} n={r['n_batch']} "
              f"lat={r['latency_s']}s json={r['json_ok']} vote={r['vote_ok']} ko={r['ko']}"
              + (f" err={r['err'][:60]}" if r.get("err") else ""))

    ok = [r for r in rows if r.get("hosted") and r.get("vote_ok", 0) >= 0.67]
    ok.sort(key=lambda r: (not r.get("n_batch"), -r["vote_ok"], r["latency_s"]))
    print("\n── 권장 순위 (n=K 배치 지원 > 파싱 신뢰도 > 지연) ──")
    for i, r in enumerate(ok, 1):
        mult = 1 if r["n_batch"] else args.k
        print(f"{i}. {r['key']:<18} {r['id']:<40} 컷오프 {r['cutoff']} | "
              f"요청배수 ×{mult} | {r['latency_s']}s")
    if ok:
        best = ok[0]
        calls = 1000 * 3 * (1 if best["n_batch"] else args.k)
        print(f"\n추천: --provider nvidia --model {best['key']}")
        print(f"  3암×1,000명 = {calls:,}요청 → {args.rpm} RPM 기준 약 {calls/args.rpm/60:.1f}시간")
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(rows, open(OUT / "nvidia_probe.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n→ {OUT / 'nvidia_probe.json'}")


if __name__ == "__main__":
    main()
