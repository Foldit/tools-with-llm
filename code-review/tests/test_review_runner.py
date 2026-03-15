import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import review_runner  # type: ignore[import-not-found]


class ReviewRunnerTests(unittest.TestCase):
    def test_prepare_prompt_with_budget_truncates_when_enabled(self):
        config = {
            "llm": {"model": "gpt-4o-mini", "max_tokens": 80},
            "other": {"cal_token": False, "token_overflow_strategy": "truncate_retry"}
        }
        system_prompt = "system"
        user_prompt = "word " * 500

        new_prompt, warnings = review_runner.prepare_prompt_with_budget(
            config,
            "review_step",
            system_prompt,
            user_prompt
        )

        self.assertIn("TRUNCATED_FOR_TOKEN_BUDGET", new_prompt)
        self.assertTrue(warnings)

    def test_normalize_review_result_drops_findings_without_evidence(self):
        raw = {
            "summary": "s",
            "overall_decision": "approved_with_suggestions",
            "findings": [
                {
                    "title": "missing evidence",
                    "severity": "high"
                },
                {
                    "title": "ok",
                    "severity": "high",
                    "evidence": {
                        "file": "src/app.ts",
                        "line": 10,
                        "snippet": "dangerous_call()"
                    }
                }
            ]
        }

        normalized, warnings = review_runner.normalize_review_result(raw)

        self.assertEqual(1, len(normalized["findings"]))
        self.assertEqual("ok", normalized["findings"][0]["title"])
        self.assertTrue(any("missing required evidence" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
