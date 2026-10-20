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
    CANAL_ID_PRINCIPAL,
    AutopilotV2Controller,
    collect_canales_payload,
)
from controllers.canal_controller import _PlaylistEntry, _RotatorState  # noqa: E402
from core.autopilot_client import MODE_PROGRAM_GLOBAL, MODE_SCENE_ITEMS  # noqa: E402


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


class FakeSceneController:
    """Doble headless del SceneController real.

    Expone solo lo que `_collect_canal_principal_entry` consume + el
    callback registration que `AutopilotV2Controller` usa.
    """
    def __init__(self, scenes_list=None, active_scene_name="",
                 time_left=0, timer_active=False, is_paused=False):
        self.scenes_list = scenes_list or []
        self.active_scene_name = active_scene_name
        self.time_left = time_left
        self.is_paused = is_paused
        self.timer = MagicMock()
        self.timer.isActive.return_value = timer_active
        self._cbs = []

    def register_on_rotator_change(self, cb):
        self._cbs.append(cb)

    def _notify(self):
        for cb in self._cbs:
            cb()


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
# Tests de Canal Principal (Fase D)
# --------------------------------------------------------------------------

def test_collect_canal_principal_rotando():
    print("[collect: Canal Principal con rotador corriendo]")
    cc = FakeCanalController()
    sc = FakeSceneController(
        scenes_list=[
            {"name": "Bienvenida", "duration": 10, "active_days": 127,
             "active_time_start": None, "active_time_end": None},
            {"name": "Menu", "duration": 15, "active_days": 31,
             "active_time_start": "11:30", "active_time_end": "13:30"},
        ],
        active_scene_name="Bienvenida",
        time_left=7,
        timer_active=True,
    )
    canales = collect_canales_payload(cc, scene_controller=sc)
    _check(len(canales) == 1, "1 entry en payload")
    cp = canales[0]
    _check(cp["canal_id"] == CANAL_ID_PRINCIPAL, "canal_id = -1 (Principal)")
    _check(cp["modo_rotacion"] == MODE_PROGRAM_GLOBAL,
           "modo program_global")
    _check("scene_name" not in cp, "no scene_name en program_global")
    _check("filter_name" not in cp, "no filter_name en program_global")
    _check(len(cp["playlist"]) == 2, "playlist tiene las 2 escenas")
    _check(cp["playlist"][0]["name"] == "Bienvenida", "primer item nombre")
    _check(cp["playlist"][0]["duration_seg"] == 10, "primer item duration")
    _check(cp["playlist"][1]["active_time_start"] == "11:30",
           "ventana horaria preservada")
    _check(cp["handoff"]["active_scene"] == "Bienvenida",
           "handoff active_scene correcto")
    _check(cp["handoff"]["seconds_remaining"] == 7,
           "handoff seconds_remaining correcto")


def test_collect_canal_principal_pausado():
    print("[collect: Canal Principal pausado tambien se incluye]")
    cc = FakeCanalController()
    sc = FakeSceneController(
        scenes_list=[{"name": "A", "duration": 10}],
        active_scene_name="A", time_left=5,
        timer_active=False, is_paused=True,
    )
    canales = collect_canales_payload(cc, scene_controller=sc)
    _check(len(canales) == 1, "pausado publica igual (el Lua retoma si cae)")
    _check(canales[0]["handoff"]["seconds_remaining"] == 5,
           "handoff conserva time_left pausado")


def test_collect_canal_principal_detenido_no_se_incluye():
    print("[collect: Canal Principal detenido se omite]")
    cc = FakeCanalController()
    sc = FakeSceneController(
        scenes_list=[{"name": "A", "duration": 10}],
        timer_active=False, is_paused=False,
    )
    canales = collect_canales_payload(cc, scene_controller=sc)
    _check(canales == [], "detenido no publica Canal Principal")


def test_collect_canal_principal_sin_escenas_no_se_incluye():
    print("[collect: Canal Principal con scenes_list vacia se omite]")
    cc = FakeCanalController()
    sc = FakeSceneController(scenes_list=[], timer_active=True)
    canales = collect_canales_payload(cc, scene_controller=sc)
    _check(canales == [], "sin escenas no publica Canal Principal")


def test_collect_principal_junto_con_multisalida():
    print("[collect: Canal Principal + 2 canales multi-salida mezclados]")
    cc = FakeCanalController()
    cc._rotators[3] = _make_state(3, "canal_3", [(30, 10, 300)],
                                   active_index=0, remaining_ms=4000)
    cc._rotators[4] = _make_state(4, "canal_4", [(40, 20, 400)],
                                   active_index=0, remaining_ms=18000)
    cc.canal_model.get_canal.side_effect = lambda cid: {
        3: {"nombre": "canal_3", "habilitado": True},
        4: {"nombre": "canal_4", "habilitado": True},
    }.get(cid)
    cc.canal_model.get_items.side_effect = lambda cid: {
        3: [{"id": 30, "secuencia_id": 300}],
        4: [{"id": 40, "secuencia_id": 400}],
    }.get(cid, [])
    cc.scene_model.get_scene.side_effect = lambda sid: {
        300: {"name": "E3"}, 400: {"name": "E4"},
    }.get(sid)
    cc.set_status(3, active_index=0, remaining_ms=4000)
    cc.set_status(4, active_index=0, remaining_ms=18000)

    sc = FakeSceneController(
        scenes_list=[{"name": "Global", "duration": 10}],
        active_scene_name="Global", time_left=3,
        timer_active=True,
    )
    canales = collect_canales_payload(cc, scene_controller=sc)
    _check(len(canales) == 3,
           "3 entradas: Canal Principal + canal 3 + canal 4")
    _check(canales[0]["canal_id"] == CANAL_ID_PRINCIPAL,
           "Canal Principal publicado primero (convencion)")
    ids = sorted(c["canal_id"] for c in canales)
    _check(ids == [-1, 3, 4], "ids esperados")


