"""Smoke test headless de controllers/autopilot_v2_controller.py.

Verifica la funcion pura `collect_canales_payload` (sin red ni QTimer) y
el ciclo start/stop del `AutopilotV2Controller` (con QApplication minima
para que QTimer no explote; sin event loop activo).

Uso::

    python scripts/test_autopilot_v2_controller.py

Exit code 0 si todo verde; 1 en la primera falla.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from controllers.autopilot_v2_controller import (  # noqa: E402
    AutopilotV2Controller,
    collect_canales_payload,
)
from controllers.canal_controller import _PlaylistEntry, _RotatorState  # noqa: E402
from core.autopilot_client import MODE_SCENE_ITEMS  # noqa: E402


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


def _ensure_qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


# --------------------------------------------------------------------------
# Helpers de fixture
# --------------------------------------------------------------------------

def _make_state(canal_id: int, scene_name: str,
                items: list[tuple[int, int, int]],
                active_index: int = -1,
                remaining_ms: int = 0):
    """items: lista de (canal_item_id, duration_seg, scene_item_id)."""
    state = _RotatorState(canal_id=canal_id, scene_name=scene_name)
    state.item_to_scene_item = {ii: si for (ii, _, si) in items}
    state.playlist = [
        _PlaylistEntry(item_id=ii, duration_seg=d,
                       active_days=127, time_start=None, time_end=None)
        for (ii, d, _) in items
    ]
    state.active_index = active_index
    return state


# FakeSceneController ELIMINADO — Canal Principal legacy fue
# eliminado como parte de la unificacion.


class FakeCanalController:
    """Doble headless del CanalController real.

    Expone solo lo que `collect_canales_payload` consume + la senal
    `canal_status_changed` como MagicMock (para que el AutopilotV2Controller
    pueda hacer `.connect(...)` sin romperse).
    """
    def __init__(self):
        self._rotators = {}
        self.canal_model = MagicMock()
        self.scene_model = MagicMock()
        self.canal_status_changed = MagicMock()
        self._status_map = {}

    def set_status(self, canal_id: int, active_index: int, remaining_ms: int):
        self._status_map[canal_id] = {
            "canal_id": canal_id, "applied": True,
            "active_index": active_index, "remaining_ms": remaining_ms,
        }

    def get_status(self, canal_id: int):
        return self._status_map.get(canal_id,
                                     {"canal_id": canal_id, "applied": False})


# --------------------------------------------------------------------------
# Tests de collect_canales_payload
# --------------------------------------------------------------------------

def test_collect_happy_path_2_canales():
    print("[collect: 2 canales habilitados con 2 items cada uno]")
    cc = FakeCanalController()

    # Canal 1
    cc._rotators[1] = _make_state(1, "canal_a",
                                   [(10, 20, 100), (11, 30, 101)],
                                   active_index=1, remaining_ms=12000)
    # Canal 2
    cc._rotators[2] = _make_state(2, "canal_b",
                                   [(20, 15, 200), (21, 45, 201)],
                                   active_index=0, remaining_ms=5000)

    cc.canal_model.get_canal.side_effect = lambda cid: {
        1: {"nombre": "canal_a", "habilitado": True},
        2: {"nombre": "canal_b", "habilitado": True},
    }.get(cid)
    cc.canal_model.get_items.side_effect = lambda cid: {
        1: [{"id": 10, "secuencia_id": 100},
            {"id": 11, "secuencia_id": 101}],
        2: [{"id": 20, "secuencia_id": 200},
            {"id": 21, "secuencia_id": 201}],
    }.get(cid, [])
    cc.scene_model.get_scene.side_effect = lambda sid: {
        100: {"name": "Esc A1"}, 101: {"name": "Esc A2"},
        200: {"name": "Esc B1"}, 201: {"name": "Esc B2"},
    }.get(sid)

    cc.set_status(1, active_index=1, remaining_ms=12000)
    cc.set_status(2, active_index=0, remaining_ms=5000)

    canales = collect_canales_payload(cc)
    _check(len(canales) == 2, "2 canales en el payload")

    by_id = {c["canal_id"]: c for c in canales}

    c1 = by_id[1]
    _check(c1["modo_rotacion"] == MODE_SCENE_ITEMS, "canal 1 modo scene_items")
    _check(c1["scene_name"] == "canal_a", "canal 1 scene_name")
    _check(c1["filter_name"] == "udp_out", "canal 1 filter_name")
    _check(len(c1["playlist"]) == 2, "canal 1 playlist len 2")
    _check(c1["playlist"][0]["name"] == "Esc A1", "canal 1 item 0 name")
    _check(c1["playlist"][0]["scene_item_id"] == 100, "canal 1 item 0 scene_item_id")
    _check(c1["playlist"][0]["duration_seg"] == 20, "canal 1 item 0 duration_seg")
    _check(c1["handoff"]["active_index"] == 2,
           "canal 1 handoff active_index 1-based (1->2)")
    _check(c1["handoff"]["seconds_remaining"] == 12,
           "canal 1 handoff seconds_remaining = 12 (12000ms)")

    c2 = by_id[2]
    _check(c2["handoff"]["active_index"] == 1,
           "canal 2 handoff active_index 1-based (0->1)")
    _check(c2["handoff"]["seconds_remaining"] == 5,
           "canal 2 handoff seconds_remaining = 5 (5000ms)")


def test_collect_filtra_deshabilitados_y_sin_estado():
    print("[collect: filtra canales deshabilitados y sin _RotatorState]")
    cc = FakeCanalController()
    # Canal 1 con estado pero habilitado=False
    cc._rotators[1] = _make_state(1, "a", [(10, 10, 100)])
    # Canal 2 sin estado (nunca aplicado)
    cc.canal_model.get_canal.side_effect = lambda cid: {
        1: {"nombre": "a", "habilitado": False},
        2: {"nombre": "b", "habilitado": True},
    }.get(cid)
    cc.canal_model.get_items.return_value = []
    cc.scene_model.get_scene.return_value = None

    canales = collect_canales_payload(cc)
    _check(len(canales) == 0, "ningun canal pasa el filtro")


def test_collect_canal_sin_scene_item_mapping():
    print("[collect: item sin scene_item_id no entra en playlist publicada]")
    cc = FakeCanalController()
    state = _RotatorState(canal_id=1, scene_name="a")
    state.item_to_scene_item = {10: 100}  # solo item 10 mapeado
    state.playlist = [
        _PlaylistEntry(item_id=10, duration_seg=5, active_days=127,
                       time_start=None, time_end=None),
        _PlaylistEntry(item_id=11, duration_seg=5, active_days=127,
                       time_start=None, time_end=None),  # sin mapping
    ]
    cc._rotators[1] = state
    cc.canal_model.get_canal.return_value = {"nombre": "a", "habilitado": True}
    cc.canal_model.get_items.return_value = [
        {"id": 10, "secuencia_id": 100},
        {"id": 11, "secuencia_id": 101},
    ]
    cc.scene_model.get_scene.side_effect = lambda sid: {
        100: {"name": "A1"}, 101: {"name": "A2"},
    }.get(sid)
    cc.set_status(1, -1, 0)

    canales = collect_canales_payload(cc)
    _check(len(canales) == 1, "canal publicado")
    _check(len(canales[0]["playlist"]) == 1,
           "solo el item con scene_item_id entra en la playlist publicada")
    _check(canales[0]["playlist"][0]["scene_item_id"] == 100,
           "scene_item_id correcto")


def test_collect_handoff_sin_item_activo():
    print("[collect: handoff cuando no hay item activo (active_index=-1)]")
    cc = FakeCanalController()
    cc._rotators[1] = _make_state(1, "a", [(10, 10, 100)])
    cc.canal_model.get_canal.return_value = {"nombre": "a", "habilitado": True}
    cc.canal_model.get_items.return_value = [{"id": 10, "secuencia_id": 100}]
    cc.scene_model.get_scene.return_value = {"name": "A1"}
    cc.set_status(1, -1, 0)

    canales = collect_canales_payload(cc)
    h = canales[0]["handoff"]
    _check(h["active_index"] == 0,
           "handoff active_index = 0 cuando no hay activo "
           "(cliente lo filtrara)")
    _check(h["seconds_remaining"] == 0,
           "handoff seconds_remaining = 0")


def test_collect_sin_rotadores():
    print("[collect: sin canales -> lista vacia]")
    cc = FakeCanalController()
    _check(collect_canales_payload(cc) == [], "lista vacia")


# --------------------------------------------------------------------------
# Tests de Canal Principal — ELIMINADOS en la unificacion. Todo se
# rota ahora via CanalController multi-salida; el modo program_global
# y el canal_id=-1 ya no existen.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Tests de AutopilotV2Controller
# --------------------------------------------------------------------------

def test_start_publica_config_cuando_lua_instalado():
    print("[Controller: start() publica config inicial si Lua instalado]")
    _ensure_qapp()

    cc = FakeCanalController()
    ap_client = MagicMock()
    ap_client.is_installed.return_value = True

    ctrl = AutopilotV2Controller(ap_client, cc)
    ctrl.start()
    _check(ap_client.publish_config.called,
           "publish_config llamado al arrancar")
    args, kwargs = ap_client.publish_config.call_args
    _check(kwargs.get("bump_version", False) is True,
           "bump_version=True en publish inicial")
    ctrl.stop()


def test_start_no_publica_si_lua_no_instalado():
    print("[Controller: start() no publica si Lua ausente]")
    _ensure_qapp()

    cc = FakeCanalController()
    ap_client = MagicMock()
    ap_client.is_installed.return_value = False

    ctrl = AutopilotV2Controller(ap_client, cc)
    ctrl.start()
    _check(not ap_client.publish_config.called,
           "publish_config NO llamado si Lua no instalado")
    _check(not ap_client.send_heartbeat.called,
           "send_heartbeat NO llamado si Lua no instalado")
    ctrl.stop()


def test_stop_con_handoff_publica_ultimo_payload():
    print("[Controller: stop(publish_handoff=True) publica ultimo payload]")
    _ensure_qapp()

    cc = FakeCanalController()
    ap_client = MagicMock()
    ap_client.is_installed.return_value = True

    ctrl = AutopilotV2Controller(ap_client, cc)
    ctrl.start()
    before = ap_client.publish_config.call_count
    ctrl.stop(publish_handoff=True)
    after = ap_client.publish_config.call_count
    _check(after == before + 1,
           "stop(publish_handoff=True) agrega exactamente 1 publish mas")


def test_stop_idempotente():
    print("[Controller: stop() dos veces no rompe nada]")
    _ensure_qapp()

    cc = FakeCanalController()
    ap_client = MagicMock()
    ap_client.is_installed.return_value = True

    ctrl = AutopilotV2Controller(ap_client, cc)
    ctrl.start()
    ctrl.stop()
    ctrl.stop()  # no debe lanzar
    _check(True, "stop() idempotente no lanza")


def test_on_canal_status_changed_arma_debouncer():
    print("[Controller: senal canal_status_changed arranca el debouncer]")
    _ensure_qapp()

    cc = FakeCanalController()
    ap_client = MagicMock()
    ap_client.is_installed.return_value = True

    ctrl = AutopilotV2Controller(ap_client, cc)
    ctrl.start()
    ap_client.publish_config.reset_mock()

    # Simular senal — no debe publicar inmediatamente, solo armar debouncer
    ctrl._on_canal_status_changed(1, {"canal_id": 1})
    _check(not ap_client.publish_config.called,
           "senal no publica inmediatamente (va al debouncer)")

    # Forzar el publish sin esperar los 300ms (sin event loop no se dispara solo)
    ctrl._on_debounced_publish()
    _check(ap_client.publish_config.called,
           "publish_config llamado tras disparar debouncer manualmente")

    ctrl.stop()


def test_publish_recupera_de_not_installed():
    print("[Controller: AutopilotV2NotInstalled resetea deteccion]")
    _ensure_qapp()
    from core.autopilot_client import AutopilotV2NotInstalled

    cc = FakeCanalController()
    ap_client = MagicMock()
    ap_client.is_installed.return_value = True
    ap_client.publish_config.side_effect = AutopilotV2NotInstalled("test")

    ctrl = AutopilotV2Controller(ap_client, cc)
    ctrl.start()  # intenta publicar, falla con NotInstalled
    _check(ctrl._script_present is None,
           "_script_present se resetea a None tras NotInstalled")

    # Siguiente ciclo re-detecta
    ap_client.publish_config.side_effect = None
    ap_client.is_installed.reset_mock()
    ctrl._do_publish(bump_version=True)
    _check(ap_client.is_installed.called,
           "re-chequea instalacion en el proximo intento")

    ctrl.stop()


# --------------------------------------------------------------------------
# Tests de sync_from_handoff (Fase E)
# --------------------------------------------------------------------------

def test_canal_sync_from_handoff_happy_path():
    print("[CanalController.sync_from_handoff: happy path]")
    _ensure_qapp()
    from controllers.canal_controller import CanalController

    # Mocks minimos para instanciar
    cc = CanalController(MagicMock(), MagicMock(), MagicMock())
    state = _make_state(7, "canal_x",
                        [(100, 20, 500), (101, 30, 501)],
                        active_index=0, remaining_ms=0)
    cc._rotators[7] = state

    ok = cc.sync_from_handoff(canal_id=7, active_scene_item_id=501,
                               remaining_sec=12)
    _check(ok is True, "sync devuelve True con item valido")
    _check(state.active_index == 1,
           "active_index actualizado al indice del item (501 esta en pos 1)")
    _check(state.timer is not None,
           "timer fue creado por _ensure_timer")
    _check(not state.is_paused, "is_paused=False tras sync")
    _check(state.remaining_ms == 0, "remaining_ms reseteado (ya no pausado)")


def test_canal_sync_from_handoff_canal_no_aplicado():
    print("[CanalController.sync_from_handoff: canal no aplicado -> False]")
    _ensure_qapp()
    from controllers.canal_controller import CanalController
    cc = CanalController(MagicMock(), MagicMock(), MagicMock())
    _check(cc.sync_from_handoff(99, 500, 10) is False,
           "canal sin _RotatorState devuelve False")


def test_canal_sync_from_handoff_item_no_en_playlist():
    print("[CanalController.sync_from_handoff: scene_item_id ajeno -> False]")
    _ensure_qapp()
    from controllers.canal_controller import CanalController
    cc = CanalController(MagicMock(), MagicMock(), MagicMock())
    state = _make_state(7, "canal_x", [(100, 20, 500)])
    cc._rotators[7] = state
    # scene_item_id=999 no esta en item_to_scene_item (500 solo)
    _check(cc.sync_from_handoff(7, 999, 10) is False,
           "scene_item_id ajeno devuelve False")


# test_scene_sync_from_handoff_* ELIMINADOS — SceneController ya no
# tiene rotador tras la unificacion.


def main():
    print("=== AutopilotV2Controller smoke tests ===")
    test_collect_happy_path_2_canales()
    test_collect_filtra_deshabilitados_y_sin_estado()
    test_collect_canal_sin_scene_item_mapping()
    test_collect_handoff_sin_item_activo()
    test_collect_sin_rotadores()
    test_start_publica_config_cuando_lua_instalado()
    test_start_no_publica_si_lua_no_instalado()
    test_stop_con_handoff_publica_ultimo_payload()
    test_stop_idempotente()
    test_on_canal_status_changed_arma_debouncer()
    test_publish_recupera_de_not_installed()
    test_canal_sync_from_handoff_happy_path()
    test_canal_sync_from_handoff_canal_no_aplicado()
    test_canal_sync_from_handoff_item_no_en_playlist()
    # Tests de scene_sync_from_handoff y canal_principal eliminados en
    # la unificacion — el rotador legacy del SceneController ya no existe.
    print("\n=== TODO OK ===")


if __name__ == "__main__":
    main()
