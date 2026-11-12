import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "publish_release.py"
spec = importlib.util.spec_from_file_location("publish_release", MODULE_PATH)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

sys.path.insert(0, str(MODULE_PATH.parent / "build"))
import stage_mods
sys.path.pop(0)


class ManifestMetadataTests(unittest.TestCase):
    def test_staging_uses_existing_feature_copy_for_summary(self):
        for features in (["Коротке призначення."], []):
            with self.subTest(features=features), tempfile.TemporaryDirectory() as directory:
                mod = {
                    "id": "fixture", "folder": "fixture", "title": "Fixture", "version": "1.0",
                    "files": [], "description": "Повний опис.", "readme_features": features,
                }
                previous = Path.cwd()
                try:
                    os.chdir(directory)
                    with patch.object(stage_mods.mods_registry, "find_repo", return_value=directory), patch.object(stage_mods.mods_registry, "load_mods", return_value=[mod]), contextlib.redirect_stdout(io.StringIO()):
                        stage_mods.main()
                    info = json.loads(Path("staging_modpack/Mods/fixture/info.json").read_text(encoding="utf-8"))
                finally:
                    os.chdir(previous)
                self.assertEqual(features[0] if features else mod["description"], info["summary"])
                self.assertEqual(mod["description"], info["description"])

    def test_local_and_release_preserve_separate_mod_metadata(self):
        for local in (True, False):
            for with_changes in (True, False):
                with self.subTest(local=local, with_changes=with_changes):
                    self.check_manifest(local, with_changes)

    def check_manifest(self, local, with_changes):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / "staging_modpack" / "Launcher" / "WotModLauncher.exe"
            launcher.parent.mkdir(parents=True)
            launcher.write_bytes(b"launcher fixture")
            mod = root / "staging_modpack" / "Mods" / "fixture"
            packages = mod / "game_files" / "mods" / "_VERSION_"
            packages.mkdir(parents=True)
            bundled = packages / "fixture.bundled_1.0.wotmod"
            remote = root / "fixture.remote_1.0.wotmod"
            for path, mod_id in ((bundled, "fixture.bundled"), (remote, "fixture.remote")):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("meta.xml", f"<root><id>{mod_id}</id><version>1.0</version></root>")
            info = {
                "title": "Тестовий мод",
                "author": "Niedvin",
                "summary": "Коротке призначення мода.",
                "description": "Опис призначення, який не є описом змін.",
                "remote_files": [{"source": str(remote), "file": remote.name, "path": "game_files/mods/_VERSION_/" + remote.name}],
            }
            if with_changes:
                info["changes"] = "Виправлено конкретну помилку."
            (mod / "info.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(publisher, "read_launcher_version", return_value="1.4.4.0"), contextlib.redirect_stdout(io.StringIO()):
                    if local:
                        publisher.local_test("2.4.1.1", False, str(root / "local"))
                        output = root / "local"
                    else:
                        with patch.object(publisher, "detect_game_version", return_value="2.4.1.1"), patch("sys.argv", ["publish_release.py"]):
                            publisher.main()
                        output = root / "build" / "release_assets"
                manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            finally:
                os.chdir(previous)
            self.assertEqual(2, len(manifest["mods"]))
            self.assertEqual("1.4.4.0", manifest["launcher"]["version"])
            for entry in manifest["mods"]:
                self.assertEqual(info["description"], entry["description"])
                self.assertEqual(info["author"], entry["author"])
                self.assertEqual(info["summary"], entry["summary"])
                self.assertEqual(info.get("changes", ""), entry["changes"])
                self.assertNotEqual(entry["description"], entry["changes"])
                self.assertEqual(64, len(entry["sha256"]))
                self.assertEqual(publisher.sha256_file(output / entry["file"]), entry["sha256"])


if __name__ == "__main__":
    unittest.main()
