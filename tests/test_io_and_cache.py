import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.utils.cache_manager import CacheManager
from src.utils.io import save_json, save_text


class IoAndCacheTests(unittest.TestCase):
    def test_save_json_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "data.json"
            self.assertTrue(save_json(str(target), {"ok": True}))
            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")), {"ok": True}
            )

    def test_save_text_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "note.txt"
            self.assertTrue(save_text(str(target), "hello"))
            self.assertEqual(target.read_text(encoding="utf-8"), "hello")

    def test_save_json_checks_target_directory_disk_space(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nested" / "data.json"
            checked_paths = []

            def fake_disk_usage(path):
                checked_paths.append(Path(path))
                return SimpleNamespace(free=1024 * 1024 * 1024)

            with patch("src.utils.io.shutil.disk_usage", fake_disk_usage):
                self.assertTrue(save_json(str(target), {"ok": True}))

            self.assertEqual(checked_paths, [target.parent])

    def test_save_json_fails_closed_when_disk_check_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "data.json"

            with patch(
                "src.utils.io.shutil.disk_usage", side_effect=OSError("stat failed")
            ):
                self.assertFalse(save_json(str(target), {"ok": True}))

            self.assertFalse(target.exists())

    def test_save_text_rejects_low_target_disk_space(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "note.txt"

            with patch(
                "src.utils.io.shutil.disk_usage", return_value=SimpleNamespace(free=1)
            ):
                self.assertFalse(save_text(str(target), "hello"))

            self.assertFalse(target.exists())

    def test_cache_manager_persists_summary_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = CacheManager(cache_dir=tmpdir)
            cache.set_summary_cache("paper", "content", "summary")
            self.assertEqual(cache.get_summary_cache("paper", "content"), "summary")


if __name__ == "__main__":
    unittest.main()
