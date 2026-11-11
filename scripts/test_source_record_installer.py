"""Tests de core/source_record_installer.py y OBSClient.has_source_record.

Sin OBS ni red: el bundle se simula en un directorio temporal.

Uso: venv\\Scripts\\python.exe scripts\\test_source_record_installer.py
"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import source_record_installer as sri
from models.obs_client import OBSClient, _GuardedClient


def make_fake_bundle(root: Path) -> Path:
    vendor = root / "vendor" / "source-record"
    for layout, dll_rel in (("new", "source-record.dll"),
                            ("legacy", "bin/64bit/source-record.dll")):
        base = vendor / layout / "source-record"
        dll = base / dll_rel
        dll.parent.mkdir(parents=True, exist_ok=True)
        dll.write_bytes(b"MZ-fake-" + layout.encode())
        (base / "data" / "locale").mkdir(parents=True, exist_ok=True)
        (base / "data" / "locale" / "en-US.ini").write_text("SourceRecord=\"Source Record\"\n")
        (base / "data" / "manifest.json").write_text("{}")
    (vendor / "LICENSE").write_text("GPL-2.0")
    return vendor


def make_fake_obs(root: Path, portable: bool) -> Path:
    exe = root / "bin" / "64bit" / "obs64.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    if portable:
        (root / "portable_mode.txt").write_text("")
    return exe


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="srtest_"))
        self.vendor = make_fake_bundle(self.tmp)
        patcher = patch.object(sri, "bundled_root", return_value=self.vendor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.programdata = self.tmp / "ProgramData" / "obs-studio" / "plugins"
        pd = patch.object(sri, "programdata_plugins_dir", return_value=self.programdata)
        pd.start()
        self.addCleanup(pd.stop)

    def local(self, portable, version):
        root = self.tmp / ("obs-portable" if portable else "obs-installed")
        exe = make_fake_obs(root, portable)
        return sri.LocalObs(exe=exe, root=root, portable=portable, version=version)

    def test_bundle_detected(self):
        self.assertTrue(sri.is_bundled())

    def test_plan_matrix(self):
        cases = [
            (False, (32, 1, 2), sri.LAYOUT_LEGACY, lambda l: self.programdata / "source-record" / "bin" / "64bit" / "source-record.dll"),
            (False, (33, 0, 1), sri.LAYOUT_NEW, lambda l: self.programdata / "source-record" / "source-record.dll"),
            (True, (32, 1, 2), sri.LAYOUT_INTREE, lambda l: l.root / "obs-plugins" / "64bit" / "source-record.dll"),
            (True, (33, 0, 1), sri.LAYOUT_NEW, lambda l: l.root / "plugins" / "source-record" / "source-record.dll"),
            (False, None, sri.LAYOUT_LEGACY, lambda l: self.programdata / "source-record" / "bin" / "64bit" / "source-record.dll"),
        ]
        for portable, version, layout, dll_of in cases:
            with self.subTest(portable=portable, version=version):
                local = self.local(portable, version)
                plan = sri.plan_install(local)
                self.assertEqual(plan.layout, layout)
                self.assertEqual(plan.dll_target, dll_of(local))
                data_targets = [dst for _s, dst in plan.files if dst.suffix == ".ini"]
                self.assertEqual(len(data_targets), 1)
                if layout == sri.LAYOUT_INTREE:
                    self.assertEqual(data_targets[0], local.root / "data" / "obs-plugins" / "source-record" / "locale" / "en-US.ini")
                else:
                    self.assertEqual(data_targets[0].parent.parent.name, "data")

    def test_websocket_version_overrides_exe_version(self):
        local = self.local(False, (32, 0, 0))
        plan = sri.plan_install(local, obs_version=(33, 0, 0))
        self.assertEqual(plan.layout, sri.LAYOUT_NEW)

    def test_install_copies_all_files(self):
        local = self.local(True, (32, 1, 2))
        plan = sri.plan_install(local)
        ok, msg = sri.install(plan)
        self.assertTrue(ok, msg)
        self.assertEqual((local.root / "obs-plugins" / "64bit" / "source-record.dll").read_bytes(), b"MZ-fake-legacy")
        self.assertTrue((local.root / "data" / "obs-plugins" / "source-record" / "locale" / "en-US.ini").is_file())
        self.assertTrue((local.root / "data" / "obs-plugins" / "source-record" / "manifest.json").is_file())
        self.assertIn("instalado", msg)

    def test_install_new_layout_in_programdata(self):
        local = self.local(False, (33, 1, 0))
        ok, _ = sri.install(sri.plan_install(local))
        self.assertTrue(ok)
        self.assertEqual((self.programdata / "source-record" / "source-record.dll").read_bytes(), b"MZ-fake-new")
        self.assertTrue((self.programdata / "source-record" / "data" / "manifest.json").is_file())

    def test_install_without_bundle_fails_clearly(self):
        with patch.object(sri, "bundled_root", return_value=self.tmp / "nope"):
            plan = sri.InstallPlan(sri.LAYOUT_NEW, self.tmp / "x", [], "")
            ok, msg = sri.install(plan)
        self.assertFalse(ok)
        self.assertIn("bundle_source_record", msg)

    def test_detect_local_obs_portable_and_installed(self):
        exe_p = make_fake_obs(self.tmp / "p", True)
        local = sri.detect_local_obs(str(exe_p))
        self.assertTrue(local.portable)
        self.assertEqual(local.root, (self.tmp / "p").resolve())
        exe_i = make_fake_obs(self.tmp / "i", False)
        self.assertFalse(sri.detect_local_obs(str(exe_i)).portable)
        self.assertIsNone(sri.detect_local_obs(str(self.tmp / "missing.exe")) if False else None)
        with patch.object(sri.obs_launcher, "find_obs_executable", return_value=None):
            self.assertIsNone(sri.detect_local_obs(""))

    def test_parse_version(self):
        self.assertEqual(sri.parse_version("32.1.2"), (32, 1, 2))
        self.assertEqual(sri.parse_version("33.0.1-beta2"), (33, 0, 1))
        self.assertEqual(sri.parse_version("33"), (33, 0, 0))
        self.assertIsNone(sri.parse_version(""))

    @unittest.skipUnless(sys.platform == "win32", "solo Windows")
    def test_exe_file_version_reads_versioninfo(self):
        version = sri.exe_file_version(r"C:\Windows\System32\kernel32.dll")
        self.assertIsNotNone(version)
        self.assertGreaterEqual(version[0], 6)
        self.assertIsNone(sri.exe_file_version(str(self.tmp / "nope.exe")))

    def test_export_package_layouts(self):
        for major, expect in ((32, "plugins/source-record/bin/64bit/source-record.dll"),
                              (33, "plugins/source-record/source-record.dll"),
                              (None, "plugins/source-record/bin/64bit/source-record.dll")):
            with self.subTest(major=major):
                out = sri.export_package(self.tmp / "out", major)
                self.assertTrue(out.name.startswith("source-record-0.5.0-OBS"))
                with zipfile.ZipFile(out) as z:
                    names = set(z.namelist())
                    self.assertIn(expect, names)
                    self.assertIn("plugins/source-record/data/locale/en-US.ini", names)
                    self.assertIn("LEEME.txt", names)
                    self.assertIn("LICENSE", names)
                    leeme = z.read("LEEME.txt").decode("utf-8")
                    self.assertIn("ProgramData", leeme)
                    self.assertIn("reinicia" if False else "abrir OBS", leeme)


class HasSourceRecordTests(unittest.TestCase):
    def client(self, session):
        obs = OBSClient()
        obs.client = _GuardedClient(session, obs)
        return obs

    def test_kind_list_present_and_absent(self):
        session = Mock()
        session.get_source_filter_kind_list.return_value = SimpleNamespace(
            source_filter_kinds=["color_filter", "source_record_filter"])
        self.assertTrue(self.client(session).has_source_record())
        session.get_source_filter_kind_list.return_value = SimpleNamespace(
            sourceFilterKinds=["color_filter"])
        self.assertFalse(self.client(session).has_source_record())

    def test_fallback_to_default_settings(self):
        session = Mock()
        session.get_source_filter_kind_list.side_effect = RuntimeError("unknown request")
        session.get_source_filter_default_settings.return_value = SimpleNamespace(default_filter_settings={})
        self.assertTrue(self.client(session).has_source_record())
        session.get_source_filter_default_settings.side_effect = RuntimeError("No filter kind found (600)")
        self.assertFalse(self.client(session).has_source_record())
        session.get_source_filter_default_settings.side_effect = RuntimeError("timed out")
        self.assertIsNone(self.client(session).has_source_record())

    def test_disconnected_returns_none(self):
        self.assertIsNone(OBSClient().has_source_record())
        self.assertIsNone(OBSClient().list_source_filter_kinds())


if __name__ == "__main__":
    unittest.main()
