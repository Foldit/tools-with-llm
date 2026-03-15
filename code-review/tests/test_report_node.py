import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import report_node


class ReportNodeTests(unittest.TestCase):
    def test_report_includes_context_strategy_and_transparency(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = str(Path(temp_dir) / "report.md")
            result = report_node.main({
                "task": {
                    "repo_path": "repo",
                    "target_branch": "main",
                    "source_branch": "feature",
                    "devops_url": "",
                    "output_path": output_path
                },
                "requirement_summary": {"title": "t", "main_source": "manual", "summary": "s"},
                "diff_result": {
                    "change_summary": ["changed_files_count=1"],
                    "commit_list": ["abc test"],
                    "warnings": ["warn"],
                    "skipped_files": ["src/skip.ts"]
                },
                "context_bundle": {
                    "files": [
                        {
                            "file": "src/app.ts",
                            "context_strategy": "symbol-ast",
                            "strategy_confidence": 0.95,
                            "strategy_chain": ["symbol-ast:selected"],
                            "fallback_reason": None,
                            "omitted_ranges": [[20, 25]],
                            "hunk_count": 1,
                            "context_truncated": False
                        }
                    ],
                    "summary": {
                        "fallback_reason_counts": {"symbol_too_large": 1},
                        "skipped_files": [{"file": "src/missing.ts", "reason": "missing"}],
                        "truncated_files": ["src/app.ts"],
                        "warnings": ["context warn"]
                    }
                },
                "review_result": {
                    "overall_decision": "approved_with_suggestions",
                    "summary": "done",
                    "warnings": ["review warning"],
                    "findings": [
                        {
                            "title": "manual check",
                            "file": "src/app.ts",
                            "needs_manual_confirmation": True
                        }
                    ],
                    "coverage_assessment": {}
                }
            })

            markdown = Path(result["report_path"]).read_text(encoding="utf-8")
            self.assertIn("strategy=symbol-ast", markdown)
            self.assertIn("strategy_chain", markdown)
            self.assertIn("omitted_ranges=20-25", markdown)
            self.assertIn("Manual Confirmation Required", markdown)
            self.assertIn("Review Warnings", markdown)
            self.assertIn("src/skip.ts", markdown)


if __name__ == "__main__":
    unittest.main()