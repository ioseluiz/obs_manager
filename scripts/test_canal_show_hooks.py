"""Smoke test headless de los hooks por tipo en CanalController._show_item.

Fase 1.F1/F2/F3 del plan de unificacion:

- F1 — URL con `refresh_interval_seg > 0` → arma QTimer que llama
  OBSClient.refresh_browser_source cada N segundos.
- F2 — file con `video_offset_seg > 0` → set_media_cursor al activar.
- F3 — secuencia cuyo nombre coincide con settings `cal_scene` →
  calendar_controller.move_circle_to_today(show_messages=False).

Uso::

    python scripts/test_canal_show_hooks.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


def _ensure_qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


def _build_state_and_controller():
    """Infra comun para los tests. Devuelve (cc, state, obs, cal_ctrl)."""
    from controllers.canal_controller import (
        CanalController,
        _PlaylistEntry,
        _RotatorState,
    )
    obs = MagicMock()
    obs.client = MagicMock()  # 'connected'
    canal_model = MagicMock()
    scene_model = MagicMock()
    cal_ctrl = MagicMock()
    cal_ctrl.settings_model.get_settings.return_value = {
        "cal_scene": "CalendarScene"
    }
    cc = CanalController(
        canal_model, scene_model, obs,
        calendar_controller=cal_ctrl,
    )

    state = _RotatorState(canal_id=1, scene_name="canal_x")
    state.item_to_scene_item = {10: 100, 11: 101, 12: 102, 13: 103}
    state.item_to_seq = {
        10: {"name": "DashA", "tipo": "url",
             "refresh_interval_seg": 30, "duration": 60},
        11: {"name": "VideoB", "tipo": "file",
             "video_offset_seg": 45, "duration": 60},
        12: {"name": "CalendarScene", "tipo": "file",
             "duration": 60},
        13: {"name": "StaticImage", "tipo": "file",
             "video_offset_seg": 0, "duration": 60},
    }
    state.playlist = [
        _PlaylistEntry(item_id=i, duration_seg=60, active_days=127,
                       time_start=None, time_end=None)
        for i in (10, 11, 12, 13)
    ]
    return cc, state, obs, cal_ctrl


def test_f1_url_refresh_armado():
    print("[F1: URL con refresh_interval_seg arma refresh_timer]")
    _ensure_qapp()
    cc, state, obs, _ = _build_state_and_controller()
    cc._show_item(state, 10)
    _check(state.refresh_timer is not None,
           "refresh_timer instanciado")
    _check(state.active_input_name == "DashA_Web",
           "active_input_name = 'DashA_Web' (convencion SceneController)")


def test_f1_url_sin_interval_no_arma():
    print("[F1: URL con refresh_interval_seg=0 NO arma refresh_timer]")
    _ensure_qapp()
    cc, state, obs, _ = _build_state_and_controller()
    state.item_to_seq[10]["refresh_interval_seg"] = 0
    cc._show_item(state, 10)
    _check(state.active_input_name is None,
           "sin interval no se setea active_input_name")


def test_f1_hide_para_refresh():
    print("[F1: _hide_current para el refresh_timer]")
    _ensure_qapp()
    cc, state, obs, _ = _build_state_and_controller()
    cc._show_item(state, 10)
    state.active_index = 0
    cc._hide_current(state)
    _check(state.active_input_name is None,
           "active_input_name limpiado tras _hide_current")


def test_f2_video_offset_seek():
    print("[F2: file con video_offset_seg llama set_media_cursor]")
    _ensure_qapp()
    cc, state, obs, _ = _build_state_and_controller()
    obs.set_media_cursor.reset_mock()
    cc._show_item(state, 11)
    obs.set_media_cursor.assert_called_once_with("VideoB_Contenido", 45000)
    _check(True, "set_media_cursor('VideoB_Contenido', 45000) llamado")


def test_f2_sin_offset_no_llama():
    print("[F2: file con video_offset_seg=0 NO llama set_media_cursor]")
    _ensure_qapp()
    cc, state, obs, _ = _build_state_and_controller()
    obs.set_media_cursor.reset_mock()
    cc._show_item(state, 13)
    _check(not obs.set_media_cursor.called,
           "set_media_cursor NO fue llamado")


def test_f3_calendar_move_circle():
    print("[F3: secuencia cal_scene mueve el marcador del calendario]")
    _ensure_qapp()
    cc, state, obs, cal_ctrl = _build_state_and_controller()
    cal_ctrl.move_circle_to_today.reset_mock()
    cc._show_item(state, 12)
    cal_ctrl.move_circle_to_today.assert_called_once_with(show_messages=False)
    _check(True, "move_circle_to_today(show_messages=False) llamado")


def test_f3_sin_calendar_controller_no_falla():
    print("[F3: sin calendar_controller el hook no falla]")
    _ensure_qapp()
    from controllers.canal_controller import (
        CanalController, _PlaylistEntry, _RotatorState,
    )
    obs = MagicMock()
    obs.client = MagicMock()
    cc = CanalController(MagicMock(), MagicMock(), obs,
                          calendar_controller=None)
    state = _RotatorState(canal_id=1, scene_name="x")
    state.item_to_scene_item = {10: 100}
    state.item_to_seq = {10: {"name": "Scene", "tipo": "file"}}
    state.playlist = [_PlaylistEntry(item_id=10, duration_seg=1,
                                       active_days=127, time_start=None,
                                       time_end=None)]
    cc._show_item(state, 10)  # no debe lanzar
    _check(True, "sin calendar_controller no lanza AttributeError")


def test_rotacion_consecutiva_para_refresh_previo():
    print("[Integracion: pasar de URL a video para el refresh del URL]")
    _ensure_qapp()
    cc, state, obs, _ = _build_state_and_controller()
    cc._show_item(state, 10)
    _check(state.active_input_name == "DashA_Web", "URL activo")
    state.active_index = 0
    cc._hide_current(state)
    cc._show_item(state, 11)  # video
    _check(state.active_input_name is None,
           "al cambiar a video, refresh de URL se para y active_input_name = None")


def main():
    print("=== CanalController show-hooks smoke tests ===")
    test_f1_url_refresh_armado()
    test_f1_url_sin_interval_no_arma()
    test_f1_hide_para_refresh()
    test_f2_video_offset_seek()
    test_f2_sin_offset_no_llama()
    test_f3_calendar_move_circle()
    test_f3_sin_calendar_controller_no_falla()
    test_rotacion_consecutiva_para_refresh_previo()
    print("\n=== TODO OK ===")


if __name__ == "__main__":
    main()
