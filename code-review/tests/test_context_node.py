import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import context_node


class ContextNodeTests(unittest.TestCase):
    def test_extract_vue_script_blocks(self):
        lines = [
            "<template><div /></template>",
            "<script lang=\"ts\">",
            "export function setup() {",
            "  return 1;",
            "}",
            "</script>"
        ]

        blocks = context_node.extract_vue_script_blocks(lines)

        self.assertEqual(1, len(blocks))
        self.assertEqual("ts", blocks[0]["file_type"])
        self.assertEqual(3, blocks[0]["content_start"])
        self.assertEqual(5, blocks[0]["content_end"])

    def test_symbol_context_range_prefers_function_block(self):
        lines = [
            "export function foo(value: number) {",
            "  const next = value + 1;",
            "  return next;",
            "}",
            "const after = 1;"
        ]
        hunks = [{"new_start": 2, "new_count": 1, "old_start": 2, "old_count": 1}]

        ranges, strategy, events = context_node.build_symbol_context_ranges(lines, hunks, "M", "ts", 50)

        self.assertEqual([(1, 4)], ranges)
        self.assertIn(strategy, {"symbol-ast", "symbol-heuristic"})
        self.assertIn("strategy_chain", events)
        self.assertGreater(events.get("strategy_confidence", 0), 0)

    @patch("context_node.read_git_file")
    def test_overlong_symbol_falls_back_to_hunk(self, mock_read_git_file):
        mock_read_git_file.return_value = "\n".join([
            "export function oversized() {",
            *[f"  const value{i} = {i};" for i in range(1, 30)],
            "  return value1;",
            "}"
        ])

        context_data = context_node.build_file_context(
            repo_path="repo",
            target_branch="main",
            source_branch="feature",
            item={
                "path": "src/example.ts",
                "status": "M",
                "hunks": [{"new_start": 10, "new_count": 1, "old_start": 10, "old_count": 1}]
            },
            max_context_chars_per_file=8000,
            context_before=1,
            context_after=1,
            max_snippets_per_file=3,
            max_symbol_context_lines=5,
            warning_max_context_chars_per_file=None,
            context_ranges_hard_limit=3,
            context_ranges_soft_warning=None
        )

        self.assertEqual("hunk", context_data["context_strategy"])
        self.assertFalse(context_data["context_truncated"])
        self.assertIn("@@ lines 9-11 @@", context_data["snippet"])
        self.assertIn("strategy_chain", context_data)

    @patch("context_node.read_git_file")
    def test_range_hard_limit_records_omitted_ranges(self, mock_read_git_file):
        mock_read_git_file.return_value = "\n".join([f"line{i}" for i in range(1, 80)])

        context_data = context_node.build_file_context(
            repo_path="repo",
            target_branch="main",
            source_branch="feature",
            item={
                "path": "src/example.ts",
                "status": "M",
                "hunks": [
                    {"new_start": 10, "new_count": 1, "old_start": 10, "old_count": 1},
                    {"new_start": 30, "new_count": 1, "old_start": 30, "old_count": 1},
                    {"new_start": 50, "new_count": 1, "old_start": 50, "old_count": 1}
                ]
            },
            max_context_chars_per_file=8000,
            context_before=1,
            context_after=1,
            max_snippets_per_file=10,
            max_symbol_context_lines=1,
            warning_max_context_chars_per_file=None,
            context_ranges_hard_limit=1,
            context_ranges_soft_warning=1
        )

        self.assertTrue(context_data["context_truncated"])
        self.assertTrue(context_data["omitted_ranges"])
        self.assertIn("range-limit:hard-limit-applied", context_data["strategy_chain"])


if __name__ == "__main__":
    unittest.main()