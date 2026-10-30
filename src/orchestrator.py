from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, Callable
from uuid import uuid4

from src.db import persist_run
from src.llm_evaluator import evaluate_proposal
from src.pdf_extractor import extract_pdf
from src.scoring import calculate_results


def _plain(model: Any) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else dict(model)


def evaluate_batch(
    proposals: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
    mock_mode: bool,
    progress_callback: Callable[[int, int], None] | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    total_weight = sum(float(item["weight"]) for item in criteria)
    if not criteria or abs(total_weight - 100) > 0.001:
        raise ValueError(f"Active criterion weights must total exactly 100% (currently {total_weight:g}%).")

    run_id = str(uuid4())
    documents: list[dict[str, Any]] = []
    supplier_inputs: list[dict[str, Any]] = []
    for completed, proposal in enumerate(proposals, start=1):
        name = str(proposal["supplier_name"]).strip()
        warnings: list[str] = []
        try:
            extracted = extract_pdf(proposal["content"])
            if not extracted.text:
                warnings.append("PDF contains no extractable text; human review required.")
        except Exception as error:
            extracted = type("EmptyExtraction", (), {"pages": [], "text": ""})()
            warnings.append(f"PDF extraction failed: {error}")
        document = {
            **proposal,
            "supplier_name": name,
            "sha256": sha256(proposal["content"]).hexdigest(),
            "page_count": len(extracted.pages),
            "text": extracted.text,
        }
        documents.append(document)
        try:
            evaluation = evaluate_proposal(name, extracted.pages, criteria, api_key, model_name)
            raw = _plain(evaluation)
        except Exception as error:
            raw = {"supplier_name": name, "criteria": [], "risks": [str(error)],
                   "missing_information": [], "overall_summary": "Evaluation unavailable.",
                   "commercial_facts": {}}
            warnings.append(str(error))

        raw_by_id: dict[int, dict[str, Any]] = {}
        for item in raw.get("criteria", []):
            criterion_id = int(item.get("criterion_id", -1))
            if criterion_id in raw_by_id:
                warnings.append(f"Duplicate result for criterion {criterion_id}; first result kept.")
                continue
            raw_by_id[criterion_id] = item

        scores: dict[str, float] = {}
        score_details: list[dict[str, Any]] = []
        for criterion in criteria:
            criterion_id = int(criterion["criterion_id"])
            item = raw_by_id.get(criterion_id)
            if item is None:
                warnings.append(f"Missing score for {criterion['name']}; zero used.")
                item = {}
            raw_score = item.get("score")
            try:
                score = float(raw_score) if raw_score is not None else 0.0
            except (TypeError, ValueError):
                score = 0.0
                warnings.append(f"Malformed score for {criterion['name']}; zero used.")
            maximum = float(criterion["max_score"])
            if score < 0 or score > maximum:
                warnings.append(f"Out-of-range score for {criterion['name']} was clamped to 0-{maximum:g}.")
                score = min(max(score, 0), maximum)
            if raw_score is not None:
                scores[str(criterion_id)] = score

            evidence = str(item.get("evidence") or "").strip()
            quote_normalized = re.sub(r"\s+", " ", evidence).strip()
            text_normalized = re.sub(r"\s+", " ", extracted.text).strip()
            verified = bool(quote_normalized and quote_normalized in text_normalized)
            evidence_status = "verified" if verified else ("unverified" if evidence else "missing")
            if evidence and not verified:
                warnings.append(f"Evidence quote for {criterion['name']} could not be verified against extracted PDF text.")
            page_number = item.get("page_number")
            if page_number is not None:
                try:
                    if not 1 <= int(page_number) <= len(extracted.pages):
                        warnings.append(f"Invalid evidence page for {criterion['name']}; page removed.")
                        page_number = None
                except (TypeError, ValueError):
                    warnings.append(f"Invalid evidence page for {criterion['name']}; page removed.")
                    page_number = None
            score_details.append({
                "criterion_id": criterion_id,
                "score": score,
                "justification": str(item.get("justification") or "No justification provided."),
                "evidence": evidence or None,
                "page_number": page_number,
                "evidence_status": evidence_status,
            })

        supplier_inputs.append({
            "supplier_name": name,
            "submission_date": str(proposal["submission_date"]),
            "experience_rating": float(proposal["experience_rating"]),
            "scores": scores,
            "warnings": warnings,
            "overall_summary": raw.get("overall_summary", ""),
            "strengths": [item["justification"] for item in score_details if item["score"] > 0],
            "risks": raw.get("risks", []),
            "missing_information": raw.get("missing_information", []),
            "commercial_facts": raw.get("commercial_facts", {}),
            "raw_evaluation": raw,
            "score_details": score_details,
            "evaluation_mode": "MOCK" if mock_mode else "LIVE LLM",
            "evaluation_model": "mock-heuristic" if mock_mode else model_name,
        })
        if progress_callback is not None:
            progress_callback(completed, len(proposals))

    results = calculate_results(supplier_inputs, criteria)
    for result in results:
        detail_by_id = {item["criterion_id"]: item for item in result["score_details"]}
        for criterion_result in result["criteria"]:
            criterion_result.update(detail_by_id.get(criterion_result["criterion_id"], {}))
        result["rfp_run_id"] = run_id
        result["tie_break_explanation"] = "Ranked by PPI descending, submission date ascending, experience descending, then supplier name ascending."
        if result["score_coverage"] < 70:
            result["warnings"].append("Low score coverage; human review required.")

    status = "completed" if all(result["score_coverage"] == 100 for result in results) else "completed_with_warnings"
    persist_run(run_id, criteria, results, documents, status)
    return run_id, results