"""llm_client 자체검증 — API 호출 없이 스텁으로 배선을 검사한다 (AGENTS 구현 규율: 동작·게이트·회귀 3축).

    python scripts/selftest_llm_client.py
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from engine import llm_client as LC  # noqa: E402

FAIL = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + ((" — " + detail) if detail else ""))
    if not cond:
        FAIL.append(name)


def _resp(n, text='{"ideology":"중도","vote":"국민의힘 김문수"}'):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text)) for _ in range(n)],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=40))


class Stub:
    """mode: batch=n 지원 / reject=n 거부 / silent=n 무시하고 1개만 / flaky=첫 429"""

    def __init__(self, mode):
        self.mode, self.calls, self.n_seen = mode, 0, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        n = kw.get("n", 1)
        self.n_seen.append(n)
        if self.mode == "reject" and n > 1:
            raise ValueError("400 Bad Request: parameter 'n' is not supported")
        if self.mode == "silent":
            return _resp(1)
        if self.mode == "flaky" and self.calls == 1:
            raise RuntimeError("429 Too Many Requests")
        return _resp(n)


print("① n=K 배치 지원 백엔드")
s = LC.Sampler(client=Stub("batch"), model_id="m", k=5)
out, u = s.sample("sys", "usr")
check("샘플 5개", len(out) == 5)
check("요청 1회", s.client.calls == 1, f"실제 {s.client.calls}")
check("n 모드 batch", s.n_mode == "batch")
check("usage 집계", u == {"in": 100, "out": 40}, str(u))

print("② n 미지원 백엔드 → K콜 자동 강등")
s = LC.Sampler(client=Stub("reject"), model_id="m", k=5)
out, u = s.sample("sys", "usr")
check("샘플 5개", len(out) == 5)
check("요청 6회(실패1+직렬5)", s.client.calls == 6, f"실제 {s.client.calls}")
check("n 모드 serial", s.n_mode == "serial")
check("usage 누적", u == {"in": 500, "out": 200}, str(u))
out2, _ = s.sample("sys", "usr")            # 두 번째 페르소나는 n 재시도 없이 바로 직렬
check("판정 고착(재시도 없음)", s.client.calls == 11, f"실제 {s.client.calls}")

print("③ n을 무시하고 1개만 주는 백엔드")
s = LC.Sampler(client=Stub("silent"), model_id="m", k=3)
out, _ = s.sample("sys", "usr")
check("샘플 3개", len(out) == 3)
check("n 모드 serial", s.n_mode == "serial")

print("④ 429 재시도 + 전역 감속")
s = LC.Sampler(client=Stub("flaky"), model_id="m", k=1, limiter=LC.RateLimiter(600), retries=3)
t0 = time.monotonic()
out, _ = s.sample("sys", "usr")
check("결국 성공", len(out) == 1)
check("429 카운트", s.stats["429"] == 1, str(s.stats))
check("백오프 대기 발생", time.monotonic() - t0 >= 2.0)

print("⑤ ISS-012 컷오프 게이트")
check("안전 모델 통과", LC.assert_cutoff(LC.MODELS["llama-3.3-70b"]) == "OK")
for bad in ["mistral-small-24b", "nemotron-super-49b"]:
    try:
        LC.assert_cutoff(LC.MODELS[bad])
        check(f"{bad} 차단", False, "차단되지 않음")
    except SystemExit:
        check(f"{bad} 차단", True)
risky = LC.ModelSpec("nvidia", "x/y-2026", "2026-01", "가상")
try:
    LC.assert_cutoff(risky)
    check("선거 이후 컷오프 차단", False)
except SystemExit:
    check("선거 이후 컷오프 차단", True)
check("강행 시 라벨 부여", LC.assert_cutoff(risky, allow_risk=True).startswith("MEMORIZATION_RISK"))

print("⑥ 레이트리미터 정확도")
lim = LC.RateLimiter(120)      # 0.5s 간격
t0 = time.monotonic()
for _ in range(4):
    lim.acquire()
el = time.monotonic() - t0
check("4콜 ≈1.5s", 1.4 <= el <= 2.0, f"{el:.2f}s")

print("⑦ 출력 정제 (추론 토큰·코드펜스)")
check("think 제거", LC.clean("<think>고민</think>{\"v\":1}") == '{"v":1}')
check("펜스 제거", LC.clean('```json\n{"v":1}\n```') == '{"v":1}')
check("None 안전", LC.clean(None) == "")

print("⑧ 키 비노출")
try:
    key, fp = LC.load_key("nvidia")
    check("지문에 키 원문 없음", key not in fp and key[6:14] not in fp, fp)
except SystemExit:
    print("  skip  (nvidia 키 없음)")

print("\n" + ("전부 통과" if not FAIL else f"실패 {len(FAIL)}건: {FAIL}"))
sys.exit(1 if FAIL else 0)
