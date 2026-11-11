"""Regressions for startup repairs and safe logging; no OBS needed."""
import logging
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from controllers.countdown_controller import CountdownController
from controllers.canal_controller import CanalController
from core.autopilot_client import AutopilotClientV2, CONFIG_SOURCE_V2, STATE_SOURCE_V2
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
