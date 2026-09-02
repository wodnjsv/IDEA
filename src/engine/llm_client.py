"""LLM 백엔드 추상화 — OpenAI(유료) / NVIDIA NIM(무료) 공용.

설계 원칙
  1) 키는 **환경변수 또는 gitignore된 키 파일**에서만 읽는다. 코드·로그·표준출력·커밋에 키 원문을 남기지 않는다.
  2) ISS-012 컷오프 게이트를 **코드로 강제**한다. 컷오프가 선거일 이후이거나 불확실하면 실행이 막힌다.
  3) K 샘플은 n=K 1콜을 우선 시도하되, 지원하지 않는 백엔드면 K콜로 자동 강등한다(요청 수 K배 증가 → RPM 예산에 반영).
  4) 무료 티어는 RPM이 병목이므로 클라이언트측 레이트리미터를 기본 탑재한다.

AGENTS 규칙 6: 사용한 모델 스냅샷 ID와 컷오프는 EXP 카드에 기록할 것. describe()가 그 문자열을 만들어 준다.
"""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ELECTION_DATE = "2025-06-03"
ELECTION_YM = ELECTION_DATE[:7]

# ── 백엔드 ────────────────────────────────────────────────────────────────────
PROVIDERS = {
    "openai": {"base_url": None, "envs": ("OPENAI_API_KEY",), "prefix": "sk-", "rpm": 500},
    "nvidia": {"base_url": "https://integrate.api.nvidia.com/v1",
               "envs": ("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NGC_API_KEY"),
               "prefix": "nvapi-", "rpm": 35},   # 무료 티어 공개 한도 40 RPM에 여유 5
}


@dataclass
class ModelSpec:
    provider: str
    id: str                  # 백엔드에 그대로 넘기는 스냅샷 ID
    cutoff: str | None       # "YYYY-MM" 학습 데이터 컷오프
    cutoff_src: str = ""     # 근거 (모델카드/공식문서)
    confident: bool = True   # 컷오프 근거가 1차 출처인가
    reasoning: bool = False  # 사고 토큰을 뱉는 모델인가 (짧은 JSON 과제에 불리)
    note: str = ""


# 컷오프는 "선거일(2025-06-03)보다 확실히 앞선" 모델만 게이트를 통과한다(ISS-012).
# 무료 카탈로그의 최신 플래그십(2025년 이후 학습)은 대선 결과를 이미 알고 있어 백테스트에 쓸 수 없다.
MODELS: dict[str, ModelSpec] = {
    "gpt-4o-mini": ModelSpec("openai", "gpt-4o-mini-2024-07-18", "2023-10",
                             "OpenAI 모델 문서", note="EXP-004/005 기준 모델"),
    # --- NVIDIA NIM 무료 호스팅, 컷오프 안전 후보 ---
    "llama-3.3-70b": ModelSpec("nvidia", "meta/llama-3.3-70b-instruct", "2023-12",
                               "Meta Llama 3.3 모델카드", note="비추론·안정 호스팅. 한국어 공식 지원 언어 아님"),
    "llama-3.1-405b": ModelSpec("nvidia", "meta/llama-3.1-405b-instruct", "2023-12",
                                "Meta Llama 3.1 모델카드", note="품질 최상위지만 지연·혼잡 큼"),
    "llama-3.1-70b": ModelSpec("nvidia", "meta/llama-3.1-70b-instruct", "2023-12",
                               "Meta Llama 3.1 모델카드", note="NVIDIA EOL 2026-08-26 — 사용 불가"),
    "llama-3.1-8b": ModelSpec("nvidia", "meta/llama-3.1-8b-instruct", "2023-12",
                              "Meta Llama 3.1 모델카드", note="NVIDIA EOL 2026-08-26 — 사용 불가"),
    "llama-3.2-90b": ModelSpec("nvidia", "meta/llama-3.2-90b-vision-instruct", "2023-12",
                               "Meta Llama 3.2 모델카드 — 3.1-70B 텍스트 모델 기반 비전 확장",
                               note="EXP-009 미국장 (llama-3.1-70b EOL 대체 — 개정 3)"),
    "gemma-3-27b": ModelSpec("nvidia", "google/gemma-3-27b-it", "2024-08",
                             "Google Gemma 3 모델카드", note="다국어 140종 — 한국어 후보 1순위"),
    "gemma-2-27b": ModelSpec("nvidia", "google/gemma-2-27b-it", "2024-06",
                             "Google Gemma 2 모델카드"),
    "qwen2.5-7b": ModelSpec("nvidia", "qwen/qwen2.5-7b-instruct", "2023-10",
                            "Qwen2.5 기술보고서", note="한국어 양호. 소형이라 지시추종 편차 확인 필요"),
    "mistral-small-24b": ModelSpec("nvidia", "mistralai/mistral-small-24b-instruct", None,
                                   "", confident=False, note="컷오프 미확인 → 게이트 차단"),
    "nemotron-super-49b": ModelSpec("nvidia", "nvidia/llama-3.3-nemotron-super-49b-v1", "2023-12",
                                    "Llama 3.3 베이스", confident=False, reasoning=True,
                                    note="후처리에 2024~25 합성데이터 — 컷오프 상속 불확실 + 추론 토큰"),
}

