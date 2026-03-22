import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import input_node


class InputNodeTests(unittest.TestCase):
    @patch("input_node.branch_exists", return_value=True)
    @patch("input_node.is_git_repo", return_value=True)
    @patch("input_node.os.path.exists", return_value=True)
    def test_main_preserves_config_overrides(self, _exists, _repo, _branch):
        result = input_node.main({
            "repo_path": "./repo",
            "target_branch": "main",
            "source_branch": "feature",
            "manual_requirement": "req",
            "config_overrides": {"review": {"max_files": 5}}
        })

        self.assertEqual(5, result["task"]["config_overrides"]["review"]["max_files"])
        self.assertEqual([], result["task"]["requirement_images"])

    def test_main_requires_manual_requirement(self):
        with self.assertRaises(ValueError):
            input_node.main({
                "repo_path": "./repo",
                "target_branch": "main",
                "source_branch": "feature",
                "manual_requirement": ""
            })

    @patch("input_node.branch_exists", return_value=True)
    @patch("input_node.is_git_repo", return_value=True)
    @patch("input_node.os.path.exists", return_value=True)
    def test_main_accepts_requirement_image_urls(self, _exists, _repo, _branch):
        result = input_node.main({
            "repo_path": "./repo",
            "target_branch": "main",
            "source_branch": "feature",
            "manual_requirement": "req",
            "requirement_images": [
                "https://example.com/ui.png",
                {"url": "https://example.com/flow.jpg", "note": "交互流程"}
            ]
        })

        self.assertEqual(2, len(result["task"]["requirement_images"]))
        self.assertEqual("https://example.com/ui.png", result["task"]["requirement_images"][0]["source"])
        self.assertEqual("交互流程", result["task"]["requirement_images"][1]["note"])

    @patch("input_node.branch_exists", return_value=True)
    @patch("input_node.is_git_repo", return_value=True)
    @patch("input_node.os.path.exists", return_value=True)
    def test_main_rejects_non_array_requirement_images(self, _exists, _repo, _branch):
        with self.assertRaises(ValueError):
            input_node.main({
                "repo_path": "./repo",
                "target_branch": "main",
                "source_branch": "feature",
                "manual_requirement": "req",
                "requirement_images": "https://example.com/ui.png"
            })


if __name__ == "__main__":
    unittest.main()