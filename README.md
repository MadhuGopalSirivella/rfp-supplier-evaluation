# RFP Supplier Evaluation

A Streamlit application for evidence-grounded evaluation and comparison of multiple supplier proposal PDFs in one auditable run. The included five synthetic proposal PDFs can be uploaded together to compare all five vendors.

## Run with uv

Requirements: Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
Copy-Item .env.example .env
uv run python scripts\init_db.py
uv run streamlit run app.py
```

Run the tests with `uv run --group dev pytest`. `uv sync` creates and maintains the project `.venv` and `uv.lock`; activating the environment manually is not required. The equivalent launch command after syncing is `uv run streamlit run app.py`.

For live evaluation, enter your OpenAI API key in the Streamlit sidebar and select **Validate key and load models**. After validation, choose one of the chat models returned for that account. The key stays in Streamlit session memory and is not saved to `.env`, SQLite, or logs. Without a validated key, live evaluation is locked. To try the interface without an API key, set `RFP_MOCK_MODE=true` in `.env`, restart Streamlit, and note the persistent MOCK MODE warnings. Mock mode uses text matching and is not suitable for procurement decisions.

## Included sample proposals

Upload these five files from the repository root in one Evaluation batch:

- `Synthetic_Proposal_1_Apex_Systems.pdf`
- `Synthetic_Proposal_2_BrightPath_Tech.pdf`
- `Synthetic_Proposal_3_NexaWorks.pdf`
- `Synthetic_Proposal_4_Orbit_Digital.pdf`
- `Synthetic_Proposal_5_CedarPeak_Solutions.pdf`

The governing mini-project brief and supplier proposal template are also included at the repository root.

## Application structure

```text
app.py
config/settings.py
data/rfp_eval.sqlite3                 # created at first initialization
scripts/init_db.py
src/db.py
src/models.py
src/pdf_extractor.py
src/llm_evaluator.py
src/validation.py
src/scoring.py
src/orchestrator.py
src/exports.py
src/charts.py
tests/test_scoring.py
```

The four tabs cover batch Evaluation, Leaderboard and charts/exports, evidence-level Vendor Evaluation Results with side-by-side comparison, and criteria/weight management with audit history. All uploaded files in a run are compared as one cohort. Each PDF is stored with its extracted text and SHA-256, and the exact criteria snapshot is saved with the run.

## Scoring and ranking

- Absolute score: `sum((score / max_score) * criterion_weight)` on a 0-100 scale. Missing scores contribute zero and lower coverage.
- Criterion benchmark: highest normalized criterion score within that run.
- Gap: vendor normalized score minus the cohort benchmark.
- Relative performance: vendor normalized score divided by the benchmark, times 100. A zero benchmark has an explicit special case and is flagged.
- PPI: weighted sum of criterion relative-performance percentages. PPI is cohort-relative.
- IFI: project-defined weighted average of normalized scores using each criterion's industrial relevance weight. It is not an industry-standard measure.
- Tie-break sequence: higher PPI, earlier submission date, higher separately entered historical experience, then supplier name ascending.

Only the LLM judges proposal text. Python deterministically calculates scores, benchmarks, gaps, relative percentages, PPI, IFI, and rank. Active criteria weights must total exactly 100% before evaluation. Changes to criteria are audit logged and apply only to future runs.

## Reliability and review

PDF files must have a PDF signature and be within the configured size limit (25 MB by default). Duplicate file content, duplicate supplier names, invalid dates, and experience values outside 0-10 are rejected before evaluation. PDF text is extracted page-by-page with PyMuPDF. Evidence quotes are whitespace-normalized and checked against extracted text; unverified quotes are labeled and warned. Model failures and missing/malformed criterion scores do not remove a vendor: the proposal remains in the run with explicit warnings and conservative zero scores. Results with low score coverage call for human review.

LLM outputs are validated with Pydantic structured output, evaluated independently per proposal, and retried once on a failed live call. Proposal text is treated as untrusted input. API secrets are read from environment variables and are never stored in SQLite. Commercial comparisons are shown only when every supplier has a total cost in the same currency. Always review source PDFs and warnings before making procurement decisions.

## Tests

```powershell
uv run --group dev pytest
```