# 컷오프 게이트를 통과하는 NVIDIA 후보만 프로브 기본 대상으로 삼는다.
PROBE_SHORTLIST = ["llama-3.3-70b", "gemma-3-27b", "llama-3.1-70b", "qwen2.5-7b",
                   "gemma-2-27b", "llama-3.1-405b", "llama-3.1-8b"]
DEFAULT_MODEL = "llama-3.3-70b"


# ── 키 로딩 (원문 비노출) ──────────────────────────────────────────────────────
def load_key(provider: str, key_file: str | None = None) -> tuple[str, str]:
    """(키, 마스킹된 지문)을 돌려준다. 지문에는 키 문자가 한 글자도 들어가지 않는다."""
    cfg = PROVIDERS[provider]
    for env in cfg["envs"]:
        v = os.environ.get(env, "").strip()
        if v:
            return v, f"{cfg['prefix']}…(env {env}, {len(v)}자)"
    cands = [key_file, os.environ.get("IDEA_KEY_FILE"), str(ROOT / "API.txt")]
    for c in cands:
        if not c:
            continue
        p = Path(c).expanduser()
        if not p.exists():
            continue
        m = re.search(re.escape(cfg["prefix"]) + r"[A-Za-z0-9_\-\.]{16,}", p.read_text(encoding="utf-8"))
        if m:
            return m.group(), f"{cfg['prefix']}…({p.name}, {len(m.group())}자)"
    raise SystemExit(
        f"[{provider}] 키를 찾지 못했습니다. 다음 중 하나로 지정하세요:\n"
        f"  export {cfg['envs'][0]}=...        (권장)\n"
        f"  또는 gitignore된 키 파일에 '{cfg['prefix']}...' 를 한 줄 포함 (기본 탐색: API.txt)")


def make_client(provider: str, key_file: str | None = None, timeout: float | None = None):
    from openai import OpenAI
    key, fp = load_key(provider, key_file)
    base = PROVIDERS[provider]["base_url"]
    kw = {"timeout": timeout} if timeout else {}  # 무료 큐 지연(>10분) 대응 — ISS-024
    client = OpenAI(api_key=key, base_url=base, **kw) if base else OpenAI(api_key=key, **kw)
    return client, fp


# ── ISS-012 컷오프 게이트 ─────────────────────────────────────────────────────
def assert_cutoff(spec: ModelSpec, allow_risk: bool = False) -> str:
    """통과하면 'OK', allow_risk로 강행하면 'MEMORIZATION_RISK' 라벨을 돌려준다."""
    if spec.cutoff is None:
        if not allow_risk:
            raise SystemExit(f"[ISS-012] {spec.id}: 학습 컷오프 미확인 → 사용 불가. "
                             f"(강행하려면 --allow-memorization-risk, 결과에 MEMORIZATION_RISK 라벨 필수)")
        return "MEMORIZATION_RISK(컷오프 미확인)"
    if spec.cutoff >= ELECTION_YM:
        if not allow_risk:
            raise SystemExit(f"[ISS-012] {spec.id}: 컷오프 {spec.cutoff} ≥ 선거일 {ELECTION_DATE} → "
                             f"정답 암기 가능. 백테스트 사용 금지.")
        return "MEMORIZATION_RISK(컷오프 이후)"
    if not spec.confident:
        if not allow_risk:
            raise SystemExit(f"[ISS-012] {spec.id}: 컷오프 근거가 1차 출처가 아님({spec.note}) → "
                             f"보수적 차단. 강행 시 --allow-memorization-risk")
        return "MEMORIZATION_RISK(근거 불확실)"
    return "OK"


def describe(key: str, gate: str, fingerprint: str) -> str:
    s = MODELS[key]
    return (f"provider={s.provider} model_id={s.id} cutoff={s.cutoff} "
            f"src={s.cutoff_src or '-'} gate={gate} key={fingerprint}")


# ── 레이트리미터 (무료 티어 RPM 병목) ─────────────────────────────────────────
class RateLimiter:
    """스레드 안전 간격 페이서 — 전역 RPM을 넘지 않게 호출 시각을 배분한다."""

    def __init__(self, rpm: int):
        self.interval = 60.0 / max(rpm, 1) if rpm else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self):
        if not self.interval:
            return
        with self._lock:
            now = time.monotonic()
            t = max(now, self._next)
            self._next = t + self.interval
        d = t - time.monotonic()
        if d > 0:
            time.sleep(d)

    def penalize(self, seconds: float):
        """429를 맞으면 전역 파이프라인을 잠시 뒤로 민다."""
        with self._lock:
            self._next = max(self._next, time.monotonic() + seconds)


