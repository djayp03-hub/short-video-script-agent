"""Weighted rubric for explicitly attributed reviews; missing grades stay unscored."""
import argparse
import json
from pathlib import Path

WEIGHTS = {"facts": 30, "decisions": 25, "status": 20, "constraints": 15, "usability": 10}


def score(review):
    grades = review.get("grades", {})
    missing = [k for k in WEIGHTS if grades.get(k) is None]
    for k, value in grades.items():
        if k not in WEIGHTS or (value is not None and (type(value) is not int or not 0 <= value <= 4)):
            raise ValueError("grades must use the five rubric keys and integers 0..4 or null")
    if not review.get("reviewer") or not review.get("reviewer_type"):
        raise ValueError("reviewer attribution required")
    if not missing and not review.get("evidence_notes"):
        raise ValueError("completed scores require evidence notes")
    if review.get("critical_defects"):
        return {"case": review["case"], "status": "failed_critical", "score": None,
                "critical_defects": review["critical_defects"]}
    if missing:
        return {"case": review["case"], "status": "unverified", "score": None, "missing": missing}
    return {"case": review["case"], "status": "scored",
            "score": sum(WEIGHTS[k] * grades[k] / 4 for k in WEIGHTS),
            "reviewer": review["reviewer"], "reviewer_type": review["reviewer_type"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reviews", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = [score(r) for r in json.loads(args.reviews.read_text(encoding="utf-8"))]
    # Never average only the successes and hide critical/unverified cases.
    mean = sum(r["score"] for r in results) / len(results) if results and all(r["status"] == "scored" for r in results) else None
    report = {"weights": WEIGHTS, "official_rubric": False, "mean_score": mean, "results": results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
