from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import DATABASE_PATH

DEFAULT_CRITERIA = [
    ("Technical Capability", "Architecture, integrations, scalability, and technical fit.", 30, 10, 30, "Assess the proposed architecture, interoperability, scalability, and fit to the stated requirements."),
    ("Implementation Plan", "Timeline, milestones, staffing, and risk plan.", 20, 10, 20, "Assess delivery phases, milestones, resourcing, dependencies, and mitigation plans."),
    ("Commercial Value", "Pricing clarity, total cost, and assumptions.", 20, 10, 20, "Assess completeness, transparency, total cost, and commercial assumptions."),
    ("Security & Compliance", "Controls, certifications, privacy, and auditability.", 20, 10, 20, "Assess only evidenced security controls, certifications, privacy, and audit practices."),
    ("Support & Experience", "Support model, similar projects, and references.", 10, 10, 10, "Assess support coverage, relevant delivery experience, and verifiable references."),
]


def connect() -> sqlite3.Connection:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluation_criteria (
                criterion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                weight REAL NOT NULL CHECK(weight >= 0),
                max_score REAL NOT NULL CHECK(max_score > 0),
                industrial_relevance_weight REAL NOT NULL DEFAULT 0,
                scoring_guidance TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS rfp_runs (
                rfp_run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS criteria_snapshots (
                rfp_run_id TEXT PRIMARY KEY REFERENCES rfp_runs(rfp_run_id) ON DELETE CASCADE,
                snapshot_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS supplier_results (
                result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id) ON DELETE CASCADE,
                supplier_name TEXT NOT NULL,
                submission_date TEXT NOT NULL,
                experience_rating REAL NOT NULL,
                absolute_score REAL NOT NULL,
                ppi REAL NOT NULL,
                ifi REAL NOT NULL DEFAULT 0,
                final_rank INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                UNIQUE(rfp_run_id, supplier_name)
            );
            CREATE TABLE IF NOT EXISTS supplier_documents (
                document_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id) ON DELETE CASCADE,
                supplier_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                page_count INTEGER NOT NULL,
                extracted_text TEXT NOT NULL,
                file_bytes BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS criterion_scores (
                score_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id) ON DELETE CASCADE,
                supplier_name TEXT NOT NULL,
                criterion_id INTEGER NOT NULL,
                score REAL NOT NULL,
                score_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluation_warnings (
                warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id) ON DELETE CASCADE,
                supplier_name TEXT NOT NULL,
                warning TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS criteria_audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                criterion_id INTEGER,
                action TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_results_run_rank ON supplier_results(rfp_run_id, final_rank);
            CREATE INDEX IF NOT EXISTS idx_scores_run_vendor ON criterion_scores(rfp_run_id, supplier_name);
            CREATE INDEX IF NOT EXISTS idx_documents_run ON supplier_documents(rfp_run_id);
        """)
        for name, description, weight, maximum, industrial, guidance in DEFAULT_CRITERIA:
            connection.execute(
                """INSERT OR IGNORE INTO evaluation_criteria
                   (name, description, weight, max_score, industrial_relevance_weight, scoring_guidance)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, description, weight, maximum, industrial, guidance),
            )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES(1, ?)",
            (_now(),),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_criteria(active_only: bool = False) -> list[dict[str, Any]]:
    with connect() as connection:
        query = "SELECT * FROM evaluation_criteria"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY criterion_id"
        return [dict(row) for row in connection.execute(query).fetchall()]


def save_criterion(criterion: dict[str, Any]) -> None:
    with connect() as connection:
        criterion_id = criterion.get("criterion_id")
        before = None
        if criterion_id:
            row = connection.execute(
                "SELECT * FROM evaluation_criteria WHERE criterion_id = ?", (criterion_id,)
            ).fetchone()
            before = dict(row) if row else None
            connection.execute(
                """UPDATE evaluation_criteria SET name=?, description=?, weight=?, max_score=?,
                   industrial_relevance_weight=?, scoring_guidance=?, is_active=? WHERE criterion_id=?""",
                (criterion["name"], criterion["description"], criterion["weight"], criterion["max_score"],
                 criterion["industrial_relevance_weight"], criterion["scoring_guidance"],
                 int(criterion["is_active"]), criterion_id),
            )
            action = "update"
        else:
            cursor = connection.execute(
                """INSERT INTO evaluation_criteria
                   (name, description, weight, max_score, industrial_relevance_weight, scoring_guidance, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (criterion["name"], criterion["description"], criterion["weight"], criterion["max_score"],
                 criterion["industrial_relevance_weight"], criterion["scoring_guidance"],
                 int(criterion["is_active"])),
            )
            criterion_id = cursor.lastrowid
            action = "create"
        connection.execute(
            """INSERT INTO criteria_audit_log(criterion_id, action, changed_at, before_json, after_json)
               VALUES (?, ?, ?, ?, ?)""",
            (criterion_id, action, _now(), json.dumps(before), json.dumps(criterion)),
        )


def get_audit_log() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute("SELECT * FROM criteria_audit_log ORDER BY audit_id DESC").fetchall()
        return [dict(row) for row in rows]


def get_run_ids() -> list[str]:
    with connect() as connection:
        return [row[0] for row in connection.execute("SELECT rfp_run_id FROM rfp_runs ORDER BY created_at DESC")]


def get_run_results(run_id: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT result_json FROM supplier_results WHERE rfp_run_id=? ORDER BY final_rank", (run_id,)
        ).fetchall()
        return [json.loads(row[0]) for row in rows]


def persist_run(
    run_id: str,
    criteria: list[dict[str, Any]],
    results: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    status: str,
) -> None:
    with connect() as connection:
        connection.execute(
            "INSERT INTO rfp_runs(rfp_run_id, created_at, status) VALUES (?, ?, ?)",
            (run_id, _now(), status),
        )
        connection.execute(
            "INSERT INTO criteria_snapshots(rfp_run_id, snapshot_json) VALUES (?, ?)",
            (run_id, json.dumps(criteria)),
        )
        for document in documents:
            connection.execute(
                """INSERT INTO supplier_documents
                   (rfp_run_id, supplier_name, file_name, sha256, page_count, extracted_text, file_bytes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, document["supplier_name"], document["filename"], document["sha256"],
                 document["page_count"], document["text"], document["content"]),
            )
        for result in results:
            connection.execute(
                """INSERT INTO supplier_results
                   (rfp_run_id, supplier_name, submission_date, experience_rating, absolute_score, ppi, ifi, final_rank, result_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, result["supplier_name"], result["submission_date"], result["experience_rating"],
                 result["absolute_score"], result["ppi"], result["ifi"], result["final_rank"],
                 json.dumps(result)),
            )
            for item in result["criteria"]:
                connection.execute(
                    """INSERT INTO criterion_scores(rfp_run_id, supplier_name, criterion_id, score, score_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (run_id, result["supplier_name"], item["criterion_id"], item["score"], json.dumps(item)),
                )
            for warning in result.get("warnings", []):
                connection.execute(
                    "INSERT INTO evaluation_warnings(rfp_run_id, supplier_name, warning) VALUES (?, ?, ?)",
                    (run_id, result["supplier_name"], warning),
                )