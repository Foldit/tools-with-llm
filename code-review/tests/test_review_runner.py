import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch


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

    def test_summarize_requirement_images_uses_filename_for_local_path(self):
        images = [{"source": "D:/repo/assets/ui/home.png", "note": "首页", "detail": "high"}]
        summary = review_runner.summarize_requirement_images(images)

        self.assertEqual("home.png", summary[0]["source"])
        self.assertEqual("首页", summary[0]["note"])

    @patch("review_runner.build_image_data_url", return_value="data:image/png;base64,AAA")
    def test_build_requirement_user_content_returns_multimodal_blocks(self, _data_url):
        blocks = review_runner.build_requirement_user_content(
            "text prompt",
            [{"source": "D:/repo/assets/ui/home.png", "note": "按钮样式", "detail": "high"}]
        )

        self.assertIsInstance(blocks, list)
        self.assertEqual("text", blocks[0]["type"])
        self.assertEqual("image_url", blocks[2]["type"])
        self.assertEqual("high", blocks[2]["image_url"]["detail"])

    def test_validate_requirement_images_limits_rejects_too_many_images(self):
        config = {
            "review": {
                "max_requirement_images": 1,
                "max_image_bytes": 1024,
                "requirement_image_overflow_strategy": "error"
            }
        }
        images = [
            {"source": "https://example.com/a.png"},
            {"source": "https://example.com/b.png"}
        ]

        with self.assertRaises(ValueError):
            review_runner.validate_requirement_images_limits(images, config)

    def test_validate_requirement_images_limits_rejects_large_local_image(self):
        config = {
            "review": {
                "max_requirement_images": 5,
                "max_image_bytes": 4,
                "requirement_image_overflow_strategy": "error"
            }
        }
        with tempfile.NamedTemporaryFile(delete=False) as temp_image:
            temp_image.write(b"0123456789")
            temp_path = temp_image.name

        try:
            with self.assertRaises(ValueError):
                review_runner.validate_requirement_images_limits(
                    [{"source": temp_path}],
                    config
                )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_validate_requirement_images_limits_warns_remote_url_unchecked(self):
        config = {
            "review": {
                "max_requirement_images": 5,
                "max_image_bytes": 1024,
                "requirement_image_overflow_strategy": "error"
            }
        }

        kept_images, warnings = review_runner.validate_requirement_images_limits(
            [{"source": "https://example.com/a.png"}],
            config
        )

        self.assertEqual(1, len(kept_images))
        self.assertTrue(any("size unchecked" in item for item in warnings))

    def test_validate_requirement_images_limits_drops_tail_when_count_overflow(self):
        config = {
            "review": {
                "max_requirement_images": 1,
                "max_image_bytes": 1024,
                "requirement_image_overflow_strategy": "drop_with_warning"
            }
        }

        kept_images, warnings = review_runner.validate_requirement_images_limits(
            [
                {"source": "https://example.com/a.png"},
                {"source": "https://example.com/b.png"}
            ],
            config
        )

        self.assertEqual(1, len(kept_images))
        self.assertEqual("https://example.com/a.png", kept_images[0]["source"])
        self.assertTrue(any("dropped tail images" in item for item in warnings))

    def test_validate_requirement_images_limits_drops_large_local_image_with_warning(self):
        config = {
            "review": {
                "max_requirement_images": 5,
                "max_image_bytes": 4,
                "requirement_image_overflow_strategy": "drop_with_warning"
            }
        }
        with tempfile.NamedTemporaryFile(delete=False) as temp_image:
            temp_image.write(b"0123456789")
            temp_path = temp_image.name

        try:
            kept_images, warnings = review_runner.validate_requirement_images_limits(
                [{"source": temp_path}],
                config
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

        self.assertEqual([], kept_images)
        self.assertTrue(any("dropped due to size overflow" in item for item in warnings))

    def test_validate_requirement_images_limits_drop_count_only_drops_on_count(self):
        config = {
            "review": {
                "max_requirement_images": 1,
                "max_image_bytes": 1024,
                "requirement_image_overflow_strategy": "drop_count_only_with_warning"
            }
        }

        kept_images, warnings = review_runner.validate_requirement_images_limits(
            [
                {"source": "https://example.com/a.png"},
                {"source": "https://example.com/b.png"}
            ],
            config
        )

        self.assertEqual(1, len(kept_images))
        self.assertEqual("https://example.com/a.png", kept_images[0]["source"])
        self.assertTrue(any("dropped tail images" in item for item in warnings))

    def test_validate_requirement_images_limits_drop_count_only_still_errors_on_size(self):
        config = {
            "review": {
                "max_requirement_images": 5,
                "max_image_bytes": 4,
                "requirement_image_overflow_strategy": "drop_count_only_with_warning"
            }
        }
        with tempfile.NamedTemporaryFile(delete=False) as temp_image:
            temp_image.write(b"0123456789")
            temp_path = temp_image.name

        try:
            with self.assertRaises(ValueError):
                review_runner.validate_requirement_images_limits(
                    [{"source": temp_path}],
                    config
                )
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
