import csv
import io
import json
from typing import Any


def results_json(results: list[dict[str, Any]]) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False)


def leaderboard_csv(results: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    fields = ["final_rank", "supplier_name", "absolute_score", "ppi", "ifi",
              "submission_date", "experience_rating", "score_coverage"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows({field: result.get(field) for field in fields} for result in results)
    return output.getvalue()