import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import llm_client


class LLMClientTests(unittest.TestCase):
    @patch("llm_client.requests.post")
    def test_chat_json_parses_fenced_json(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "```json\n{\"ok\": true}\n```"}}]
        }
        mock_post.return_value = response

        client = llm_client.LLMClient("http://example.com", "token", "model")
        result = client.chat_json("system", "user")

        self.assertEqual({"ok": True}, result)

    @patch("llm_client.time.sleep")
    @patch("llm_client.requests.post")
    def test_chat_json_retries_request_errors(self, mock_post, _sleep):
        good_response = Mock()
        good_response.raise_for_status.return_value = None
        good_response.json.return_value = {
            "choices": [{"message": {"content": "{\"ok\": true}"}}]
        }
        mock_post.side_effect = [requests.RequestException("boom"), good_response]

        client = llm_client.LLMClient("http://example.com", "token", "model", max_retries=1)
        result = client.chat_json("system", "user")

        self.assertEqual({"ok": True}, result)
        self.assertEqual(2, mock_post.call_count)


if __name__ == "__main__":
    unittest.main()