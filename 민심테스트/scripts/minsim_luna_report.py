"""EXP-014 descriptive aggregation, no majority vote or national weighting."""
import json
import sys
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from engine.registry import data_dir, resolve
from minsim_luna_run import KEYS, validate, prompt, digest, BASE, MODEL, SCHEMA


def main():
    out = data_dir() / "minsim/luna_parent70"
    people = {p["pid"]: p for p in map(json.loads, resolve("minsim_full_personas", verify=True).open())}
    attempts = [json.loads(s) for s in (out / "raw.jsonl").open()]
    question = next(q for q in json.loads(resolve("minsim_six_questions", verify=True).read_text())["items"]
                    if q["id"] == "parent_support")
    selected = {}
    for r in attempts:
        if r["valid"]:
            p = people[r["pid"]]
            assert r["model"] == MODEL and r["wave"] == p["wave"]
            assert r["cache_key"] == digest(BASE + MODEL + "low" + prompt(p, question) + json.dumps(SCHEMA))
            assert r["answers"] == len(p["full_lines"])
            assert not r.get("model_reroute") and not r.get("unexpected_items")
            assert all(i["type"] in {"userMessage", "agentMessage", "reasoning"} for i in r["items"])
            if "runtime" in r:
                assert r["runtime"]["model"] == MODEL and r["runtime"]["model_provider"] == "openai"
            assert validate(r["raw"]) == r["dist"]
            selected.setdefault(r["pid"], r)
    assert set(selected) == set(people), f"incomplete: {len(selected)}/1200"
    assert len({r["thread_id"] for r in selected.values()}) == 1200
    rows = list(selected.values())

    def group(name, subset):
        d = {k: mean(r["dist"][k] for r in subset) for k in KEYS}
        return {"group": name, "n": len(subset), "dist": d,
                "support": d["SA"] + d["A"], "oppose": d["D"] + d["SD"],
                "neutral": d["N"], "uncertain": d["U"]}

    overall = group("전체", rows)
    waves = [group(str(w), [r for r in rows if r["wave"] == w]) for w in (2018, 2021, 2023, 2025)]
    sexes = [group(label, [r for r in rows if people[r["pid"]]["sex"] == code])
             for code, label in ((1, "남성"), (2, "여성"))]
    ages = [group(label, [r for r in rows if low <= people[r["pid"]]["age"] < high])
            for low, high, label in ((0, 30, "29세 이하"), (30, 40, "30대"), (40, 50, "40대"),
                                    (50, 60, "50대"), (60, 200, "60세 이상"))]
    tokens = {k: sum((r.get("usage") or {}).get("total", {}).get(k, 0) for r in attempts)
              for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")}
    launches = sorted((json.loads(p.read_text()) for p in out.glob("launch-*.json")), key=lambda x: x["started"])
    speeds = []
    for i, launch in enumerate(launches):
        end = launches[i+1]["started"] if i+1 < len(launches) else float("inf")
        batch = [r for r in attempts if launch["started"] <= r["started"] < end]
        if batch:
            duration = max(r["started"] + r["elapsed"] for r in batch) - min(r["started"] for r in batch)
            speeds.append({"concurrency": launch["concurrency"], "attempts": len(batch),
                           "valid": sum(r["valid"] for r in batch), "seconds": duration,
                           "median_seconds_per_person": median(r["elapsed"] for r in batch),
                           "completed_per_minute": len(batch) / duration * 60})
    result = {"overall": overall, "waves": waves, "sexes": sexes, "ages": ages,
              "attempts": len(attempts), "failed": sum(not r["valid"] for r in attempts),
              "duplicates_valid": sum(r["valid"] for r in attempts) - len(selected),
              "runtime_model_recorded": sum("runtime" in r for r in rows), "tokens": tokens,
              "tokens_missing": sum(not r.get("usage") for r in attempts), "speeds": speeds,
              "generation_active_seconds": sum(s["seconds"] for s in speeds),
              "wall_seconds": max(r["started"] + r["elapsed"] for r in attempts) - min(r["started"] for r in attempts),
              "uncertainty": {"kind": "none", "reason": "실측 정답지와 반복 실행이 없어 예측 오차와 불확실성 구간을 산출하지 않음."}}
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))

    def table(groups):
        return "| 집단 | 인원 | 동의 | 비동의 | 중립 | 판단 어려움 |\n|---|---:|---:|---:|---:|---:|\n" + "\n".join(
            f"| {g['group']} | {g['n']} | {g['support']*100:.1f}% | {g['oppose']*100:.1f}% | {g['neutral']*100:.1f}% | {g['uncertain']*100:.1f}% |" for g in groups)

    report = "# 부모가 집값을 보태면 부모님 의견도 더 따라야 할까?\n\n"
    report += "2026-09-14 · EXP-014 · 과거 설문 응답자 1,200명의 합성 응답 · 예측 오차 미산출\n\n"
    report += "## 질문 조건\n\n부모가 집값의 **70%를 상환 조건 없이 지원**합니다. 거주 지역에 관한 사전 약속은 없고, 부모와 성인 자녀 부부가 원하는 지역이 다릅니다. 이때 **자녀 부부가 거주 지역 선택에서 부모의 의견을 우선해야 하는가**를 물었습니다.\n\n"
    report += "## 전체 결과\n\n" + table([overall]) + "\n\n"
    report += "각 인물에게 여섯 선택지의 확률을 받고, 1,200명의 확률을 같은 비중으로 평균했습니다. 실제 1,200명이 투표한 결과나 현재 전국민 여론의 추정치는 아닙니다.\n\n"
    report += "| 선택지 | 평균 확률 |\n|---|---:|\n"
    names = ["매우 동의", "대체로 동의", "동의도 비동의도 아님", "대체로 비동의", "전혀 동의하지 않음", "판단하기 어려움"]
    report += "\n".join(f"| {name} | {overall['dist'][k]*100:.2f}% |" for name, k in zip(names, KEYS))
    report += "\n\n## 조사 연도별\n\n" + table(waves)
    report += "\n\n서로 다른 조사연도의 표본이며 문항 구성도 다릅니다. 연도 차이를 사회의 태도 변화로 해석할 수 없습니다.\n\n## 성별\n\n" + table(sexes)
    report += "\n\n## 조사 당시 연령별\n\n" + table(ages)
    report += "\n\n성별·연령별 결과는 연도·직업·가족상황 등의 차이를 보정하지 않은 기술 통계입니다.\n\n## 입력과 실행 기록\n\n"
    report += "- 2018·2021·2023·2025년 각 300명. 기존 실험과 동일한 1,200개 ID를 원자료와 대조했습니다.\n- 1명당 실제 설문 응답 214~361개를 생략 없이 입력했습니다. 기존 FULL 변수 선정 규칙(연도별 유효응답률 30% 이상)에 따른 응답이며, 원자료의 모든 변수라는 의미는 아닙니다.\n- 원래 상세 응답이 비어 있던 2021·2025년 600명도 원자료에서 복원했습니다. 관리용 가구번호는 제외했습니다.\n"
    report += f"- 요청 모델 GPT-5.6-Luna, effort low, ChatGPT 구독, 독립 세션 1,200개. 성공 {len(rows)}/1,200, 실패 시도 {result['failed']}회, 중복 유효 {result['duplicates_valid']}개.\n"
    report += f"- 입력 토큰 {tokens['input_tokens']:,}(그중 캐시 {tokens['cached_input_tokens']:,}), 출력 {tokens['output_tokens']:,}. 사용량 기록 누락 {result['tokens_missing']}건.\n"
    report += "- 별도 API 키 과금 경로는 사용하지 않았습니다. 계정 주간 사용량 표시는 실행 전 0%에서 실행 후 2%로 바뀌었습니다. 다른 작업도 포함된 계정 전체 값이며 실험 단독 차감량은 아닙니다.\n"
    report += "- 공개 모델 지식 컷오프 2026-02-16. 불변 스냅샷 미확보, temperature와 모델 난수 시드는 제어하지 않았습니다.\n"
    report += f"- 생성 실행 구간 합계 {result['generation_active_seconds']/60:.1f}분. 점검·재시작 간격을 포함한 첫 요청~마지막 응답 {result['wall_seconds']/60:.1f}분.\n"
    report += "\n| 동시 세션 설정 | 처리 건수 | 유효 | 구간 소요 | 분당 완료 |\n|---:|---:|---:|---:|---:|\n"
    report += "\n".join(f"| {s['concurrency']} | {s['attempts']} | {s['valid']} | {s['seconds']:.1f}초 | {s['completed_per_minute']:.1f} |" for s in speeds)
    report += "\n\n동시 세션 설정은 이 실험에서 시도한 값이며, 서비스가 보장하는 최대 허용 수가 아닙니다.\n\n## 해석 범위와 미검증 사항\n\n"
    report += "- 실제 정답 설문이 없어 정확도와 예측 오차를 검증하지 않았습니다. 1회 실행이므로 반복 안정성도 미검증입니다. 신뢰구간은 제시하지 않습니다.\n- 70% 조건만 실행했습니다. 지원액이 늘면 동의가 얼마나 바뀌는지는 이 결과로 알 수 없습니다.\n- 원설문의 부모 지원·부모 의견 관련 태도는 예측 입력입니다. 이번 가상 상황과 같은 정답지로 채점한 실험이 아닙니다.\n- 숫자는 모델이 발화한 확률입니다. 균등 6선택지 각 16.67%는 무정보 참조일 뿐이며, 이를 이겼다는 성능 주장은 하지 않습니다.\n- 간단한 의견·이유는 이번 실행에서 수집하지 않았습니다. 결과를 보고 그럴듯한 이유를 지어내지 않았습니다.\n"
    report += f"- 시작 반환 모델과 provider를 기록한 응답은 {result['runtime_model_recorded']}건입니다. 초기 108건은 요청 모델·가용 카탈로그만 기록했습니다. 불변 모델 스냅샷은 확보하지 못했습니다.\n"
    report += "- 도구를 비활성화했고 완료 기록에서 도구 호출은 발견되지 않았습니다. 전역 Codex AGENTS 지침은 포함되어 있어 순수 채팅 API와 완전히 같은 실행 환경은 아닙니다.\n- 원문 응답은 로컬 캐시에 보관했습니다. 이 보고서에는 개인별 원문을 싣지 않습니다.\n"
    (out / "결과보고서.md").write_text(report)
    print(json.dumps({"overall": overall, "tokens": tokens, "speeds": speeds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
