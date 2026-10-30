from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from config.settings import MAX_PDF_SIZE_MB, MOCK_MODE
from src.charts import criterion_heatmap, experience_scatter, ppi_chart, score_chart
from src.db import get_audit_log, get_criteria, get_run_ids, get_run_results, initialize_database, save_criterion
from src.exports import leaderboard_csv, results_json
from src.orchestrator import evaluate_batch
from src.openai_access import validate_api_key_and_list_models
from src.validation import validate_uploads

st.set_page_config(page_title="RFP Supplier Evaluation", page_icon="📊", layout="wide")
initialize_database()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --ink:#14213d; --blue:#2f75ff; --teal:#16b8a6; --green:#41a36a; --orange:#e99436; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
h1,h2,h3 { font-family:'Space Grotesk',sans-serif; color:var(--ink); letter-spacing:0; }
.block-container { padding-top:1.6rem; max-width:1440px; }
[data-testid="stMetric"] { background:linear-gradient(135deg,#f3f7ff,#e7faf7); border:1px solid #dce8f4; padding:16px; border-radius:8px; }
[data-testid="stMetricValue"] { color:#14213d; }
.mode-banner { border-left:4px solid #e99436; background:#fff4e5; padding:10px 14px; border-radius:4px; }
.live-banner { border-left:4px solid #16b8a6; background:#e9fbf7; padding:10px 14px; border-radius:4px; }
</style>
""", unsafe_allow_html=True)

st.title("RFP Supplier Evaluation")
st.caption("Evidence-led proposal review · deterministic scoring · auditable supplier comparisons")
selected_model = None
live_ready = False
with st.sidebar:
    st.subheader("Live evaluation access")
    if MOCK_MODE:
        st.info("Mock mode is active. API credentials are not required or used.")
    else:
        api_key_input = st.text_input("OpenAI API key", type="password", key="api_key_input",
                                      help="Used only for this Streamlit session; never saved to the database or files.")
        if api_key_input != st.session_state.get("validated_api_key", ""):
            st.session_state.pop("validated_api_key", None)
            st.session_state.pop("available_models", None)
            st.session_state.pop("selected_model", None)
        if st.button("Validate key and load models", disabled=not api_key_input):
            try:
                models = validate_api_key_and_list_models(api_key_input)
                st.session_state["validated_api_key"] = api_key_input
                st.session_state["available_models"] = models
                st.session_state["selected_model"] = models[0]
                st.success(f"Key validated. {len(models)} chat model(s) available.")
            except Exception as error:
                st.session_state.pop("validated_api_key", None)
                st.session_state.pop("available_models", None)
                st.error(f"Key validation failed: {error}")
        available_models = st.session_state.get("available_models", [])
        if available_models and st.session_state.get("validated_api_key") == api_key_input:
            selected_model = st.selectbox("Evaluation model", available_models, key="selected_model")
            st.caption("Only model IDs returned by the validated account are shown.")
        else:
            selected_model = None
            st.caption("Enter and validate an API key to choose an available model.")
        live_ready = bool(selected_model and st.session_state.get("validated_api_key") == api_key_input)

if MOCK_MODE:
    st.markdown('<div class="mode-banner"><b>MOCK MODE ENABLED</b> · Demo heuristic only; not a live AI evaluation and not suitable for procurement decisions.</div>', unsafe_allow_html=True)
elif live_ready:
    st.markdown(f'<div class="live-banner"><b>Live evaluation ready</b> · Validated model: {selected_model}. Human review remains required.</div>', unsafe_allow_html=True)
else:
    st.warning("Live evaluation is locked until an OpenAI API key is validated in the sidebar and an available model is selected. Demo evaluation can only be enabled explicitly with RFP_MOCK_MODE=true.")

evaluation_tab, leaderboard_tab, vendor_tab, criteria_tab = st.tabs([
    "Evaluation", "Leaderboard", "Vendor Evaluation Results", "RFP Criteria & Weight Management"
])

with evaluation_tab:
    st.subheader("Evaluate a proposal batch")
    st.write("Upload the complete comparison cohort in one run. All proposals in the batch share the same criteria snapshot.")
    uploads = st.file_uploader(
        "Proposal PDFs", type=["pdf"], accept_multiple_files=True,
        help=f"Upload multiple proposals together, including all five vendors. Maximum {MAX_PDF_SIZE_MB} MB each.",
    )
    proposals: list[dict[str, Any]] = []
    for index, uploaded in enumerate(uploads or []):
        stem = Path(uploaded.name).stem
        default_name = stem.split("_", 1)[-1].replace("_", " ").replace("-", " ").strip().title()
        with st.container(border=True):
            st.markdown(f"**Proposal {index + 1}:** `{uploaded.name}`")
            name_col, date_col, rating_col = st.columns([2, 1, 1])
            supplier_name = name_col.text_input("Supplier name", value=default_name,
                                                key=f"supplier_{index}_{uploaded.name}")
            submitted = date_col.date_input("Submission date", value=date.today(),
                                            key=f"date_{index}_{uploaded.name}")
            experience = rating_col.slider("Historical experience (0-10)", 0.0, 10.0, 5.0, 0.5,
                                           key=f"experience_{index}_{uploaded.name}")
            proposals.append({"filename": uploaded.name, "content": uploaded.getvalue(),
                              "supplier_name": supplier_name, "submission_date": submitted.isoformat(),
                              "experience_rating": experience})

    criteria = get_criteria(active_only=True)
    active_weight = sum(float(item["weight"]) for item in criteria)
    weight_col, count_col = st.columns(2)
    weight_col.metric("Active criteria weight", f"{active_weight:g}%", "Ready" if abs(active_weight - 100) < 0.001 else "Must total 100%")
    count_col.metric("Proposals in batch", len(proposals), "All will be compared together")
    if proposals:
        for error in validate_uploads(proposals):
            st.error(error)
    if abs(active_weight - 100) > 0.001:
        st.error("Evaluation is disabled until active criteria weights total exactly 100%.")
    can_evaluate = (bool(proposals) and not validate_uploads(proposals)
                    and abs(active_weight - 100) < 0.001 and (MOCK_MODE or live_ready))
    evaluate_clicked = st.button("Evaluate batch", type="primary", disabled=not can_evaluate, icon="📈")
    if evaluate_clicked:
        progress = st.progress(0, text="Starting proposal evaluation")
        status_text = st.empty()
        try:
            def update_progress(done: int, total: int) -> None:
                progress.progress(done / total, text=f"Evaluated {done} of {total} proposals")
                status_text.caption(f"Processing proposal {done} of {total}")

            run_id, results = evaluate_batch(
                proposals, criteria, MOCK_MODE, update_progress,
                st.session_state.get("validated_api_key"), selected_model,
            )
            st.session_state["active_run_id"] = run_id
            progress.progress(1.0, text="Batch saved")
            st.success(f"Run `{run_id}` completed with {len(results)} proposals. Open the comparison tabs below.")
            if any(item["warnings"] for item in results):
                st.warning("Some proposals have review warnings. Check the vendor results before relying on the ranking.")
            st.rerun()
        except Exception as error:
            progress.empty()
            st.error(f"Batch could not be completed: {error}")

with leaderboard_tab:
    st.subheader("Supplier leaderboard")
    run_ids = get_run_ids()
    if not run_ids:
        st.info("Evaluate a proposal batch to populate the leaderboard.")
    else:
        selected_run = st.selectbox("Evaluation run", run_ids,
                                   index=run_ids.index(st.session_state["active_run_id"]) if st.session_state.get("active_run_id") in run_ids else 0,
                                   key="leaderboard_run")
        results = get_run_results(selected_run)
        if results:
            leader = results[0]
            metric_cols = st.columns(4)
            metric_cols[0].metric("Rank 1 supplier", leader["supplier_name"])
            metric_cols[1].metric("Top absolute score", f"{leader['absolute_score']:.1f} / 100")
            metric_cols[2].metric("Top PPI", f"{leader['ppi']:.1f}")
            metric_cols[3].metric("Vendors compared", len(results))
            frame = pd.DataFrame([{
                "Rank": item["final_rank"], "Supplier": item["supplier_name"],
                "Absolute score": item["absolute_score"], "PPI": item["ppi"],
                "Submission date": item["submission_date"], "Experience": item["experience_rating"],
                "Project-defined IFI": item["ifi"], "Score coverage": item["score_coverage"],
            } for item in results])
            st.dataframe(frame, hide_index=True, use_container_width=True)
            chart_left, chart_right = st.columns(2)
            chart_left.plotly_chart(score_chart(results), use_container_width=True)
            chart_right.plotly_chart(ppi_chart(results), use_container_width=True)
            st.caption("IFI is project-defined, not an industry-standard certification or benchmark. Formula: normalized score × industrial relevance weight, divided by total relevance weight.")
            st.plotly_chart(criterion_heatmap(results), use_container_width=True)
            st.subheader("Criterion gaps from cohort leader")
            gap_rows = [{"Supplier": item["supplier_name"], "Criterion": criterion["name"],
                         "Gap (points)": criterion["gap"], "Relative performance (%)": criterion["relative_percent"]}
                        for item in results for criterion in item["criteria"]]
            st.dataframe(pd.DataFrame(gap_rows), hide_index=True, use_container_width=True)
            st.plotly_chart(experience_scatter(results), use_container_width=True)
            currencies = {item.get("commercial_facts", {}).get("currency") for item in results}
            prices = [item.get("commercial_facts", {}).get("total_cost") for item in results]
            if len(currencies) == 1 and None not in currencies and all(value is not None for value in prices):
                st.subheader("Commercial comparison")
                st.dataframe(pd.DataFrame([{"Supplier": item["supplier_name"],
                    "Currency": item["commercial_facts"].get("currency"),
                    "Total cost": item["commercial_facts"].get("total_cost"),
                    "Assumptions": "; ".join(item["commercial_facts"].get("assumptions", []))}
                    for item in results]), hide_index=True, use_container_width=True)
            else:
                st.info("Commercial prices are not comparable: complete total-cost values in one common currency were not available for every supplier.")
            export_left, export_right = st.columns(2)
            export_left.download_button("Download complete results (JSON)", results_json(results),
                                        file_name=f"{selected_run}.json", mime="application/json")
            export_right.download_button("Download leaderboard (CSV)", leaderboard_csv(results),
                                         file_name=f"{selected_run}-leaderboard.csv", mime="text/csv")

with vendor_tab:
    st.subheader("Vendor evaluation results")
    run_ids = get_run_ids()
    if not run_ids:
        st.info("Evaluate a batch to see evidence-grounded vendor scorecards.")
    else:
        selected_run = st.selectbox("Evaluation run", run_ids,
                                   index=run_ids.index(st.session_state["active_run_id"]) if st.session_state.get("active_run_id") in run_ids else 0,
                                   key="vendor_run")
        results = get_run_results(selected_run)
        vendors = [item["supplier_name"] for item in results]
        selected_vendor = st.selectbox("Supplier", vendors, key="selected_vendor")
        vendor = next(item for item in results if item["supplier_name"] == selected_vendor)
        st.markdown(f"**Run ID:** `{selected_run}` · **Rank:** {vendor['final_rank']} · **Evaluation mode:** {vendor['evaluation_mode']} · **Model:** {vendor.get('evaluation_model') or 'Unavailable'}")
        st.write(vendor.get("overall_summary") or "No executive summary returned.")
        coverage_col, absolute_col, ppi_col, ifi_col = st.columns(4)
        coverage_col.metric("Score coverage", f"{vendor['score_coverage']:.0f}%")
        absolute_col.metric("Absolute score", f"{vendor['absolute_score']:.1f} / 100")
        ppi_col.metric("PPI", f"{vendor['ppi']:.1f}")
        ifi_col.metric("Project-defined IFI", f"{vendor['ifi']:.1f}")
        st.markdown(f"**Tie-break order:** {vendor['tie_break_explanation']}")
        st.markdown(f"**Strengths:** {'; '.join(vendor.get('strengths', [])) or 'No scored strengths returned.'}")
        st.markdown(f"**Risks:** {'; '.join(vendor.get('risks', [])) or 'None stated.'}")
        st.markdown(f"**Missing information:** {'; '.join(vendor.get('missing_information', [])) or 'None stated.'}")
        st.dataframe(pd.DataFrame([{
            "Criterion": item["name"], "Score": f"{item['score']:g} / {item['max_score']:g}",
            "Weight (%)": item["weight"], "Weighted contribution": item["weighted_contribution"],
            "Benchmark": item["benchmark"], "Gap": item["gap"],
            "Relative (%)": item["relative_percent"], "Justification": item.get("justification", ""),
            "Evidence quote": item.get("evidence") or "No quote returned",
            "PDF page": item.get("page_number") or "Not provided",
            "Evidence status": item.get("evidence_status", "missing"),
        } for item in vendor["criteria"]]), hide_index=True, use_container_width=True)
        if vendor.get("warnings"):
            st.warning("Evaluation warnings")
            for warning in vendor["warnings"]:
                st.write(f"- {warning}")
        st.subheader("Side-by-side criterion comparison")
        comparison = [{"Criterion": criterion["name"], **{
            item["supplier_name"]: next((score["score"] for score in item["criteria"]
                                        if score["criterion_id"] == criterion["criterion_id"]), 0)
            for item in results
        }} for criterion in vendor["criteria"]]
        st.dataframe(pd.DataFrame(comparison), hide_index=True, use_container_width=True)

with criteria_tab:
    st.subheader("Criteria and weight management")
    all_criteria = get_criteria()
    active_sum = sum(float(item["weight"]) for item in all_criteria if item["is_active"])
    st.metric("Active weight total", f"{active_sum:g}%", "Valid" if abs(active_sum - 100) < 0.001 else "Must equal 100% before evaluation")
    for criterion in all_criteria:
        with st.expander(f"{criterion['name']} · {criterion['weight']:g}% · {'Active' if criterion['is_active'] else 'Inactive'}"):
            with st.form(f"criterion_{criterion['criterion_id']}"):
                name = st.text_input("Name", criterion["name"])
                description = st.text_area("Description", criterion["description"])
                scoring_guidance = st.text_area("Scoring guidance", criterion["scoring_guidance"])
                col_weight, col_max, col_industrial, col_active = st.columns(4)
                weight = col_weight.number_input("Weight (%)", 0.0, 100.0, float(criterion["weight"]), 1.0)
                max_score = col_max.number_input("Maximum score", 1.0, 100.0, float(criterion["max_score"]), 1.0)
                industrial_weight = col_industrial.number_input("Industrial relevance weight", 0.0, 100.0,
                                                                 float(criterion["industrial_relevance_weight"]), 1.0)
                is_active = col_active.checkbox("Active", bool(criterion["is_active"]))
                if st.form_submit_button("Save criterion"):
                    try:
                        save_criterion({"criterion_id": criterion["criterion_id"], "name": name.strip(),
                            "description": description, "scoring_guidance": scoring_guidance,
                            "weight": weight, "max_score": max_score,
                            "industrial_relevance_weight": industrial_weight, "is_active": is_active})
                        st.success("Criterion saved and audit logged. Existing runs are unchanged.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not save criterion: {error}")
    with st.expander("Create criterion"):
        with st.form("create_criterion"):
            name = st.text_input("New criterion name")
            description = st.text_area("Description", key="new_description")
            guidance = st.text_area("Scoring guidance", key="new_guidance")
            create_col1, create_col2, create_col3 = st.columns(3)
            weight = create_col1.number_input("Weight (%)", 0.0, 100.0, 0.0, 1.0, key="new_weight")
            maximum = create_col2.number_input("Maximum score", 1.0, 100.0, 10.0, 1.0, key="new_max")
            industrial = create_col3.number_input("Industrial relevance weight", 0.0, 100.0, 0.0, 1.0, key="new_industrial")
            active = st.checkbox("Activate criterion", True, key="new_active")
            if st.form_submit_button("Create criterion"):
                if not name.strip():
                    st.error("A criterion name is required.")
                else:
                    try:
                        save_criterion({"name": name.strip(), "description": description,
                            "scoring_guidance": guidance, "weight": weight, "max_score": maximum,
                            "industrial_relevance_weight": industrial, "is_active": active})
                        st.success("Criterion created and audit logged.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Could not create criterion: {error}")
    st.subheader("Criteria change audit log")
    audit = get_audit_log()
    if audit:
        st.dataframe(pd.DataFrame(audit), hide_index=True, use_container_width=True)
    else:
        st.caption("No criteria changes recorded yet.")