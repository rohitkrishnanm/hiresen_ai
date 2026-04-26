def calculate_overall_score(rules_score: float, llm_quality_score: float, rules_weight: float = 0.4, llm_weight: float = 0.6) -> float:
    rules_score = max(0.0, min(float(rules_score), 100.0))
    llm_score = max(0.0, min(float(llm_quality_score) * 10.0, 100.0))
    overall = (rules_score * rules_weight) + (llm_score * llm_weight)
    return round(overall, 1)


def normalize_llm_score(llm_quality_score: float) -> float:
    return round(max(0.0, min(float(llm_quality_score) * 10.0, 100.0)), 1)