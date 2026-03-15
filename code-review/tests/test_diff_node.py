import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import diff_node


class DiffNodeTests(unittest.TestCase):
    def test_parse_hunks(self):
        diff_text = "@@ -10,2 +20,3 @@\n-old\n+new\n@@ -30 +40 @@\n"
        hunks = diff_node.parse_hunks(diff_text)

        self.assertEqual(2, len(hunks))
        self.assertEqual(10, hunks[0]["old_start"])
        self.assertEqual(3, hunks[0]["new_count"])
        self.assertEqual(30, hunks[1]["old_start"])
        self.assertEqual(1, hunks[1]["old_count"])

    def test_parse_name_status_handles_rename(self):
        output = "R100\tsrc/old.ts\tsrc/new.ts\nM\tsrc/app.ts\n"
        files = diff_node.parse_name_status(output, ["src/"], [])

        self.assertEqual(2, len(files))
        self.assertEqual("src/new.ts", files[0]["path"])
        self.assertEqual("src/old.ts", files[0]["old_path"])

    def test_parse_hunks_with_stats_detects_invalid_counts(self):
        diff_text = "@@ -10,2 +20,2 @@\n-old\n+new\n"
        _, anomalies = diff_node.parse_hunks_with_stats(diff_text, strict_validation=True)
        self.assertTrue(anomalies)
        self.assertIn("invalid_hunk_counts", anomalies[0])

    def test_determine_file_strategy_for_rename(self):
        strategy, hunks_truncated, omitted_hunks = diff_node.determine_file_strategy(
            {"status": "R100"},
            "@@ -1 +1 @@\n-old\n+new\n",
            max_hunks_per_file=1
        )
        self.assertEqual("rename-local-first", strategy)
        self.assertFalse(hunks_truncated)
        self.assertEqual(0, omitted_hunks)


if __name__ == "__main__":
    unittest.main()