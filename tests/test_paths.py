import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import paths


class UserDataDirTests(unittest.TestCase):
    # No test_windows_uses_appdata here: since Python 3.12, pathlib refuses to
    # instantiate a WindowsPath on a non-Windows OS regardless of os.name
    # patching ("cannot instantiate 'WindowsPath' on your system"), so the
    # `os.name == "nt"` branch can't be exercised from this Linux dev
    # machine. It's covered instead by the Windows CI job actually running
    # the packaged app on windows-latest.

    def test_linux_uses_xdg_config_home_when_set(self):
        with TemporaryDirectory() as temp_dir:
            xdg = Path(temp_dir) / "xdg"
            with patch("os.name", "posix"), patch.dict(
                os.environ, {"XDG_CONFIG_HOME": str(xdg)}, clear=False
            ):
                os.environ.pop("NOA_DATA_DIR", None)
                result = paths.user_data_dir()

            self.assertEqual(result, xdg / paths.APP_SLUG)
            self.assertTrue(result.exists())

    def test_linux_falls_back_to_home_config_without_xdg(self):
        with TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            home.mkdir()
            with patch("os.name", "posix"), patch.dict(os.environ, {}, clear=False), patch(
                "pathlib.Path.home", return_value=home
            ):
                os.environ.pop("XDG_CONFIG_HOME", None)
                os.environ.pop("NOA_DATA_DIR", None)
                result = paths.user_data_dir()

            self.assertEqual(result, home / ".config" / paths.APP_SLUG)

    def test_noa_data_dir_override_takes_precedence(self):
        with TemporaryDirectory() as temp_dir:
            override = Path(temp_dir) / "custom"
            with patch.dict(os.environ, {"NOA_DATA_DIR": str(override)}, clear=False):
                result = paths.user_data_dir()

            self.assertEqual(result, override)
            self.assertTrue(result.exists())


class MigrateLegacyFileTests(unittest.TestCase):
    def test_copies_legacy_file_when_target_missing(self):
        with TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir) / "custom"
            legacy = Path(paths.__file__).resolve().parents[1] / "legacy_test_artifact.tmp"
            legacy.write_text("legacy-contents", encoding="utf-8")
            try:
                with patch.dict(os.environ, {"NOA_DATA_DIR": str(target_dir)}, clear=False):
                    paths.migrate_legacy_file("legacy_test_artifact.tmp")

                self.assertEqual(
                    (target_dir / "legacy_test_artifact.tmp").read_text(encoding="utf-8"),
                    "legacy-contents",
                )
            finally:
                legacy.unlink()

    def test_does_not_overwrite_existing_target(self):
        with TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir) / "custom"
            target_dir.mkdir()
            (target_dir / "legacy_test_artifact.tmp").write_text("current", encoding="utf-8")
            legacy = Path(paths.__file__).resolve().parents[1] / "legacy_test_artifact.tmp"
            legacy.write_text("legacy-contents", encoding="utf-8")
            try:
                with patch.dict(os.environ, {"NOA_DATA_DIR": str(target_dir)}, clear=False):
                    paths.migrate_legacy_file("legacy_test_artifact.tmp")

                self.assertEqual(
                    (target_dir / "legacy_test_artifact.tmp").read_text(encoding="utf-8"),
                    "current",
                )
            finally:
                legacy.unlink()


if __name__ == "__main__":
    unittest.main()
