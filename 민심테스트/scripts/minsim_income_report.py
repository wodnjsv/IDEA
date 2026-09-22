"""EXP-016 complete matched-persona income comparison; no human-accuracy claims."""
import json
import argparse
from statistics import mean

from minsim_luna_run import BASE, MODEL, data_dir, resolve, digest, prompt, validate

LABELS = {"E": "소득 동일", "H10": "남편 10% 높음", "H30": "남편 30% 높음",
          "W10": "아내 10% 높음", "W30": "아내 30% 높음"}


def main(model=MODEL):
    gpt55 = model == "gpt-5.5"
    labels = {k: v for k, v in LABELS.items() if not gpt55 or k in {"E", "H30", "W30"}}
    expected = len(labels) * 1200
    out = data_dir() / ("minsim/gpt55_housework_income" if gpt55 else "minsim/luna_housework_income")
    people = {p["pid"]: p for p in map(json.loads, resolve("minsim_full_personas", verify=True).open())}
    question = json.loads(resolve("minsim_income_question", verify=True).read_text())
    keys = list(question["options"])
    schema = {"type": "object", "properties": {k: {"type": "number"} for k in keys},
              "required": keys, "additionalProperties": False}
    selected, attempts = {}, []
    for arm in labels:
        rows = list(map(json.loads, (out / arm / "raw.jsonl").open()))
        selected[arm] = {}
        for r in rows:
            p = people[r["pid"]]
            assert r["model"] == model and r["wave"] == p["wave"]
            assert r["cache_key"] == digest(BASE+model+"low"+prompt(p, question, arm)+json.dumps(schema))
            if r["valid"]:
                assert validate(r["raw"], keys) == r["dist"]
                assert r["runtime"]["model"] == model and r["runtime"]["model_provider"] == "openai"
                assert not r.get("model_reroute") and not r.get("unexpected_items")
                assert r["answers"] == len(p["full_lines"])
                assert all(i["type"] in {"userMessage", "agentMessage", "reasoning"} for i in r["items"])
                selected[arm].setdefault(r["pid"], r)
        assert set(selected[arm]) == set(people), f"incomplete {arm}: {len(selected[arm])}/1200"
        attempts.extend({**r, "condition": arm} for r in rows)
    assert len({r["thread_id"] for arm in selected.values() for r in arm.values()}) == expected
    groups = {"전체": list(people)}
    groups.update({f"연도{w}": [pid for pid, p in people.items() if p["wave"] == w] for w in (2018, 2021, 2023, 2025)})
    groups.update({name: [pid for pid, p in people.items() if p["sex"] == code] for code, name in ((1, "남성"), (2, "여성"))})
    groups.update({name: [pid for pid, p in people.items() if lo <= p["age"] < hi] for lo, hi, name in
                   ((18, 30, "18~29세"), (30, 40, "30대"), (40, 50, "40대"), (50, 60, "50대"), (60, 200, "60세 이상"))})
    result_groups = {}
    for name, ids in groups.items():
        conditions = {arm: {k: mean(selected[arm][pid]["dist"][k] for pid in ids) for k in keys} for arm in labels}
        contrasts = {}
        for arm in list(labels)[1:]:
            contrasts[arm] = {k: mean(selected[arm][pid]["dist"][k]-selected["E"][pid]["dist"][k] for pid in ids) for k in keys}
            assert all(abs(contrasts[arm][k] - (conditions[arm][k]-conditions["E"][k])) < 1e-12 for k in keys)
        incremental = {direction: {k: mean(selected[direction+"30"][pid]["dist"][k]-selected[direction+"10"][pid]["dist"][k] for pid in ids) for k in keys} for direction in ("H", "W") if direction+"10" in labels}
        result_groups[name] = {"n": len(ids), "conditions": conditions, "paired_delta_vs_equal": contrasts,
                               "secondary_delta_30_vs_10": incremental}
    tokens = {k: sum((r.get("usage") or {}).get("total", {}).get(k, 0) for r in attempts)
              for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")}
    blocks = list(map(json.loads, (out / "blocks.jsonl").open()))
    totals = {"attempts": len(attempts), "valid": sum(r["valid"] for r in attempts),
              "failed": sum(not r["valid"] for r in attempts), "duplicate_valid": sum(r["valid"] for r in attempts)-expected,
              "tokens": tokens, "tokens_missing": sum(not r.get("usage") for r in attempts),
              "block_seconds": sum(b["elapsed"] for b in blocks),
              "wall_seconds": max(r["started"]+r["elapsed"] for r in attempts)-min(r["started"] for r in attempts)}
    summary = {"groups": result_groups, "totals": totals, "question": question,
               "mde_plan": json.loads((out / "mde_plan.json").read_text()),
               "uncertainty": {"kind": "none", "reason": "인간 정답과 반복검증이 없어 예측오차 구간 미산출."}}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    top = result_groups["전체"]
    report = "# 남편·아내의 소득 차이에 따라 공정한 가사 분담은 달라질까?\n\n2026-09-14 · EXP-016 · 5조건×동일1,200명 · 합성 응답 · 예측 오차 미산출\n\n"
    report += "## 동일하게 유지한 조건\n\nA는 남편, B는 아내입니다. 둘 다 주40시간 근무하고 건강·출퇴근 시간·가사 숙련도는 같으며, 자녀나 별도 돌봄 대상은 없습니다. 부부의 **합산 세후 근로소득은 모든 조건에서 동일**합니다. 소득이 높은 배우자는 상대보다10% 또는30% 더 법니다(110:100 또는130:100). 가사 비율은 **남편의 몫**을 말합니다.\n\n"
    report += "## 핵심 비교\n\n| 소득 조건 | 남편이 적게 맡기(0·25%) | 반반(50%) | 남편이 많이 맡기(75·100%) | 판단 어려움 | 반반 확률: 동일소득 대비 |\n|---|---:|---:|---:|---:|---:|\n"
    for arm, label in labels.items():
        d = top["conditions"][arm]
        delta = "기준" if arm == "E" else f"{top['paired_delta_vs_equal'][arm]['P50']*100:+.2f}%p"
        report += f"| {label} | {(d['P0']+d['P25'])*100:.2f}% | {d['P50']*100:.2f}% | {(d['P75']+d['P100'])*100:.2f}% | {d['U']*100:.2f}% | {delta} |\n"
    report += "\n각 수치는 그 선택지를 고를 모델 확률의 평균입니다. 남편이 실제로 맡는 평균 가사비율이나 사람들의 실제 투표수가 아닙니다. 차이는 같은페르소나의 조건별 확률을 먼저 뺀 뒤 평균했습니다.\n\n"
    report += "## 여섯 선택지 전체\n\n| 소득 조건 | 남편 거의0% | 약25% | 약50% | 약75% | 거의100% | 판단 어려움 |\n|---|---:|---:|---:|---:|---:|---:|\n"
    for arm, label in labels.items():
        report += "| " + label + " | " + " | ".join(f"{top['conditions'][arm][k]*100:.2f}%" for k in keys) + " |\n"
    if not gpt55:
        report += "\n## 소득 격차10%에서30%로 커질 때\n\n같은 방향에서 30% 조건−10% 조건의 반반 선택확률 차이(보조 기술통계):\n\n"
        report += "\n".join(f"- {label}: {top['secondary_delta_30_vs_10'][direction]['P50']*100:+.2f}%p" for direction, label in (("H", "남편 소득이 높은 경우"), ("W", "아내 소득이 높은 경우"))) + "\n\n"
    report += "\n## 집단별 반반 선택 확률\n\n| 집단 | 인원 | 소득동일 | 남편+10% | 남편+30% | 아내+10% | 아내+30% |\n|---|---:|---:|---:|---:|---:|---:|\n"
    for name, g in result_groups.items():
        if name != "전체":
            report += f"| {name} | {g['n']} | " + " | ".join(f"{g['conditions'][arm]['P50']*100:.2f}%" for arm in labels) + " |\n"
    report += "\n성별은 응답자의 성별이고 연령은 조사 당시 나이입니다. 집단별 전체6선택지와 차분은 summary.json에 보존했습니다. 집단 간 차이는 다른 특성으로 보정하지 않았습니다.\n\n"
    report += "## 실행 기록\n\n- GPT-5.6-Luna, effort low, ChatGPT구독 인증. 별도API키/NVIDIA/리셋크레딧 미사용. 불변스냅샷미확보,공개컷오프2026-02-16,temperature/모델난수시드미제어.\n- 동일1200ID,4개조사연도각300명,개인별214~361개실제상세응답. 기존FULL선정규칙 기반이며 모든원자료변수라는 뜻은 아닙니다.\n- 성별고정 동일소득 기준도 새로 생성했습니다. 성별을 지정하지 않은 EXP-015를 소득효과의 기준으로 사용하지 않았습니다.\n- 동일인물의 선택지순서는 모든조건에서같고,각조건은독립세션입니다. 같은인물블록 내 조건순서를 섞었습니다.\n"
    report += f"- 유효{totals['valid']:,}/6,000,실패시도{totals['failed']}회,중복유효{totals['duplicate_valid']}개. 전원Luna/openai 시작모델확인.\n- 입력{tokens['input_tokens']:,}토큰(캐시{tokens['cached_input_tokens']:,}포함),출력{tokens['output_tokens']:,}토큰. 기록누락{totals['tokens_missing']}건.\n- 블록실행구간합계{totals['block_seconds']/60:.1f}분,첫응답요청~마지막응답{totals['wall_seconds']/60:.1f}분. 총동시64~128개.\n\n"
    report += "## 해석 범위와 검증 상태\n\n- 이 차이는 모델의 조건별 반응이며 실제 국민의 인과효과가 아닙니다. 현재전국대표성·인간응답정확도·반복안정성은 미검증입니다.\n- 실행 전4대비·가족α.05·검정력.8·목표MDE10%p를 기록했습니다. SD상한1의 보수적 정규근사 기획MDE는9.64%p입니다. 실제검정력 보장이나 예측오차구간이 아닙니다. 작은집단은 목표검정력부족으로 기술통계만 제공합니다.\n- 다른모델·질문의 캐시분산은 기획참고자료일뿐 대상분산으로 이식하지 않았습니다. 의미정렬 proxy정정이력은 EXP카드에 보존했습니다.\n- 인간정답과 반복런이 없어 통계적유의성·신뢰구간을 제시하지 않습니다. 작은차이가 안정적인지는 별도검증이 필요합니다.\n- 동일시드에 따른공통난수 재현성을 주장하지 않습니다. 전역Codex지침이 포함되어 있고 불변모델스냅샷은 없습니다.\n- 이유·의견은 수집하지 않았습니다. 원응답은 로컬캐시에 보존하고 이 보고서에 개인별원문을 싣지 않았습니다.\n"
    if gpt55:
        report = (report.replace("EXP-016", "EXP-017").replace("5조건×", "3조건×")
                  .replace("GPT-5.6-Luna", "GPT-5.5").replace("전원Luna/openai", "전원GPT-5.5/openai")
                  .replace("2026-02-16", "2025-12-01").replace("/6,000", "/3,600")
                  .replace("10% 또는30%", "30%").replace("110:100 또는130:100", "130:100")
                  .replace("| 남편+10% | 남편+30% | 아내+10% | 아내+30% |", "| 남편+30% | 아내+30% |")
                  .replace("실행 전4대비", "실행 전2대비").replace("9.64%p", "8.90%p"))
        report = report.replace("| 집단 | 인원 | 소득동일 | 남편+30% | 아내+30% |\n|---|---:|---:|---:|---:|---:|---:|", "| 집단 | 인원 | 소득동일 | 남편+30% | 아내+30% |\n|---|---:|---:|---:|---:|")
        report += "\n기존 Luna 응답은 이 결과에 포함하지 않았습니다. GPT-5.5 동일소득 기준을 포함해 세 조건 모두 새로 생성했습니다.\n"
    (out / "결과보고서.md").write_text(report)
    print(json.dumps({"overall": top, "totals": totals}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=[MODEL, "gpt-5.5"], default=MODEL)
    main(parser.parse_args().model)
