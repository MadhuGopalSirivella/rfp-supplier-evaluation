from __future__ import annotations

from datetime import date
from hashlib import sha256
from typing import Any

from config.settings import MAX_PDF_SIZE_BYTES


def validate_uploads(proposals: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    hashes: set[str] = set()
    names: set[str] = set()
    for index, proposal in enumerate(proposals, start=1):
        label = proposal.get("filename") or f"Proposal {index}"
        content = proposal.get("content", b"")
        supplier_name = str(proposal.get("supplier_name", "")).strip()
        submission_date = str(proposal.get("submission_date", "")).strip()
        experience = proposal.get("experience_rating")
        if not content.startswith(b"%PDF-"):
            errors.append(f"{label}: file does not have a valid PDF signature.")
        if len(content) > MAX_PDF_SIZE_BYTES:
            errors.append(f"{label}: exceeds the {MAX_PDF_SIZE_BYTES // (1024 * 1024)} MB limit.")
        digest = sha256(content).hexdigest()
        if digest in hashes:
            errors.append(f"{label}: duplicate PDF content detected.")
        hashes.add(digest)
        normalized_name = supplier_name.casefold()
        if not supplier_name:
            errors.append(f"{label}: supplier name is required.")
        elif normalized_name in names:
            errors.append(f"{label}: supplier name '{supplier_name}' is duplicated.")
        names.add(normalized_name)
        try:
            date.fromisoformat(submission_date)
        except ValueError:
            errors.append(f"{label}: a valid submission date is required.")
        try:
            if experience is None or not 0 <= float(experience) <= 10:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{label}: experience rating must be between 0 and 10.")
    return errors