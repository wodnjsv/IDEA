"""EXP-015: equal-hours housework choice probabilities, descriptive only."""
import json
from statistics import mean, median

from minsim_luna_run import BASE, MODEL, data_dir, resolve, digest, prompt, validate


def main():
    out = data_dir() / "minsim/luna_housework_A"
    people = {p["pid"]: p for p in map(json.loads, resolve("minsim_full_personas", verify=True).open())}
    question = next(q for q in json.loads(resolve("minsim_six_questions", verify=True).read_text())["items"]
                    if q["id"] == "housework")
    keys = list(question["options"])
    schema = {"type": "object", "properties": {k: {"type": "number"} for k in keys},
              "required": keys, "additionalProperties": False}
    attempts = list(map(json.loads, (out / "raw.jsonl").open()))
    selected = {}
    for r in attempts:
        p = people[r["pid"]]
        assert r["cache_key"] == digest(BASE + MODEL + "low" + prompt(p, question, "A") + json.dumps(schema))
        assert r["wave"] == p["wave"] and r["model"] == MODEL
        if r["valid"]:
            assert validate(r["raw"], keys) == r["dist"]
            assert r["answers"] == len(p["full_lines"])
            assert r["runtime"]["model"] == MODEL and r["runtime"]["model_provider"] == "openai"
            assert not r.get("model_reroute") and not r.get("unexpected_items")
            assert all(i["type"] in {"userMessage", "agentMessage", "reasoning"} for i in r["items"])
            selected.setdefault(r["pid"], r)
    assert set(selected) == set(people), f"incomplete: {len(selected)}/1200"
    assert len({r["thread_id"] for r in selected.values()}) == 1200
    rows = list(selected.values())

    def group(label, subset):
        return {"group": label, "n": len(subset), "dist": {k: mean(r["dist"][k] for r in subset) for k in keys}}

    overall = group("전체", rows)
    waves = [group(str(w), [r for r in rows if r["wave"] == w]) for w in (2018, 2021, 2023, 2025)]
    sexes = [group(label, [r for r in rows if people[r["pid"]]["sex"] == code])
             for code, label in ((1, "남성"), (2, "여성"))]
    ages = [group(label, [r for r in rows if low <= people[r["pid"]]["age"] < high])
            for low, high, label in ((18, 30, "18~29세"), (30, 40, "30대"), (40, 50, "40대"),
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
    summary = {"question": question, "condition": "A", "overall": overall, "waves": waves,
               "sexes": sexes, "ages": ages, "attempts": len(attempts),
               "failed": sum(not r["valid"] for r in attempts),
               "duplicates_valid": sum(r["valid"] for r in attempts) - len(rows),
               "tokens": tokens, "tokens_missing": sum(not r.get("usage") for r in attempts),
               "speeds": speeds, "generation_active_seconds": sum(s["seconds"] for s in speeds),
               "wall_seconds": max(r["started"] + r["elapsed"] for r in attempts) - min(r["started"] for r in attempts),
               "uncertainty": {"kind": "none", "reason": "실측정답 및 반복실행 없음. 예측오차 미산출."}}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    def table(groups):
        head = "| 집단 | 인원 | A 거의0% | A 약25% | A 약50% | A 약75% | A 거의100% | 판단 어려움 |\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
        return head + "\n".join(f"| {g['group']} | {g['n']} | " + " | ".join(f"{g['dist'][k]*100:.1f}%" for k in keys) + " |" for g in groups)

    report = "# 부부의 집안일은 반반이 공정할까?\n\n2026-09-14 · EXP-015 · 과거 응답자 기반 합성 응답 · 예측 오차 미산출\n\n"
    report += "## 질문 조건\n\n**A와 B 모두 주 40시간 근무**합니다. 건강·소득·출퇴근 시간·가사 숙련도는 같고, 자녀나 별도 돌봄 대상이 없습니다. **전체 가사노동 시간 중 A가 맡을 비율**을 물었습니다. A와 B의 성별은 지정하지 않았습니다.\n\n"
    report += "## 전체 결과\n\n| A의 가사 분담 선택지 | 해당 선택지의 평균 응답 확률 |\n|---|---:|\n"
    report += "\n".join(f"| {question['options'][k]} | {overall['dist'][k]*100:.2f}% |" for k in keys)
    report += "\n\n표의 결과는 각 선택지를 고를 모델 확률의 1,200명 평균입니다. 예를 들어 ‘A 약50%’ 열의 값은 반반 분담을 선택할 확률이며, A의 평균 가사 분담률 자체가 아닙니다.\n\n"
    for title, groups in (("조사 당시 연령별", ages), ("응답자 성별", sexes), ("원자료 조사 연도별", waves)):
        report += "## " + title + "\n\n" + table(groups) + "\n\n"
    report += "성별 표는 응답자의 성별 구분입니다. 시나리오 속 A/B를 남편/아내로 지정한 결과가 아닙니다. 연령·성별 차이는 다른 특성을 보정하지 않았으며, 조사연도 차이는 시계열 변화로 해석할 수 없습니다.\n\n"
    report += "## 실행과 입력\n\n- GPT-5.6-Luna, effort low, ChatGPT 구독 로그인 강제. 별도 유료 API키/NVIDIA 경로 미사용. 불변 스냅샷 미확보, 공개 컷오프2026-02-16, 모델 난수시드·temperature 미제어.\n- 같은 1,200명: 2018·2021·2023·2025년 각300명. 한 사람당214~361개 상세 설문 응답을 입력. 조사시점 정보 유지, 현재 상태로 갱신하지 않음.\n- 상세 응답은 기존 FULL 선정 규칙(연도별 유효응답률30%이상)이며 원자료 모든 변수와 같지는 않습니다.\n"
    report += f"- 독립 세션1,200개, 유효1,200명, 실패시도{summary['failed']}회, 중복유효{summary['duplicates_valid']}개. 전원 시작반환모델 Luna/openai 확인.\n"
    report += f"- 입력{tokens['input_tokens']:,}토큰(캐시{tokens['cached_input_tokens']:,} 포함), 출력{tokens['output_tokens']:,}토큰. 토큰기록누락{summary['tokens_missing']}건.\n"
    report += "- 이번 실행 전후 계정 주간 사용량 표시는2%→3%였습니다. 다른 작업도 포함된 계정 전체 값이므로 실험 단독 차감량과 같지는 않습니다.\n"
    report += f"- 생성구간 합계{summary['generation_active_seconds']/60:.1f}분, 중간점검포함{summary['wall_seconds']/60:.1f}분.\n\n"
    report += "| 동시 세션 설정 | 처리 건수 | 유효 | 소요 | 분당 완료 |\n|---:|---:|---:|---:|---:|\n"
    report += "\n".join(f"| {s['concurrency']} | {s['attempts']} | {s['valid']} | {s['seconds']:.1f}초 | {s['completed_per_minute']:.1f} |" for s in speeds)
    report += "\n\n## 해석 범위\n\n- 실제 전국민 여론조사 결과가 아닙니다. 과거 표본의 모델 확률을 같은 비중으로 평균했으며 전국 대표 가중치는 사용하지 않았습니다.\n- 정답 설문과 반복실행이 없어 정확도·오차범위·반복 안정성을 검증하지 않았습니다.\n- 근로시간이 같은 한 조건만 실행했습니다. 근로시간 차이의 효과나 실제 부부의 행동을 추정하지 않습니다.\n- 관련 원설문 가사·가족 태도는 입력 자료이며 이 시나리오의 정답지로 채점한 것은 아닙니다.\n- 균등6선택지 각16.67%는 무정보 참조일 뿐, 그보다 정확하다는 주장은 하지 않습니다.\n- 선택지별 확률을 보존했습니다. 판단어려움을0%로 취급한 평균 가사비율이나 최빈값 투표를 계산하지 않았습니다.\n- 이유·간단한 의견은 수집하지 않았습니다. 전역 Codex AGENTS 지침은 포함되어 있습니다. 도구호출은 완료응답에서 발견되지 않았습니다.\n- 개인별 원문은 로컬 캐시에 보관하며 이 보고서에 노출하지 않습니다.\n"
    (out / "결과보고서.md").write_text(report)
    print(json.dumps({"overall": overall, "tokens": tokens, "speeds": speeds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
