"""Connection-card regressions. Run with QT_QPA_PLATFORM=offscreen; no OBS required."""
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread, QBuffer, QIODevice
from PyQt6.QtGui import QFontDatabase, QPixmap, QColor
from controllers.home_controller import HomeController, _ChannelFramesWorker
from core.workers import OBSWatchdog
from models.obs_client import OBSClient, _GuardedClient
from obsws_python.error import OBSSDKTimeoutError
from views.home_view import HomeView
from views.logs_view import LogsView
from views.widgets import HeroHeader
from views.styles import LIGHT_THEME_QSS


def fake_session():
    session = Mock()
    session.get_version.return_value = SimpleNamespace(obs_version='32.1.2')
    session.get_profile_list.return_value = SimpleNamespace(current_profile_name='Canal de Panamá')
    session.get_scene_list.return_value = SimpleNamespace(scenes=[])
    return session


class ConnectionInfoTests(unittest.TestCase):
    def setUp(self):
        self.obs = OBSClient()
        self.raw = fake_session()
        self.obs.client = _GuardedClient(self.raw, self.obs)
        self.obs.connection_host = '192.0.2.10'
        self.obs.connection_port = 4455
        self.obs.connected_since = time.monotonic() - 120

    def test_actual_version_profile_zero_scenes_and_elapsed(self):
        info = self.obs.get_connection_info()
        self.assertTrue(info['connected'])
        self.assertEqual(info['version'], '32.1.2')
        self.assertEqual(info['profile'], 'Canal de Panamá')
        self.assertEqual(info['scene_count'], 0)
        self.assertEqual(info['host'], '192.0.2.10')
        self.assertGreaterEqual(info['connected_seconds'], 120)

    def test_optional_profile_failure_preserves_other_details(self):
        self.raw.get_profile_list.side_effect = RuntimeError('unsupported')
        info = self.obs.get_connection_info()
        self.assertTrue(info['connected'])
        self.assertEqual(info['version'], '32.1.2')
        self.assertEqual(info['profile'], '')
        self.assertEqual(info['scene_count'], 0)

    def test_timeout_discards_session_and_stale_details(self):
        self.raw.get_version.side_effect = OBSSDKTimeoutError('timed out')
        self.assertEqual(self.obs.get_connection_info(), {'connected': False})
        self.assertIsNone(self.obs.client)
        self.assertIsNone(self.obs.connected_since)
        self.raw.get_profile_list.assert_not_called()

    def test_reconnect_resets_endpoint_and_connection_clock(self):
        with patch('models.obs_client.obs.ReqClient', return_value=fake_session()):
            self.assertTrue(self.obs.connect('192.0.2.20', 4466)[0])
        info = self.obs.get_connection_info()
        self.assertEqual((info['host'], info['port']), ('192.0.2.20', 4466))
        self.assertLess(info['connected_seconds'], 2)
        self.obs.disconnect()
        self.assertEqual(self.obs.get_connection_info(), {'connected': False})

    def test_parallel_requests_do_not_overlap_on_socket(self):
        active = 0
        maximum = 0
        lock = threading.Lock()
        def request():
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.02)
            with lock:
                active -= 1
        self.raw.get_version.side_effect = request
        threads = [threading.Thread(target=self.obs.client.get_version) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(maximum, 1)


class CardControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if not QFontDatabase.families():
            for font in ('segoeui.ttf', 'segoeuib.ttf'):
                QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
        cls.app.setStyleSheet(LIGHT_THEME_QSS)

    def test_disconnected_card_clears_old_values_and_disables_disconnect(self):
        view = HomeView()
        view.set_obs_card(True, '32.1.2', 'localhost', 4455, 0, 'Canal', 9240)
        self.assertEqual(view.obs_card.values['scenes'].text(), '0')
        self.assertEqual(view.obs_card.values['elapsed'].text(), '2 h 34 min')
        self.assertTrue(view.btn_obs_disconnect.isEnabled())
        view.set_obs_card(False)
        self.assertFalse(view.btn_obs_disconnect.isEnabled())
        self.assertEqual(view.obs_card.version.text(), 'OBS Studio')
        self.assertEqual(view.obs_card.values['profile'].text(), '—')
        view.close()

    def test_app_version_follows_release_version_independently_of_obs(self):
        from core import version
        with patch.object(version, 'APP_VERSION', '2.4.1-rc.2'):
            view = HomeView()
        view.set_obs_card(True, '32.1.2')
        self.assertIn('v2.4.1-rc.2', view.obs_card.app_version.text())
        self.assertEqual(view.obs_card.version.text(), 'OBS Studio 32.1.2')
        view.set_obs_card(False)
        self.assertIn('v2.4.1-rc.2', view.obs_card.app_version.text())
        self.assertEqual(view.obs_card.version.text(), 'OBS Studio')
        view.close()

    def test_async_response_from_replaced_session_is_ignored(self):
        entered = threading.Event()
        release = threading.Event()
        obs = Mock(client=object())
        def slow_info():
            entered.set()
            release.wait(2)
            return {'connected': True, 'version': 'old version'}
        obs.get_connection_info.side_effect = slow_info
        view = Mock()
        controller = HomeController(
            view, Mock(get_all_canales=lambda: []),
            Mock(get_all_scenes=lambda: []), obs,
            Mock(get_settings=lambda: {}), Mock())
        self.assertTrue(entered.wait(2))
        # The GUI event loop remains available during a slow OBS request.
        self.app.processEvents()
        view.set_obs_card.reset_mock()
        obs.client = object()
        release.set()
        controller._status_worker.wait(2000)
        self.app.processEvents()
        view.set_obs_card.assert_not_called()
        controller.stop()

    def test_connected_response_does_not_depend_on_qt_sender_wrapper(self):
        obs = Mock(client=object())
        info = {'connected': True, 'version': '32.1.2', 'profile': 'Canal'}
        obs.get_connection_info.return_value = info
        view = Mock()
        # Queued Qt signals may expose a base QThread wrapper as sender,
        # without the Python attributes on our worker subclass.
        sender_wrapper = QThread()
        with patch.object(HomeController, 'sender', return_value=sender_wrapper), \
                patch('sys.excepthook') as uncaught:
            controller = HomeController(
                view, Mock(get_all_canales=lambda: []),
                Mock(get_all_scenes=lambda: []), obs,
                Mock(get_settings=lambda: {}), Mock())
            self.assertTrue(controller._status_worker.wait(2000))
            view.set_obs_card.reset_mock()
            self.app.processEvents()
            controller.stop()
            uncaught.assert_not_called()
        view.set_obs_card.assert_called_once_with(**info)
        view.set_kpi_conexion.assert_called_with(True, '32.1.2')

    def test_logs_header_keeps_same_height_as_other_sections(self):
        logs = LogsView()
        logs.resize(1200, 800)
        logs.show()
        self.app.processEvents()
        header = logs.findChild(HeroHeader)
        self.assertLess(header.height(), 130)
        self.assertGreater(logs.text.height(), 500)
        logs.close()

    def test_channel_frames_show_and_survive_metadata_refresh_then_clear(self):
        view = HomeView()
        view.set_channel_previews([('Piso 1', 'Piso 1', True)], 1)
        card = view._preview_widgets[0]
        pixmap = QPixmap(480, 270)
        pixmap.fill(QColor('red'))
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, 'PNG')
        view.set_channel_preview('Piso 1', bytes(buffer.data()))
        self.assertFalse(card._preview.pixmap.isNull())
        self.assertTrue(all(label.isHidden() for label in card._placeholder_labels))
        view.set_channel_previews([('Piso 1', 'Piso 1', False)], 1)
        self.assertIs(view._preview_widgets[0], card)
        self.assertFalse(card._preview.pixmap.isNull())
        view.set_channel_preview('Piso 1', None)
        self.assertTrue(card._preview.pixmap.isNull())
        self.assertTrue(all(not label.isHidden() for label in card._placeholder_labels))
        view.close()

    def test_channel_worker_captures_each_scene_and_skips_absent_sources(self):
        obs = Mock(client=object())
        obs.list_scene_names.return_value = ['Piso 1', 'Piso 2']
        obs.get_scene_screenshot_bytes.side_effect = [b'frame1', b'frame2']
        worker = _ChannelFramesWorker(obs, ['Piso 1', 'Piso 2', 'Removed'])
        frames = Mock()
        worker.frame_ready.connect(frames)
        worker.run()
        self.assertEqual([c.args[0] for c in obs.get_scene_screenshot_bytes.call_args_list], ['Piso 1', 'Piso 2'])
        self.assertEqual([c.args[2] for c in frames.call_args_list], [b'frame1', b'frame2', None])
        self.assertTrue(all(c.args[0] is obs.client for c in frames.call_args_list))

    def test_home_frames_ignore_old_session_and_removed_channel(self):
        view = Mock()
        obs = Mock(client=object())
        controller = HomeController(view, Mock(get_all_canales=lambda: []),
            Mock(get_all_scenes=lambda: []), obs, Mock(get_settings=lambda: {}), Mock())
        controller._preview_names = ('Piso 1',)
        controller._apply_frame(object(), 'Piso 1', b'stale')
        controller._apply_frame(obs.client, 'Removed', b'stale')
        view.set_channel_preview.assert_not_called()
        controller._apply_frame(obs.client, 'Piso 1', b'current')
        view.set_channel_preview.assert_called_once_with('Piso 1', b'current')
        view.set_channel_preview.reset_mock()
        obs.client = None
        controller._refresh_frames()
        view.set_channel_preview.assert_called_once_with('Piso 1', None)
        controller.stop()

    def test_home_frames_do_not_block_gui_or_start_overlapping_workers(self):
        entered, release = threading.Event(), threading.Event()
        view = Mock()
        obs = Mock(client=object())
        obs.list_scene_names.return_value = ['Piso 1']
        def snapshot(*args):
            entered.set()
            release.wait(2)
            return b'frame'
        obs.get_scene_screenshot_bytes.side_effect = snapshot
        controller = HomeController(view, Mock(get_all_canales=lambda: []),
            Mock(get_all_scenes=lambda: []), obs, Mock(get_settings=lambda: {}), Mock())
        controller._preview_names = ('Piso 1',)
        view.isVisible.return_value = False
        controller._refresh_frames()
        self.assertIsNone(controller._frames_worker)
        view.isVisible.return_value = True
        controller._refresh_frames()
        try:
            self.assertTrue(entered.wait(2))
            worker = controller._frames_worker
            controller._refresh_frames()
            self.assertIs(worker, controller._frames_worker)
            self.app.processEvents()
            self.assertEqual(obs.get_scene_screenshot_bytes.call_count, 1)
        finally:
            release.set()
            controller.stop()

    def test_manual_disconnect_suspends_reconnect_even_during_attempt(self):
        obs = Mock()
        watchdog = OBSWatchdog(obs, lambda: {'host': 'localhost', 'port': 4455, 'password': ''})
        def connect(*args, **kwargs):
            watchdog.suspend()
            return True, 'ok'
        obs.connect.side_effect = connect
        restored = Mock()
        watchdog.connection_restored.connect(restored)
        watchdog._reconnect_loop()
        obs.disconnect.assert_called_once()
        restored.assert_not_called()
        watchdog.mark_connected()
        self.assertFalse(watchdog._suspended)

    def test_old_retry_does_not_replace_new_manual_connection(self):
        obs = Mock()
        obs.connect.return_value = (False, 'offline')
        watchdog = OBSWatchdog(obs, lambda: {'host': 'localhost', 'port': 4455, 'password': ''})
        def manual_reconnect(_seconds):
            watchdog.suspend()
            watchdog.mark_connected()
        with patch('core.workers.time.sleep', side_effect=manual_reconnect):
            watchdog._reconnect_loop()
        obs.connect.assert_called_once()


if __name__ == '__main__':
    unittest.main()
