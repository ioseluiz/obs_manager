"""Smoke test headless de AutopilotClientV2 — mocks de OBS, sin red.

Se ejerce la serializacion del protocolo v2 (canales[] con los dos modos
de rotacion), el round-trip con el buzon, la monotonicidad de version,
las validaciones de shape, y la lectura del state. No requiere OBS vivo
ni script Lua instalado.

Uso::

    python scripts/test_autopilot_client_v2.py

Exit code 0 si todos los checks pasan, 1 en la primera falla.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Project root en sys.path (igual que los demas tests del repo).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.autopilot_client import (  # noqa: E402
    CONFIG_SOURCE_V2,
    MODE_PROGRAM_GLOBAL,
    MODE_SCENE_ITEMS,
    PROTOCOL_VERSION,
    STATE_SOURCE_V2,
    AutopilotClientV2,
    AutopilotV2NotInstalled,
)


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


def _make_mock_obs(initial_texts: dict[str, str] | None = None):
    """Crea un mock de OBSClient con un buzon en memoria para los dos
    text sources v2.

    `get_input_settings(name)` devuelve `.input_settings = {"text": ...}`.
    `set_input_settings(name, settings, overlay)` pisa el texto.
    """
    storage = dict(initial_texts or {})

    def _get(name):
        resp = MagicMock()
        resp.input_settings = {"text": storage.get(name, "")}
        return resp

    def _set(name, settings, overlay):  # noqa: ARG001
        storage[name] = settings.get("text", "")

    client = MagicMock()
    client.get_input_settings.side_effect = _get
    client.set_input_settings.side_effect = _set

    obs = MagicMock()
    obs.client = client
    return obs, storage


def test_publish_config_un_canal_scene_items():
    print("[publish_config: 1 canal scene_items]")
    obs, storage = _make_mock_obs()
    ap = AutopilotClientV2(obs)

    canales = [{
        "canal_id": 3,
        "modo_rotacion": "scene_items",
        "scene_name": "canal_721",
        "filter_name": "udp_out",
        "playlist": [
            {"name": "Item A", "scene_item_id": 7, "duration_seg": 30},
            {"name": "Item B", "scene_item_id": 9, "duration_seg": 45},
        ],
    }]
    version = ap.publish_config(canales)

    _check(version == 1, "version inicial = 1")
    _check(CONFIG_SOURCE_V2 in storage, "escrito en buzon v2")
    payload = json.loads(storage[CONFIG_SOURCE_V2])
    _check(payload["protocol_version"] == PROTOCOL_VERSION, "protocol_version = 2")
    _check(payload["version"] == 1, "payload version coincide")
    _check(len(payload["canales"]) == 1, "1 canal en payload")
    c = payload["canales"][0]
    _check(c["canal_id"] == 3, "canal_id preservado")
    _check(c["modo_rotacion"] == MODE_SCENE_ITEMS, "modo preservado")
    _check(c["scene_name"] == "canal_721", "scene_name preservado")
    _check(c["filter_name"] == "udp_out", "filter_name preservado")
    _check(len(c["playlist"]) == 2, "playlist tamano correcto")
    _check(c["playlist"][0]["scene_item_id"] == 7, "scene_item_id preservado")
    _check(c["playlist"][0]["duration_seg"] == 30, "duration_seg preservado")
    _check(c["playlist"][0]["active_days"] == 127, "active_days default = 127")


def test_publish_config_canal_principal_program_global():
    print("[publish_config: Canal Principal program_global]")
    obs, storage = _make_mock_obs()
    ap = AutopilotClientV2(obs)

    canales = [{
        "canal_id": -1,
        "modo_rotacion": "program_global",
        "playlist": [
            {"name": "Bienvenida", "duration_seg": 20},
            {"name": "Menu", "duration_seg": 15,
             "active_time_start": "11:30", "active_time_end": "13:30"},
        ],
    }]
    ap.publish_config(canales)
    payload = json.loads(storage[CONFIG_SOURCE_V2])
    c = payload["canales"][0]

    _check(c["canal_id"] == -1, "canal_id -1 (Principal)")
    _check(c["modo_rotacion"] == MODE_PROGRAM_GLOBAL, "modo program_global")
    _check("scene_name" not in c, "no scene_name en program_global")
    _check("filter_name" not in c, "no filter_name en program_global")
    _check("scene_item_id" not in c["playlist"][0],
           "no scene_item_id en items de program_global")
    _check(c["playlist"][1]["active_time_start"] == "11:30",
           "ventana horaria preservada")


def test_publish_config_mezcla_de_canales():
    print("[publish_config: Canal Principal + 2 canales multi-salida]")
    obs, storage = _make_mock_obs()
    ap = AutopilotClientV2(obs)

    canales = [
        {"canal_id": -1, "modo_rotacion": "program_global",
         "playlist": [{"name": "A", "duration_seg": 10}]},
        {"canal_id": 1, "modo_rotacion": "scene_items",
         "scene_name": "sc1", "filter_name": "udp_out",
         "playlist": [{"name": "A1", "scene_item_id": 1, "duration_seg": 10}]},
        {"canal_id": 2, "modo_rotacion": "scene_items",
         "scene_name": "sc2", "filter_name": "udp_out",
         "playlist": [{"name": "B1", "scene_item_id": 2, "duration_seg": 20}]},
    ]
    ap.publish_config(canales)
    payload = json.loads(storage[CONFIG_SOURCE_V2])

    _check(len(payload["canales"]) == 3, "3 canales serializados")
    ids = [c["canal_id"] for c in payload["canales"]]
    _check(ids == [-1, 1, 2], "orden preservado")


def test_publish_config_version_monotonica():
    print("[publish_config: version monotonica]")
    obs, storage = _make_mock_obs()
    ap = AutopilotClientV2(obs)
    minimo = [{"canal_id": 1, "modo_rotacion": "scene_items",
               "scene_name": "s", "playlist": []}]

    v1 = ap.publish_config(minimo)
    v2 = ap.publish_config(minimo)
    v3 = ap.publish_config(minimo)
    _check(v1 == 1 and v2 == 2 and v3 == 3, "version incrementa en cada publish")

    v3_bis = ap.publish_config(minimo, bump_version=False)
    _check(v3_bis == 3, "bump_version=False mantiene version")


def test_publish_config_canales_vacio():
    print("[publish_config: canales vacio]")
    obs, storage = _make_mock_obs()
    ap = AutopilotClientV2(obs)
    v = ap.publish_config([])
    payload = json.loads(storage[CONFIG_SOURCE_V2])
    _check(v == 1, "version = 1 incluso con canales vacio")
    _check(payload["canales"] == [], "canales vacio preservado")


def test_publish_config_validaciones():
    print("[publish_config: validaciones de shape]")
    obs, _ = _make_mock_obs()
    ap = AutopilotClientV2(obs)

    def _raises(fn, exc_type, label):
        try:
            fn()
            _check(False, f"{label} — no lanzo {exc_type.__name__}")
        except exc_type:
            _check(True, f"{label} lanza {exc_type.__name__}")

    _raises(lambda: ap.publish_config("no es lista"), ValueError,
            "canales no-lista")
    _raises(lambda: ap.publish_config([{}]), ValueError,
            "canal sin canal_id")
    _raises(lambda: ap.publish_config([{"canal_id": 1}]), ValueError,
            "canal sin modo_rotacion")
    _raises(lambda: ap.publish_config(
        [{"canal_id": 1, "modo_rotacion": "turbo"}]),
            ValueError, "modo_rotacion desconocido")
    _raises(lambda: ap.publish_config(
        [{"canal_id": 1, "modo_rotacion": "scene_items"}]),
            ValueError, "scene_items sin scene_name")


def test_publish_config_handoff_filtrado():
    print("[publish_config: handoff vacio/invalido se omite]")
    obs, storage = _make_mock_obs()
    ap = AutopilotClientV2(obs)

    # Handoff con seconds_remaining=0 → se omite (fix bug C v1)
    canales = [{
        "canal_id": -1, "modo_rotacion": "program_global",
        "playlist": [{"name": "A", "duration_seg": 10}],
        "handoff": {"active_scene": "A", "seconds_remaining": 0},
    }]
    ap.publish_config(canales)
    c = json.loads(storage[CONFIG_SOURCE_V2])["canales"][0]
    _check("handoff" not in c, "handoff con seconds=0 omitido")

    # Handoff con active_scene vacio en program_global → se omite
    canales = [{
        "canal_id": -1, "modo_rotacion": "program_global",
        "playlist": [{"name": "A", "duration_seg": 10}],
        "handoff": {"active_scene": "", "seconds_remaining": 5},
    }]
    ap.publish_config(canales)
    c = json.loads(storage[CONFIG_SOURCE_V2])["canales"][0]
    _check("handoff" not in c, "handoff con active_scene vacio omitido")

    # Handoff con active_index=0 en scene_items → se omite
    canales = [{
        "canal_id": 3, "modo_rotacion": "scene_items",
        "scene_name": "sc", "playlist": [],
        "handoff": {"active_index": 0, "seconds_remaining": 5},
    }]
    ap.publish_config(canales)
    c = json.loads(storage[CONFIG_SOURCE_V2])["canales"][0]
    _check("handoff" not in c, "handoff con active_index=0 omitido")

    # Handoff valido → se preserva
    canales = [{
        "canal_id": 3, "modo_rotacion": "scene_items",
        "scene_name": "sc", "playlist": [],
        "handoff": {"active_index": 2, "seconds_remaining": 15},
    }]
    ap.publish_config(canales)
    c = json.loads(storage[CONFIG_SOURCE_V2])["canales"][0]
    _check(c.get("handoff", {}).get("active_index") == 2,
           "handoff valido en scene_items se preserva")


def test_send_heartbeat_round_trip():
    print("[send_heartbeat: round-trip]")
    obs, storage = _make_mock_obs()
    ap = AutopilotClientV2(obs)

    minimo = [{"canal_id": 1, "modo_rotacion": "scene_items",
               "scene_name": "s", "playlist": []}]
    ap.publish_config(minimo)
    v_before = json.loads(storage[CONFIG_SOURCE_V2])["version"]

    ok = ap.send_heartbeat()
    _check(ok is True, "heartbeat devuelve True")
    data = json.loads(storage[CONFIG_SOURCE_V2])
    _check(data["version"] == v_before,
           "heartbeat no cambia version (solo app_heartbeat_at)")


def test_send_heartbeat_sin_config_previa():
    print("[send_heartbeat: sin config previa]")
    obs, _ = _make_mock_obs()
    ap = AutopilotClientV2(obs)
    _check(ap.send_heartbeat() is False, "heartbeat False si no hay config")


def test_read_state_y_read_canal_state():
    print("[read_state + read_canal_state]")
    state = {
        "script_version": "2.0.0",
        "protocol_version": 2,
        "mode": "active",
        "canales": [
            {"canal_id": -1, "modo_rotacion": "program_global",
             "active_scene": "A", "active_index": 1, "seconds_remaining": 5},
            {"canal_id": 3, "modo_rotacion": "scene_items",
             "scene_name": "sc", "active_scene_item_id": 7,
             "active_index": 2, "seconds_remaining": 20},
        ],
        "updated_at": "2026-10-20T14:30:00Z",
    }
    obs, _ = _make_mock_obs({STATE_SOURCE_V2: json.dumps(state)})
    ap = AutopilotClientV2(obs)

    read = ap.read_state()
    _check(read is not None, "read_state devuelve dict")
    _check(read["mode"] == "active", "mode presente")
    _check(len(read["canales"]) == 2, "canales presentes")

    cp = ap.read_canal_state(-1)
    _check(cp is not None and cp["active_scene"] == "A",
           "read_canal_state(-1) encuentra Canal Principal")
    c3 = ap.read_canal_state(3)
    _check(c3 is not None and c3["active_scene_item_id"] == 7,
           "read_canal_state(3) encuentra canal multi-salida")
    c99 = ap.read_canal_state(99)
    _check(c99 is None, "read_canal_state de canal inexistente = None")


def test_read_state_sin_json():
    print("[read_state: contenido invalido]")
    obs, _ = _make_mock_obs({STATE_SOURCE_V2: "no es json"})
    ap = AutopilotClientV2(obs)
    _check(ap.read_state() is None, "read_state None si JSON invalido")

    obs2, _ = _make_mock_obs({STATE_SOURCE_V2: ""})
    ap2 = AutopilotClientV2(obs2)
    _check(ap2.read_state() is None, "read_state None si text vacio")


def test_is_installed():
    print("[is_installed]")
    # Caso 1: ambos buzones existen (storage inicial no vacio seria
    # ambiguo con "existen pero vacios" — basta con que get no lance)
    obs_ok, _ = _make_mock_obs({
        CONFIG_SOURCE_V2: "",
        STATE_SOURCE_V2: "",
    })
    ap_ok = AutopilotClientV2(obs_ok)
    _check(ap_ok.is_installed() is True, "is_installed True si ambos buzones existen")

    # Caso 2: get_input_settings lanza → no instalado
    obs_fail = MagicMock()
    obs_fail.client.get_input_settings.side_effect = RuntimeError("no source")
    ap_fail = AutopilotClientV2(obs_fail)
    _check(ap_fail.is_installed() is False, "is_installed False si source no existe")

    # Caso 3: OBS no conectado (obs.client = None) → es_installed False
    obs_none = MagicMock()
    obs_none.client = None
    ap_none = AutopilotClientV2(obs_none)
    _check(ap_none.is_installed() is False, "is_installed False si OBS no conectado")


def test_publish_sin_obs_conectado():
    print("[publish_config sin OBS conectado]")
    obs = MagicMock()
    obs.client = None
    ap = AutopilotClientV2(obs)
    try:
        ap.publish_config([])
        _check(False, "publish sin OBS no lanzo")
    except AutopilotV2NotInstalled:
        _check(True, "publish sin OBS lanza AutopilotV2NotInstalled")


def main():
    print("=== AutopilotClientV2 smoke tests ===")
    test_publish_config_un_canal_scene_items()
    test_publish_config_canal_principal_program_global()
    test_publish_config_mezcla_de_canales()
    test_publish_config_version_monotonica()
    test_publish_config_canales_vacio()
    test_publish_config_validaciones()
    test_publish_config_handoff_filtrado()
    test_send_heartbeat_round_trip()
    test_send_heartbeat_sin_config_previa()
    test_read_state_y_read_canal_state()
    test_read_state_sin_json()
    test_is_installed()
    test_publish_sin_obs_conectado()
    print("\n=== TODO OK ===")


if __name__ == "__main__":
    main()
