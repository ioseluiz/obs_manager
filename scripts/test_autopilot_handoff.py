"""Smoke test del handoff / sync entre SceneController y Autopilot (AUT-4).

Verifica que la lógica de integración (sin PyQt UI real) llama a los métodos
correctos del AutopilotClient y publica los payloads esperados.

Uso: venv\\Scripts\\python.exe scripts\\test_autopilot_handoff.py
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
    """Simula el ReqClient de OBS: set/get sobre input inexistente falla."""
    def __init__(self, sources=None):
        self._sources = dict(sources or {})
    def get_input_settings(self, name):
        if name not in self._sources:
            raise RuntimeError(f"input {name} does not exist")
        return SimpleNamespace(input_settings={"text": self._sources[name]})
    def set_input_settings(self, name, settings, overlay):
        # En OBS real, SetInputSettings sobre un input inexistente devuelve
        # code 600. Simularlo aquí para que los tests reflejen el comportamiento
        # real cuando el script Autopilot no está cargado.
        if name not in self._sources:
            raise RuntimeError(f"input {name} does not exist (code 600)")
        self._sources[name] = settings.get("text", "")


class FakeObsClient:
    def __init__(self, sources=None):
        self.client = FakeReqClient(sources)
        self.canvas_width = 1920
        self.canvas_height = 1080


class MinimalSceneController:
    """Reproduce solo lo necesario de SceneController para probar el mixin.

    Los métodos del mixin son puros — no dependen de PyQt más allá del
    hecho de que existen scenes_list, active_scene_name, time_left y
    obs_client.
    """
    def __init__(self, obs_client):
        from core.autopilot_client import AutopilotClient
        self.obs_client = obs_client
        self.autopilot = AutopilotClient(obs_client)
        self.scenes_list = []
        self.active_scene_name = ""
        self.time_left = 0

    # Copiar los métodos del mixin del SceneController real para poder
    # testear la lógica sin instanciar la clase completa (que arrastra
    # QTimer, views, etc.).
    from controllers.scene_controller import SceneController
    _build_autopilot_playlist = SceneController._build_autopilot_playlist
    sync_playlist_to_autopilot = SceneController.sync_playlist_to_autopilot
    publish_handoff_to_autopilot = SceneController.publish_handoff_to_autopilot
    sync_from_autopilot = SceneController.sync_from_autopilot


def test_build_playlist():
    print("\n[_build_autopilot_playlist traduce shape de v1.7.x]")
    from core.autopilot_client import CONFIG_SOURCE
    fake = FakeObsClient({CONFIG_SOURCE: ""})
    sc = MinimalSceneController(fake)

    # Simular scenes_list como lo devuelve SceneModel en v1.7.x
    sc.scenes_list = [
        {"id": 1, "name": "Bienvenida", "duration": 20,
         "active_days": 127, "active_time_start": "", "active_time_end": ""},
        {"id": 2, "name": "Menú", "duration": 15,
         "active_days": 31, "active_time_start": "11:30", "active_time_end": "13:30"},
    ]
    playlist = sc._build_autopilot_playlist()
    _check(len(playlist) == 2, "2 items")
    _check(playlist[0]["name"] == "Bienvenida", "primer nombre")
    _check(playlist[0]["duration_seg"] == 20, "duracion 20s")
    _check(playlist[1]["active_time_start"] == "11:30", "time_start preservado")


def test_sync_publishes_to_autopilot():
    print("\n[sync_playlist_to_autopilot escribe al text source]")
    from core.autopilot_client import CONFIG_SOURCE
    fake = FakeObsClient({CONFIG_SOURCE: ""})
    sc = MinimalSceneController(fake)
    sc.scenes_list = [
        {"id": 1, "name": "A", "duration": 10, "active_days": 127},
    ]
    ok = sc.sync_playlist_to_autopilot()
    _check(ok is True, "sync devolvió True")

    raw = fake.client._sources[CONFIG_SOURCE]
    data = json.loads(raw)
    _check(data["version"] == 1, "version=1 en la config publicada")
    _check(len(data["playlist"]) == 1, "playlist con 1 item")
    _check(data["playlist"][0]["name"] == "A", "nombre correcto")


def test_publish_handoff():
    print("\n[publish_handoff_to_autopilot incluye active_scene y remaining]")
    from core.autopilot_client import CONFIG_SOURCE
    fake = FakeObsClient({CONFIG_SOURCE: ""})
    sc = MinimalSceneController(fake)
    sc.scenes_list = [
        {"id": 1, "name": "A", "duration": 20, "active_days": 127},
        {"id": 2, "name": "B", "duration": 15, "active_days": 127},
    ]
    sc.active_scene_name = "B"
    sc.time_left = 8

    ok = sc.publish_handoff_to_autopilot()
    _check(ok is True, "handoff exitoso")

    raw = fake.client._sources[CONFIG_SOURCE]
    data = json.loads(raw)
    _check("handoff" in data, "handoff en el config publicado")
    _check(data["handoff"]["active_scene"] == "B", "handoff.active_scene=B")
    _check(data["handoff"]["seconds_remaining"] == 8, "seconds_remaining=8")


def test_sync_from_autopilot_active():
    print("\n[sync_from_autopilot con mode=active aplica el estado]")
    from core.autopilot_client import STATE_SOURCE
    state = json.dumps({
        "script_version": "1.0.0",
        "mode": "active",
        "active_scene": "TestActive",
        "seconds_remaining": 12,
    })
    fake = FakeObsClient({STATE_SOURCE: state})
    sc = MinimalSceneController(fake)
    ok = sc.sync_from_autopilot()
    _check(ok is True, "sync devolvió True")
    _check(sc.active_scene_name == "TestActive", "active_scene_name sincronizado")
    _check(sc.time_left == 12, "time_left sincronizado")


def test_sync_from_autopilot_standby():
    print("\n[sync_from_autopilot con mode=standby NO cambia estado local]")
    from core.autopilot_client import STATE_SOURCE
    state = json.dumps({
        "script_version": "1.0.0",
        "mode": "standby",
        "active_scene": "IgnoreMe",
        "seconds_remaining": 99,
    })
    fake = FakeObsClient({STATE_SOURCE: state})
    sc = MinimalSceneController(fake)
    sc.active_scene_name = "OriginalScene"
    sc.time_left = 5

    ok = sc.sync_from_autopilot()
    _check(ok is False, "sync devolvió False (standby)")
    _check(sc.active_scene_name == "OriginalScene", "estado local intacto")
    _check(sc.time_left == 5, "time_left local intacto")


def test_sync_silent_if_not_installed():
    print("\n[sync/handoff silencioso si el script no está instalado]")
    fake = FakeObsClient()  # sin sources → is_installed=False
    sc = MinimalSceneController(fake)
    sc.scenes_list = [{"id": 1, "name": "A", "duration": 10}]
    sc.active_scene_name = "A"
    sc.time_left = 5

    _check(sc.sync_playlist_to_autopilot() is False,
           "sync sin script → False (silencioso)")
    _check(sc.publish_handoff_to_autopilot() is False,
           "handoff sin script → False (silencioso)")
    _check(sc.sync_from_autopilot() is False,
           "sync_from sin script → False (silencioso)")


def test_no_publish_if_playlist_empty():
    print("\n[publish_handoff con playlist vacía no publica]")
    from core.autopilot_client import CONFIG_SOURCE
    fake = FakeObsClient({CONFIG_SOURCE: ""})
    sc = MinimalSceneController(fake)
    sc.scenes_list = []  # vacía
    sc.active_scene_name = "X"
    sc.time_left = 10

    ok = sc.publish_handoff_to_autopilot()
    _check(ok is False, "sin playlist no se publica handoff")


def test_publish_without_active_scene_omits_handoff():
    """Al cerrar la app sin haber iniciado el rotador, active_scene_name
    está vacío. En ese caso la config se publica sin bloque handoff — el
    script arranca desde el primer item cuando el heartbeat expire."""
    print("\n[publish_handoff sin active_scene NO incluye handoff]")
    from core.autopilot_client import CONFIG_SOURCE
    fake = FakeObsClient({CONFIG_SOURCE: ""})
    sc = MinimalSceneController(fake)
    sc.scenes_list = [
        {"id": 1, "name": "A", "duration": 10, "active_days": 127},
    ]
    sc.active_scene_name = ""  # rotador nunca inició
    sc.time_left = 0

    ok = sc.publish_handoff_to_autopilot()
    _check(ok is True, "publica igual, aunque sin handoff")

    raw = fake.client._sources[CONFIG_SOURCE]
    data = json.loads(raw)
    _check("handoff" not in data,
           "config publicada NO incluye bloque handoff")
    _check(len(data["playlist"]) == 1, "playlist sí se publica")

    # Mismo test con seconds_remaining=0 pero active_scene definida
    sc.active_scene_name = "A"
    sc.time_left = 0
    fake.client._sources[CONFIG_SOURCE] = ""
    ok = sc.publish_handoff_to_autopilot()
    data = json.loads(fake.client._sources[CONFIG_SOURCE])
    _check("handoff" not in data,
           "active_scene definida pero remaining=0 → NO incluye handoff")


def main():
    test_build_playlist()
    test_sync_publishes_to_autopilot()
    test_publish_handoff()
    test_sync_from_autopilot_active()
    test_sync_from_autopilot_standby()
    test_sync_silent_if_not_installed()
    test_no_publish_if_playlist_empty()
    test_publish_without_active_scene_omits_handoff()
    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
