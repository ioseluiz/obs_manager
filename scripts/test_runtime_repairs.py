"""Regressions for startup repairs, bundled preview and safe logging; no OBS needed."""
import io
import logging
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from controllers.countdown_controller import CountdownController
from controllers.canal_controller import CanalController
from core.autopilot_client import AutopilotClientV2, CONFIG_SOURCE_V2, STATE_SOURCE_V2
from core.channel_preview import find_ffplay, udp_endpoint, can_receive_locally, UdpPreview
from core.logging_setup import RedactingFormatter, redact_secrets, register_secret


class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_credentials_redacted_in_formatted_message_and_traceback(self):
        register_secret('synthetic-secret-for-test')
        record = logging.LogRecord('sdk', logging.INFO, '', 0,
            "password=%r token=%s", ('synthetic-secret-for-test', 'token-value'), None)
        formatter = RedactingFormatter('%(message)s')
        rendered = formatter.format(record)
        self.assertNotIn('synthetic-secret-for-test', rendered)
        self.assertNotIn('token-value', rendered)
        try:
            raise ValueError('synthetic-secret-for-test')
        except ValueError:
            record = logging.LogRecord('sdk', 40, '', 0, 'request failed', (), sys.exc_info())
        self.assertNotIn('synthetic-secret-for-test', formatter.format(record))
        self.assertNotIn('old-secret', redact_secrets('{"password": "old-secret"}'))

    def test_bundled_player_does_not_need_path_or_python_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            player = Path(tmp) / 'vendor/ffmpeg/bin/ffplay.exe'
            player.parent.mkdir(parents=True)
            player.touch()
            with patch.object(sys, '_MEIPASS', tmp, create=True), patch('shutil.which', return_value=None):
                self.assertEqual(find_ffplay(), str(player))

    def test_udp_endpoints_and_remote_destinations(self):
        self.assertEqual(udp_endpoint('udp://239.1.2.3:8000?pkt_size=1316'), ('239.1.2.3', 8000))
        for invalid in ('http://localhost:80', 'udp://localhost', 'udp://localhost:99999'):
            with self.assertRaises(ValueError):
                udp_endpoint(invalid)
        self.assertTrue(can_receive_locally('127.0.0.1'))
        self.assertTrue(can_receive_locally('239.1.2.3'))
        with patch('socket.socket') as sock:
            sock.return_value.__enter__.return_value.getsockname.return_value = ('192.0.2.1', 123)
            self.assertFalse(can_receive_locally('192.0.2.2'))

    def test_udp_relay_transfers_packets_and_stops_without_another_datagram(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        written = threading.Event()
        class Sink(io.BytesIO):
            def write(self, data):
                result = super().write(data)
                written.set()
                return result
            def close(self):
                pass
        process = Mock(stdin=Sink())
        process.poll.return_value = None
        preview = UdpPreview('127.0.0.1', port, 'Test', 'ffplay.exe')
        with patch('core.channel_preview.subprocess.Popen', return_value=process):
            preview.start()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    for _ in range(30):
                        sender.sendto(b'video-packet', ('127.0.0.1', port))
                        if written.wait(.05):
                            break
                self.assertTrue(written.is_set())
                self.assertIn(b'video-packet', process.stdin.getvalue())
            finally:
                preview.stop()
            self.assertFalse(preview._thread.is_alive())
            process.terminate.assert_called()

    def test_absent_autopilot_never_requests_nonexistent_source(self):
        obs = Mock(client=Mock())
        obs.list_input_names.return_value = set()
        client = AutopilotClientV2(obs)
        for _ in range(3):
            self.assertFalse(client.is_installed())
            self.assertIsNone(client.read_state())
        obs.client.get_input_settings.assert_not_called()
        obs.list_input_names.return_value = {CONFIG_SOURCE_V2, STATE_SOURCE_V2}
        obs.client.get_input_settings.return_value = SimpleNamespace(input_settings={'text': '{}'})
        self.assertTrue(client.is_installed())

    def test_channel_scene_preview_does_not_query_a_self_nested_source(self):
        from views.canal_detail_view import CanalDetailView
        from PyQt6.QtWidgets import QWidget
        view = QWidget()
        view._canal_id = 1
        view.canal_model = Mock()
        view.canal_model.get_canal.return_value = {'nombre': 'Canal', 'url_destino': ''}
        obs = Mock(client=object(), canvas_width=1920, canvas_height=1080)
        view.canal_controller = Mock(obs_client=obs)
        with patch('views.scene_preview_dialog.ScenePreviewDialog') as dialog:
            CanalDetailView._on_preview(view)
            self.assertIsNone(dialog.call_args.args[2])
            dialog.return_value.show.assert_called_once()
        view.close()

    def counter(self, scene='Canal'):
        counter = CountdownController.__new__(CountdownController)
        counter.view = Mock()
        counter.obs_client = Mock(client=object())
        counter.obs_client.list_scene_names.return_value = ['Canal']
        counter.obs_client.list_text_input_names.return_value = {'Days'}
        counter.obs_client.create_text_input.return_value = (True, '')
        counter.countdowns = [{'nombre': 'Test', 'escena': scene,
            'fecha_objetivo': '2030-12-25T00:00:00', 'repetir_anual': False,
            'source_dias': 'Days', 'source_horas': 'Hours', 'source_minutos': '', 'source_segundos': ''}]
        counter._was_syncing_before_disconnect = False
        counter.is_syncing = False
        counter._available_sources = set()
        return counter

    def test_only_missing_countdown_sources_created_in_assigned_scene(self):
        counter = self.counter()
        counter.refresh_from_obs()
        counter.obs_client.create_text_input.assert_called_once_with('Canal', 'Hours')
        counter.obs_client.set_text_source_text.assert_called_once()
        self.assertEqual(counter.obs_client.set_text_source_text.call_args.args[0], 'Days')
        counter.obs_client.list_text_input_names.return_value = {'Days', 'Hours'}
        counter.refresh_from_obs()
        counter.obs_client.create_text_input.assert_called_once()

    def test_unassigned_countdown_does_not_create_in_arbitrary_scene(self):
        counter = self.counter('')
        counter.refresh_from_obs()
        counter.obs_client.create_text_input.assert_not_called()
        self.assertEqual(counter.obs_client.set_text_source_text.call_count, 1)

    def test_playlist_reapply_preserves_text_and_reuses_placeholder(self):
        ctrl = CanalController.__new__(CanalController)
        raw = Mock()
        ctrl._raw_client = lambda: raw
        items = [{'sceneItemId': 1, 'inputKind': 'text_gdiplus_v3'},
                 {'sceneItemId': 2, 'inputKind': 'scene'}]
        raw.get_scene_item_list.return_value = SimpleNamespace(scene_items=items)
        # Obtain actual placeholder naming from the controller.
        from controllers.canal_controller import _PLACEHOLDER_SUFFIX
        raw.get_input_list.return_value = SimpleNamespace(inputs=[{'inputName': 'Canal' + _PLACEHOLDER_SUFFIX}])
        raw.create_scene_item.return_value = SimpleNamespace(scene_item_id=3)
        ctrl._reconcile_scene_items('Canal', [])
        raw.remove_scene_item.assert_called_once_with('Canal', 2)
        raw.create_input.assert_not_called()
        raw.set_scene_item_index.assert_called_once_with('Canal', 1, 1)


if __name__ == '__main__':
    unittest.main()
