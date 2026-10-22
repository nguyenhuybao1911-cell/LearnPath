import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.download_data import download_file, files_for


class Response:
    status = 206
    headers = {"Content-Range": "bytes 3-5/6"}

    def __init__(self):
        self.data = [b"def", b""]

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return self.data.pop(0)


class DownloadTests(unittest.TestCase):
    def test_interaction_history_is_opt_in_because_it_is_21_gb(self):
        self.assertNotIn("relations/user-problem.json", files_for("cs", False))
        self.assertIn("relations/user-problem.json", files_for("cs", True))
        self.assertIn("prerequisites/cs.json", files_for("cs", False))

    def test_resumes_partial_file_and_atomically_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "relations" / "user-problem.json"
            target.parent.mkdir(parents=True)
            target.with_suffix(".json.part").write_bytes(b"abc")
            with patch("scripts.download_data.urllib.request.urlopen", return_value=Response()):
                download_file("relations/user-problem.json", Path(directory), "https://example.invalid")
            self.assertEqual(target.read_bytes(), b"abcdef")
            self.assertFalse(target.with_suffix(".json.part").exists())


if __name__ == "__main__":
    unittest.main()