def test_scene_controller_callback_se_registra():
    print("[Controller: AutopilotV2Controller registra callback en SceneController]")
    _ensure_qapp()

    cc = FakeCanalController()
    sc = FakeSceneController(timer_active=False)
    ap_client = MagicMock()
    ap_client.is_installed.return_value = True

    ctrl = AutopilotV2Controller(ap_client, cc, scene_controller=sc)
    _check(len(sc._cbs) == 1,
           "AutopilotV2Controller registro 1 callback en el SceneController")
    _check(sc._cbs[0] == ctrl.request_publish,
           "callback es request_publish del AutopilotV2Controller")

    ctrl.start()
    ap_client.publish_config.reset_mock()
    # Simular que el SceneController rotó
    sc._notify()
    _check(not ap_client.publish_config.called,
           "notify no publica inmediatamente (va al debouncer)")
    ctrl._on_debounced_publish()
    _check(ap_client.publish_config.called,
           "publish tras disparar debouncer")
    ctrl.stop()


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


def test_scene_sync_from_handoff_happy_path():
    print("[SceneController.sync_from_handoff: happy path]")
    _ensure_qapp()
    from controllers.scene_controller import SceneController
    # Construimos SceneController real pero con view/model/obs/settings/cal
    # mockeados — las lineas de sync_from_handoff solo tocan atributos
    # internos + metodos del view (que son MagicMock).
    view = MagicMock()
    sc = SceneController(view, MagicMock(), MagicMock(), MagicMock(),
                          MagicMock())
    sc.scenes_list = [
        {"name": "A"}, {"name": "B"}, {"name": "C"},
    ]
    ok = sc.sync_from_handoff(active_scene_name="B", remaining_sec=8)
    _check(ok is True, "sync devuelve True con escena valida")
    _check(sc.active_scene_name == "B", "active_scene_name actualizado")
    _check(sc.time_left == 8, "time_left actualizado")
    _check(sc.current_index == 2,
           "current_index apunta al siguiente a mostrar (B esta en pos 1)")
    _check(not sc.is_paused, "is_paused=False tras sync")
    # view.set_rotator_state y highlight_active_scene fueron llamados
    view.set_rotator_state.assert_called_with("running")
    view.highlight_active_scene.assert_called_with("B")
    _check(True, "view.set_rotator_state('running') y highlight llamados")


def test_scene_sync_from_handoff_escena_ajena():
    print("[SceneController.sync_from_handoff: escena no en lista -> False]")
    _ensure_qapp()
    from controllers.scene_controller import SceneController
    view = MagicMock()
    sc = SceneController(view, MagicMock(), MagicMock(), MagicMock(),
                          MagicMock())
    sc.scenes_list = [{"name": "A"}]
    _check(sc.sync_from_handoff("B", 8) is False,
           "escena ajena a scenes_list devuelve False")


def test_scene_sync_from_handoff_sin_scenes():
    print("[SceneController.sync_from_handoff: scenes_list vacia -> False]")
    _ensure_qapp()
    from controllers.scene_controller import SceneController
    view = MagicMock()
    sc = SceneController(view, MagicMock(), MagicMock(), MagicMock(),
                          MagicMock())
    sc.scenes_list = []
    _check(sc.sync_from_handoff("A", 8) is False,
           "scenes_list vacia devuelve False")


def main():
    print("=== AutopilotV2Controller smoke tests ===")
    test_collect_happy_path_2_canales()
    test_collect_filtra_deshabilitados_y_sin_estado()
    test_collect_canal_sin_scene_item_mapping()
    test_collect_handoff_sin_item_activo()
    test_collect_sin_rotadores()
    test_collect_canal_principal_rotando()
    test_collect_canal_principal_pausado()
    test_collect_canal_principal_detenido_no_se_incluye()
    test_collect_canal_principal_sin_escenas_no_se_incluye()
    test_collect_principal_junto_con_multisalida()
    test_start_publica_config_cuando_lua_instalado()
    test_start_no_publica_si_lua_no_instalado()
    test_stop_con_handoff_publica_ultimo_payload()
    test_stop_idempotente()
    test_on_canal_status_changed_arma_debouncer()
    test_publish_recupera_de_not_installed()
    test_scene_controller_callback_se_registra()
    test_canal_sync_from_handoff_happy_path()
    test_canal_sync_from_handoff_canal_no_aplicado()
    test_canal_sync_from_handoff_item_no_en_playlist()
    test_scene_sync_from_handoff_happy_path()
    test_scene_sync_from_handoff_escena_ajena()
    test_scene_sync_from_handoff_sin_scenes()
    print("\n=== TODO OK ===")


if __name__ == "__main__":
    main()
