from __future__ import annotations

from datetime import date
from typing import Any


def calculate_results(
    suppliers: list[dict[str, Any]], criteria: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Calculate absolute scores and cohort-relative metrics deterministically."""
    criterion_metrics: dict[str, dict[str, float]] = {}
    for criterion in criteria:
        criterion_id = str(criterion["criterion_id"])
        maximum = float(criterion["max_score"])
        normalized_scores = [
            min(max(float(supplier.get("scores", {}).get(criterion_id, 0) or 0), 0), maximum)
            / maximum * 100
            for supplier in suppliers
        ]
        benchmark = max(normalized_scores, default=0)
        criterion_metrics[criterion_id] = {
            "benchmark": benchmark,
            "relative": benchmark,
        }

    results: list[dict[str, Any]] = []
    for supplier in suppliers:
        criterion_results: list[dict[str, Any]] = []
        absolute_score = 0.0
        ppi = 0.0
        industrial_numerator = 0.0
        industrial_denominator = 0.0
        covered_weight = 0.0
        total_weight = 0.0

        for criterion in criteria:
            criterion_id = str(criterion["criterion_id"])
            weight = float(criterion["weight"])
            maximum = float(criterion["max_score"])
            raw_score = supplier.get("scores", {}).get(criterion_id)
            score = min(max(float(raw_score or 0), 0), maximum)
            normalized = score / maximum * 100
            benchmark = criterion_metrics[criterion_id]["benchmark"]
            relative = normalized / benchmark * 100 if benchmark else (100 if normalized == 0 else 0)
            gap = normalized - benchmark
            industrial_weight = float(criterion.get("industrial_relevance_weight", weight))

            absolute_score += normalized * weight / 100
            ppi += relative * weight / 100
            industrial_numerator += normalized * industrial_weight
            industrial_denominator += industrial_weight
            total_weight += weight
            if raw_score is not None:
                covered_weight += weight

            criterion_results.append({
                "criterion_id": criterion["criterion_id"],
                "name": criterion["name"],
                "score": score,
                "max_score": maximum,
                "weight": weight,
                "normalized_score": normalized,
                "weighted_contribution": normalized * weight / 100,
                "benchmark": benchmark,
                "gap": gap,
                "relative_percent": relative,
                "zero_benchmark": benchmark == 0,
                "industrial_relevance_weight": industrial_weight,
            })

        results.append({
            **supplier,
            "criteria": criterion_results,
            "absolute_score": absolute_score,
            "ppi": ppi,
            "ifi": industrial_numerator / industrial_denominator if industrial_denominator else 0,
            "score_coverage": covered_weight / total_weight * 100 if total_weight else 0,
            "warnings": list(supplier.get("warnings", [])),
        })

    def tie_break_key(result: dict[str, Any]) -> tuple[float, date, float, str]:
        try:
            submission = date.fromisoformat(str(result.get("submission_date", "9999-12-31")))
        except ValueError:
            submission = date.max
        return (
            -result["ppi"],
            submission,
            -float(result.get("experience_rating", 0) or 0),
            str(result.get("supplier_name", "")).casefold(),
        )

    for rank, result in enumerate(sorted(results, key=tie_break_key), start=1):
        result["final_rank"] = rank
    return sorted(results, key=lambda result: result["final_rank"])