from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import main


class MainCliMetaTests(unittest.TestCase):
    def test_cmd_test_meta_prints_missing_credentials(self) -> None:
        with patch.object(
            main,
            "CONFIG",
            SimpleNamespace(has_facebook=lambda: False, has_instagram=lambda: False),
        ):
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main.cmd_test_meta(None)

        out = stream.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Meta credentials missing or incomplete", out)
        self.assertIn('"facebook_configured": false', out)
        self.assertIn('"instagram_configured": false', out)

    def test_cmd_test_meta_runs_readonly_checks_when_configured(self) -> None:
        with patch.object(
            main,
            "CONFIG",
            SimpleNamespace(has_facebook=lambda: True, has_instagram=lambda: True),
        ), patch(
            "connectors.facebook_page_api.fetch_recent_page_posts",
            return_value={"success": True, "error": ""},
        ), patch(
            "connectors.instagram_graph_api.fetch_recent_media",
            return_value={"success": True, "error": ""},
        ):
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main.cmd_test_meta(None)

        out = stream.getvalue()
        self.assertEqual(code, 0)
        self.assertIn('"facebook_check_success": true', out)
        self.assertIn('"instagram_check_success": true', out)

    def test_cmd_check_comments_runs_replies_only_workflow(self) -> None:
        workflow_result = {
            "mode": "DRY_RUN",
            "paused": False,
            "posts": [],
            "replies": [{"status": "draft"}],
            "external_comments": [],
            "issues": [],
        }
        with patch(
            "agents.ceo_controller.run_check_comments_only",
            return_value=workflow_result,
        ), patch(
            "agents.report_writer.build_report_text",
            return_value="reply report",
        ), patch(
            "connectors.telegram_bot.send_message",
        ) as mocked_send:
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main.cmd_check_comments(None)

        out = stream.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("reply report", out)
        mocked_send.assert_called_once_with("reply report")


if __name__ == "__main__":
    unittest.main()
