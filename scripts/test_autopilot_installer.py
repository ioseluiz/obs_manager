"""Tests de core/autopilot_installer.py (actualizacion automatica del Lua).

Sin OBS ni Qt. Usa una carpeta temporal como config de OBS.

Uso: venv\\Scripts\\python.exe scripts\\test_autopilot_installer.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import autopilot_installer as ai
from core.autopilot_paths import autopilot_v2_lua_path
from core.source_record_installer import LocalObs


def lua(version: str) -> str:
    return f'-- fake\nlocal obs = obslua\nlocal SCRIPT_VERSION = "{version}"\nlocal PROTOCOL_VERSION = 2\n'


class AutopilotInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aptest_"))
        self.cfg = self.tmp / "config" / "obs-studio"
        (self.cfg / "basic" / "scenes").mkdir(parents=True)

    def write_collection(self, name, paths):
        data = {"name": name, "modules": {"scripts-tool": [{"path": p, "settings": {}} for p in paths],
                                          "output-timer": {}}}
        (self.cfg / "basic" / "scenes" / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    def test_bundled_version_is_read_from_real_script(self):
        self.assertTrue(autopilot_v2_lua_path().is_file())
        v = ai.bundled_script_version()
        self.assertIsNotNone(v)
        self.assertIsNotNone(ai.parse_version(v))
        self.assertGreaterEqual(ai.parse_version(v), (2, 1, 0))

    def test_read_script_version_and_is_newer(self):
        p = self.tmp / "s.lua"; p.write_text(lua("2.0.0"))
        self.assertEqual(ai.read_script_version(p), "2.0.0")
        self.assertIsNone(ai.read_script_version(self.tmp / "nope.lua"))
        self.assertTrue(ai.is_newer("2.1.0", "2.0.0"))
        self.assertFalse(ai.is_newer("2.1.0", "2.1.0"))
        self.assertTrue(ai.is_newer("2.1.0", None))
        self.assertFalse(ai.is_newer(None, "2.0.0"))

    def test_obs_config_dir_portable_vs_installed(self):
        portable = LocalObs(exe=self.tmp / "bin/64bit/obs64.exe", root=self.tmp, portable=True, version=(32, 1, 2))
        self.assertEqual(ai.obs_config_dir(portable), self.tmp / "config" / "obs-studio")
        installed = LocalObs(exe=Path("C:/Program Files/obs-studio/bin/64bit/obs64.exe"),
                             root=Path("C:/Program Files/obs-studio"), portable=False, version=(33, 0, 0))
        with patch.dict("os.environ", {"APPDATA": str(self.tmp / "Roaming")}):
            self.assertEqual(ai.obs_config_dir(installed), self.tmp / "Roaming" / "obs-studio")

    def test_find_registered_scripts(self):
        old = self.tmp / "scripts" / "autopilot_v2.lua"; old.parent.mkdir(); old.write_text(lua("2.0.0"))
        self.write_collection("Untitled", [str(old).replace("\\", "/"),
                                           "C:/otro/autopilot.lua",          # v1: no es el nuestro
                                           "D:/missing/AUTOPILOT_V2.LUA"])   # registrado pero no existe
        self.write_collection("Otra", [str(old).replace("\\", "/")])          # duplicado en otra coleccion
        found = ai.find_registered_scripts(self.cfg)
        self.assertEqual(len(found), 2)
        by_exists = {f.exists: f for f in found}
        self.assertEqual(by_exists[True].path, old)
        self.assertEqual(by_exists[True].version, "2.0.0")
        self.assertIn(by_exists[True].collection, ("Untitled", "Otra"),
                      "la misma ruta en dos colecciones se reporta una sola vez")
        self.assertFalse(by_exists[False].exists)
        self.assertIsNone(by_exists[False].version)
        self.assertEqual(ai.find_registered_scripts(self.tmp / "no-config"), [])

    def test_update_writes_file_with_backup_and_skips_identical(self):
        src = self.tmp / "bundled.lua"; src.write_text(lua("2.1.0"))
        old = self.tmp / "obs" / "autopilot_v2.lua"; old.parent.mkdir(); old.write_text(lua("2.0.0"))
        targets = [ai.RegisteredScript(old, "Untitled", True, "2.0.0"),
                   ai.RegisteredScript(self.tmp / "obs" / "sub" / "autopilot_v2.lua", "Otra", False, None)]
        results = ai.update_registered_scripts(targets, source=src)
        self.assertTrue(all(r.ok for r in results), results)
        self.assertTrue(all(r.changed for r in results))
        self.assertEqual(ai.read_script_version(old), "2.1.0")
        self.assertEqual(ai.read_script_version(old.with_suffix(".lua.bak")), "2.0.0")
        self.assertEqual(ai.read_script_version(targets[1].path), "2.1.0")
        again = ai.update_registered_scripts([ai.RegisteredScript(old, "Untitled", True, "2.1.0")], source=src)
        self.assertTrue(again[0].ok and not again[0].changed)
        same = ai.update_registered_scripts([ai.RegisteredScript(src, "Dev", True, "2.1.0")], source=src)
        self.assertTrue(same[0].ok and not same[0].changed, "el propio embebido no se toca")
        missing = ai.update_registered_scripts([ai.RegisteredScript(old, "U", True, "2.1.0")], source=self.tmp / "nope.lua")
        self.assertFalse(missing[0].ok)

    def test_plan_update_states(self):
        old = self.tmp / "obs" / "autopilot_v2.lua"; old.parent.mkdir(); old.write_text(lua("2.0.0"))
        self.write_collection("Untitled", [str(old).replace("\\", "/")])
        local = LocalObs(exe=self.tmp / "bin/64bit/obs64.exe", root=self.tmp, portable=True, version=(32, 1, 2))
        with patch.object(ai, "bundled_script_version", return_value="2.1.0"):
            plan = ai.plan_update(local, running_version="2.0.0")
            self.assertTrue(plan.running_outdated)
            self.assertEqual([r.path for r in plan.outdated_files], [old])
            self.assertFalse(plan.files_current_but_not_loaded)
            old.write_text(lua("2.1.0"))
            plan = ai.plan_update(local, running_version="2.0.0")
            self.assertEqual(plan.outdated_files, [])
            self.assertTrue(plan.files_current_but_not_loaded, "archivo nuevo, OBS aun corre el viejo")
            plan = ai.plan_update(local, running_version="2.1.0")
            self.assertFalse(plan.running_outdated)
            plan = ai.plan_update(None, running_version="2.0.0")
            self.assertTrue(plan.running_outdated and plan.registered == [])


if __name__ == "__main__":
    unittest.main()
