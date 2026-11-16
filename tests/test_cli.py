import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nfl_predictor.cli import main, save_new


class CliTests(unittest.TestCase):
    def test_default_check_skips_completed_games_but_checks_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"games": [{"event_id": "done", "state": "post"},
                                                  {"event_id": "next", "state": "pre"}]}))
            with patch("sys.argv", ["nfl-predictor", "check", "--manifest", str(path)]), \
                 patch("nfl_predictor.cli.check_pregame", return_value={"ready": True}) as check, \
                 contextlib.redirect_stdout(io.StringIO()):
                main()
            self.assertEqual(check.call_count, 1)
            self.assertEqual(check.call_args.args[0]["event_id"], "next")

    def test_existing_score_file_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            save_new(path, {"original": 1})
            with self.assertRaises(FileExistsError):
                save_new(path, {"original": 2})
            self.assertEqual(json.loads(path.read_text()), {"original": 1})
