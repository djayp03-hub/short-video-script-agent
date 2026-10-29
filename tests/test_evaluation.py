import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from video_agent.cli import execute_run, read, write


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


score = module("score_reviews").score
verify = module("verify_artifacts").verify


class Evaluation(unittest.TestCase):
    def test_audit_detects_sources_removed_from_search_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case"
            execute_run(read(ROOT / "data/request.json"), read(ROOT / "data/materials.json"),
                        read(ROOT / "data/brand_rules.json"), path)
            trace = [__import__('json').loads(l) for l in (path / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
            for row in trace:
                if row.get("decision", {}).get("action") == "search_materials":
                    row["observation"]["data"]["materials"] = []
            (path / "trace.jsonl").write_text(''.join(__import__('json').dumps(r, ensure_ascii=False)+'\n' for r in trace),encoding='utf-8')
            self.assertIn("sources_not_in_search_observations", verify(path))

    def test_missing_grade_never_becomes_total(self):
        r = {"case": "test", "reviewer": "tester", "reviewer_type": "test", "grades": {"facts": 4}}
        self.assertIsNone(score(r)["score"])

    def test_critical_failure_cannot_be_offset_by_other_points(self):
        r = {"case": "test", "reviewer": "tester", "reviewer_type": "test",
             "grades": dict.fromkeys(["facts", "decisions", "status", "constraints", "usability"], 4),
             "critical_defects": ["invented_product_fact"], "evidence_notes": "test"}
        self.assertEqual(score(r)["status"], "failed_critical")
        self.assertIsNone(score(r)["score"])

    def test_weighted_score(self):
        r = {"case": "test", "reviewer": "tester", "reviewer_type": "test",
             "grades": dict.fromkeys(["facts", "decisions", "status", "constraints", "usability"], 3),
             "evidence_notes": "test only"}
        self.assertEqual(score(r)["score"], 75)

    def test_grade_requires_attribution_and_range(self):
        with self.assertRaises(ValueError):
            score({"case": "test"})
        with self.assertRaises(ValueError):
            score({"case": "test", "grades": {"facts": 5}})

    def test_audit_detects_tampered_duration_and_citation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case"
            execute_run(read(ROOT / "data/request.json"), read(ROOT / "data/materials.json"),
                        read(ROOT / "data/brand_rules.json"), path)
            self.assertEqual(verify(path), [])
            out = read(path / "output.json")
            out["estimated_total_seconds"] = 0
            out["draft"]["scenes"][0]["source_ids"] = ["forged"]
            write(path / "output.json", out)
            errors = verify(path)
            self.assertIn("duration_recalculation_failed", errors)
            self.assertIn("unretrieved_citation", errors)


if __name__ == "__main__":
    unittest.main()