_THINK = re.compile(r"<think>.*?</think>|<\|?thinking\|?>.*?<\|?/thinking\|?>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


_SECRET = re.compile(r"(nvapi-|sk-)[A-Za-z0-9_\-\.]{8,}")


def scrub(text: str) -> str:
    """감사 A: 예외 문자열이 원자료에 저장되므로 키 패턴을 무조건 마스킹한다."""
    return _SECRET.sub(r"\1<REDACTED>", str(text))


def clean(text: str | None) -> str:
    if not text:
        return ""
    return _FENCE.sub("", _THINK.sub("", text)).strip()


# ── K 샘플러 ──────────────────────────────────────────────────────────────────
@dataclass
class Sampler:
    client: object
    model_id: str
    k: int = 5
    temperature: float = 1.0
    max_tokens: int = 300
    limiter: RateLimiter | None = None
    retries: int = 4
    n_mode: str | None = None      # None=미확정, "batch"=n=K 1콜, "serial"=K콜
    stats: dict = field(default_factory=lambda: {"requests": 0, "retry": 0, "429": 0})
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _probe: threading.Lock = field(default_factory=threading.Lock)

    def _raw(self, messages, n):
        last = None
        for attempt in range(self.retries):
            if self.limiter:
                self.limiter.acquire()
            try:
                with self._lock:
                    self.stats["requests"] += 1
                kw = dict(model=self.model_id, temperature=self.temperature,
                          max_tokens=self.max_tokens, messages=messages)
                if n > 1:
                    kw["n"] = n
                return self.client.chat.completions.create(**kw)
            except Exception as e:                       # noqa: BLE001
                last = e
                msg = str(e)
                is429 = "429" in msg or "rate" in msg.lower()
                if is429:
                    with self._lock:
                        self.stats["429"] += 1
                    if self.limiter:
                        self.limiter.penalize(5.0 * (attempt + 1))
                if n > 1 and not is429:
                    raise                                 # n 미지원 판정은 상위에서
                with self._lock:
                    self.stats["retry"] += 1
                time.sleep(2.0 * (attempt + 1))
        raise last

    def sample(self, system: str, user: str) -> tuple[list[str], dict]:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        usage = {"in": 0, "out": 0}
        if self.n_mode is None:
            # 감사 C: 8스레드가 동시에 n=K를 찔러 실패콜 8회를 낭비하지 않도록 최초 1회만 탐침
            with self._probe:
                if self.n_mode is None:
                    try:
                        r = self._raw(msgs, self.k)
                        if len(r.choices) >= self.k:
                            self.n_mode = "batch"
                            u = getattr(r, "usage", None)
                            return ([clean(c.message.content) for c in r.choices[:self.k]],
                                    {"in": u.prompt_tokens, "out": u.completion_tokens} if u else usage)
                        self.n_mode = "serial"
                    except Exception:                     # noqa: BLE001
                        self.n_mode = "serial"
        if self.n_mode != "serial":
            try:
                r = self._raw(msgs, self.k)
                if len(r.choices) >= self.k:
                    self.n_mode = "batch"
                    u = getattr(r, "usage", None)
                    if u:
                        usage = {"in": u.prompt_tokens, "out": u.completion_tokens}
                    return [clean(c.message.content) for c in r.choices[:self.k]], usage
                self.n_mode = "serial"                    # n을 받았지만 1개만 준 백엔드
            except Exception:                             # noqa: BLE001
                if self.n_mode is None:
                    self.n_mode = "serial"
                else:
                    raise
        out = []
        for _ in range(self.k):
            r = self._raw(msgs, 1)
            out.append(clean(r.choices[0].message.content))
            u = getattr(r, "usage", None)
            if u:
                usage["in"] += u.prompt_tokens
                usage["out"] += u.completion_tokens
        return out, usage


def add_backend_args(ap):
    """러너 공통 CLI 스위치."""
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default="nvidia")
    ap.add_argument("--model", default=None, help=f"MODELS 키 (기본 nvidia={DEFAULT_MODEL})")
    ap.add_argument("--k", type=int, default=5, help="페르소나당 샘플 수")
    ap.add_argument("--rpm", type=int, default=None, help="분당 요청 상한 (기본: 백엔드별)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--key-file", default=None)
    ap.add_argument("--tag", default=None, help="원자료 파일 접미사 (모델별 분리 저장)")
    ap.add_argument("--allow-memorization-risk", action="store_true")
    return ap


def resolve_backend(args):
    """(sampler_factory, spec_key, spec, gate, tag, fingerprint) 준비."""
    key = args.model or (DEFAULT_MODEL if args.provider == "nvidia" else "gpt-4o-mini")
    if key not in MODELS:
        raise SystemExit(f"알 수 없는 모델 키: {key}\n사용 가능: {', '.join(MODELS)}")
    spec = MODELS[key]
    if spec.provider != args.provider:
        raise SystemExit(f"{key}는 provider={spec.provider} 전용입니다 (--provider {spec.provider})")
    gate = assert_cutoff(spec, args.allow_memorization_risk)
    client, fp = make_client(args.provider, args.key_file)
    rpm = args.rpm if args.rpm is not None else PROVIDERS[args.provider]["rpm"]
    limiter = RateLimiter(rpm)
    sampler = Sampler(client=client, model_id=spec.id, k=args.k, limiter=limiter)
    tag = args.tag if args.tag is not None else ("" if key == "gpt-4o-mini" else key)
    return sampler, key, spec, gate, tag, fp, rpm
