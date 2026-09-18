"""Smoke test headless de AutopilotClient (AUT-2). Sin OBS, sin PyQt.

Usa FakeObsClient con dict interno de sources que simula el buzón. Verifica:
- is_installed True/False según existencia de los sources.
- publish_config incrementa version, escribe JSON válido, aplica handoff.
- send_heartbeat actualiza solo app_heartbeat_at sin tocar playlist.
- read_state parsea correctamente y devuelve None si el JSON es inválido.
- Normalización de fields de la playlist (soporta nombres de v1.7.x).

Uso: venv\\Scripts\\python.exe scripts\\test_autopilot_client.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


class FakeReqClient:
    """Simula el ReqClient de obsws-python: dict interno name → text."""

    def __init__(self, initial_sources: dict[str, str] | None = None):
        self._sources: dict[str, str] = dict(initial_sources or {})
        self.set_calls: list[tuple[str, dict, bool]] = []

    def get_input_settings(self, name: str):
        if name not in self._sources:
            raise RuntimeError(f"input '{name}' does not exist (code 600)")
        return SimpleNamespace(input_settings={"text": self._sources[name]})

    def set_input_settings(self, name: str, settings: dict, overlay: bool):
        # En OBS real, escribir a un source inexistente da error. En el fake
        # lo permitimos porque el script Lua ya creó los sources.
        self._sources[name] = settings.get("text", "")
        self.set_calls.append((name, settings, overlay))


class FakeObsClient:
    def __init__(self, sources: dict[str, str] | None = None):
        self.client = FakeReqClient(sources)


def test_is_installed_false():
    print("\n[is_installed=False cuando no hay sources]")
    from core.autopilot_client import AutopilotClient
    ap = AutopilotClient(FakeObsClient())
    _check(ap.is_installed() is False, "sin sources → is_installed=False")


def test_is_installed_true():
    print("\n[is_installed=True cuando ambos sources existen]")
    from core.autopilot_client import (
        AutopilotClient, CONFIG_SOURCE, STATE_SOURCE,
    )
    ap = AutopilotClient(FakeObsClient({
        CONFIG_SOURCE: "",
        STATE_SOURCE: "{}",
    }))
    _check(ap.is_installed() is True, "ambos sources → is_installed=True")


def test_publish_config_bumps_version():
    print("\n[publish_config incrementa version]")
    from core.autopilot_client import (
        AutopilotClient, CONFIG_SOURCE, STATE_SOURCE,
    )
    fake = FakeObsClient({CONFIG_SOURCE: "", STATE_SOURCE: ""})
    ap = AutopilotClient(fake)

    v1 = ap.publish_config([{"name": "A", "duration_seg": 20}])
    _check(v1 == 1, f"1er publish → version=1 (dio {v1})")

    v2 = ap.publish_config([{"name": "A", "duration_seg": 20}])
    _check(v2 == 2, f"2do publish → version=2 (dio {v2})")

    v3 = ap.publish_config([{"name": "A", "duration_seg": 20}], bump_version=False)
    _check(v3 == 2, f"3er publish con bump_version=False → version=2 (dio {v3})")


def test_publish_config_writes_valid_json():
    print("\n[publish_config escribe JSON válido con el shape esperado]")
    from core.autopilot_client import AutopilotClient, CONFIG_SOURCE

    fake = FakeObsClient({CONFIG_SOURCE: "", "__autopilot_state__": ""})
    ap = AutopilotClient(fake)
    ap.publish_config([
        {"name": "A", "duration_seg": 20},
        {"name": "B", "duration_seg": 15, "active_days": 31,
         "active_time_start": "09:00", "active_time_end": "17:00"},
    ])

    raw = fake.client._sources[CONFIG_SOURCE]
    data = json.loads(raw)
    _check(data["version"] == 1, "version=1")
    _check(len(data["playlist"]) == 2, "playlist tiene 2 items")
    _check(data["playlist"][0]["name"] == "A", "primer item nombre A")
    _check(data["playlist"][1]["active_time_start"] == "09:00", "time_start preservado")
    _check("generated_at" in data and "app_heartbeat_at" in data,
           "generated_at y app_heartbeat_at presentes")


def test_publish_config_normalizes_v1_7_fields():
    """La playlist en v1.7.1 viene de SceneModel con 'nombre_escena' y
    'duracion_segundos' — la app se los pasa así al AutopilotClient, y el
    cliente los traduce al shape del protocolo."""
    print("\n[normalización — nombre_escena → name, duracion_segundos → duration_seg]")
    from core.autopilot_client import AutopilotClient, CONFIG_SOURCE

    fake = FakeObsClient({CONFIG_SOURCE: ""})
    ap = AutopilotClient(fake)
    ap.publish_config([
        {"nombre_escena": "OldScene", "duracion_segundos": 42},
    ])

    data = json.loads(fake.client._sources[CONFIG_SOURCE])
    item = data["playlist"][0]
    _check(item["name"] == "OldScene", "nombre_escena → name")
    _check(item["duration_seg"] == 42, "duracion_segundos → duration_seg")


def test_publish_config_with_handoff():
    print("\n[handoff explícito en publish_config]")
    from core.autopilot_client import AutopilotClient, CONFIG_SOURCE

    fake = FakeObsClient({CONFIG_SOURCE: ""})
    ap = AutopilotClient(fake)
    ap.publish_config(
        [{"name": "A", "duration_seg": 20}],
        handoff={"active_scene": "A", "seconds_remaining": 12},
    )

    data = json.loads(fake.client._sources[CONFIG_SOURCE])
    _check("handoff" in data, "handoff presente")
    _check(data["handoff"]["active_scene"] == "A", "active_scene=A")
    _check(data["handoff"]["seconds_remaining"] == 12, "seconds_remaining=12")


def test_send_heartbeat_only_updates_timestamp():
    print("\n[send_heartbeat actualiza solo app_heartbeat_at]")
    from core.autopilot_client import AutopilotClient, CONFIG_SOURCE

    fake = FakeObsClient({CONFIG_SOURCE: ""})
    ap = AutopilotClient(fake)
    ap.publish_config([{"name": "A", "duration_seg": 20}])
    original = json.loads(fake.client._sources[CONFIG_SOURCE])
    original_ts = original["app_heartbeat_at"]
    original_version = original["version"]
    original_playlist = original["playlist"]

    # Modificar el timestamp para poder verificar cambio
    import time
    time.sleep(1.1)  # asegurar que el ISO cambie a los segundos

    ok = ap.send_heartbeat()
    _check(ok is True, "send_heartbeat exitoso")

    updated = json.loads(fake.client._sources[CONFIG_SOURCE])
    _check(updated["app_heartbeat_at"] != original_ts,
           "app_heartbeat_at cambió")
    _check(updated["version"] == original_version,
           "version NO cambió (bump_version=False implícito)")
    _check(updated["playlist"] == original_playlist,
           "playlist intacta")


def test_send_heartbeat_returns_false_if_no_config():
    print("\n[send_heartbeat sin config previa → False]")
    from core.autopilot_client import AutopilotClient, CONFIG_SOURCE

    fake = FakeObsClient({CONFIG_SOURCE: ""})
    ap = AutopilotClient(fake)
    _check(ap.send_heartbeat() is False,
           "heartbeat sin publish previo → False")


def test_read_state_parses_json():
    print("\n[read_state parsea JSON válido]")
    from core.autopilot_client import AutopilotClient, STATE_SOURCE

    state_json = json.dumps({
        "script_version": "1.0.0",
        "mode": "active",
        "active_scene": "TestScene",
        "seconds_remaining": 15,
    })
    fake = FakeObsClient({STATE_SOURCE: state_json})
    ap = AutopilotClient(fake)
    state = ap.read_state()
    _check(state is not None, "state parseado")
    _check(state["mode"] == "active", "mode=active")
    _check(state["active_scene"] == "TestScene", "active_scene extraído")
    _check(state["seconds_remaining"] == 15, "seconds_remaining=15")


def test_read_state_none_if_missing():
    print("\n[read_state=None si el source no existe]")
    from core.autopilot_client import AutopilotClient
    ap = AutopilotClient(FakeObsClient())
    _check(ap.read_state() is None, "sin source → None")


def test_read_state_none_if_invalid_json():
    print("\n[read_state=None si el contenido no es JSON válido]")
    from core.autopilot_client import AutopilotClient, STATE_SOURCE
    fake = FakeObsClient({STATE_SOURCE: "not-valid-json{{"})
    ap = AutopilotClient(fake)
    _check(ap.read_state() is None, "JSON malformado → None")


def test_publish_raises_if_not_connected():
    print("\n[publish_config raises AutopilotNotInstalled si no hay conexión]")
    from core.autopilot_client import AutopilotClient, AutopilotNotInstalled

    class NoConn:
        client = None
    ap = AutopilotClient(NoConn())
    try:
        ap.publish_config([{"name": "A", "duration_seg": 20}])
        _check(False, "esperaba AutopilotNotInstalled")
    except AutopilotNotInstalled:
        _check(True, "AutopilotNotInstalled lanzado correctamente")


def test_script_version_from_state():
    print("\n[script_version leído del state]")
    from core.autopilot_client import AutopilotClient, STATE_SOURCE
    fake = FakeObsClient({
        STATE_SOURCE: json.dumps({"script_version": "1.2.3", "mode": "standby"})
    })
    ap = AutopilotClient(fake)
    _check(ap.script_version() == "1.2.3", "script_version='1.2.3'")


def main():
    test_is_installed_false()
    test_is_installed_true()
    test_publish_config_bumps_version()
    test_publish_config_writes_valid_json()
    test_publish_config_normalizes_v1_7_fields()
    test_publish_config_with_handoff()
    test_send_heartbeat_only_updates_timestamp()
    test_send_heartbeat_returns_false_if_no_config()
    test_read_state_parses_json()
    test_read_state_none_if_missing()
    test_read_state_none_if_invalid_json()
    test_publish_raises_if_not_connected()
    test_script_version_from_state()
    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
