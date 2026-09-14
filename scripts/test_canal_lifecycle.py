"""Test headless del ciclo de vida de canales (Fase 1e).

Verifica:
- apply_all_habilitados aplica canales con habilitado=True y OMITE los apagados.
- shutdown_keeping_filters detiene rotator timers pero NO invoca métodos de
  OBS que modifiquen estado (respeta la regla firme: filters quedan encendidos
  al cerrar la app).

Usa un fake ReqClient que registra todas las llamadas — así los asserts son
directos sobre el comportamiento del controller, sin dependencia de OBS real.
"""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok — {msg}")


class _FakeResp:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeReqClient:
    """ReqClient stub que registra llamadas. Devuelve respuestas plausibles."""

    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []
        self._scene_items_by_scene: dict[str, list[dict]] = {}
        self._next_scene_item_id = 100
        self._scenes: set[str] = {"OldScene1", "OldScene2"}

    def _record(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))

    def get_source_filter_kind_list(self):
        self._record("get_source_filter_kind_list", (), {})
        return _FakeResp(source_filter_kinds=["source_record_filter"])

    def get_scene_list(self):
        self._record("get_scene_list", (), {})
        return _FakeResp(scenes=[{"sceneName": s} for s in self._scenes])

    def create_scene(self, name):
        self._record("create_scene", (name,), {})
        self._scenes.add(name)

    def remove_scene(self, name):
        self._record("remove_scene", (name,), {})
        self._scenes.discard(name)
        self._scene_items_by_scene.pop(name, None)

    def create_scene_item(self, scene_name, source_name, enabled=None):
        self._record("create_scene_item",
                     (scene_name, source_name), {"enabled": enabled})
        sid = self._next_scene_item_id
        self._next_scene_item_id += 1
        self._scene_items_by_scene.setdefault(scene_name, []).append({
            "sceneItemId": sid, "sceneItemEnabled": bool(enabled),
            "sourceName": source_name,
        })
        return _FakeResp(scene_item_id=sid)

    def get_scene_item_list(self, scene_name):
        self._record("get_scene_item_list", (scene_name,), {})
        return _FakeResp(scene_items=list(self._scene_items_by_scene.get(scene_name, [])))

    def remove_scene_item(self, scene_name, item_id):
        self._record("remove_scene_item", (scene_name, item_id), {})
        lst = self._scene_items_by_scene.get(scene_name, [])
        self._scene_items_by_scene[scene_name] = [
            i for i in lst if i["sceneItemId"] != item_id
        ]

    def set_scene_item_enabled(self, scene_name, item_id, enabled):
        self._record("set_scene_item_enabled", (scene_name, item_id, enabled), {})
        for item in self._scene_items_by_scene.get(scene_name, []):
            if item["sceneItemId"] == item_id:
                item["sceneItemEnabled"] = enabled

    def create_source_filter(self, source_name, filter_name,
                             filter_kind, filter_settings=None):
        self._record("create_source_filter",
                     (source_name, filter_name), {"filter_kind": filter_kind})

    def remove_source_filter(self, scene, filter_name):
        self._record("remove_source_filter", (scene, filter_name), {})

    def set_source_filter_enabled(self, scene, filter_name, enabled):
        self._record("set_source_filter_enabled",
                     (scene, filter_name, enabled), {})

    def get_source_filter(self, scene, filter_name):
        self._record("get_source_filter", (scene, filter_name), {})
        return _FakeResp(filter_enabled=True, filter_settings={})

    def get_input_kind_list(self, unversioned):
        self._record("get_input_kind_list", (unversioned,), {})
        return _FakeResp(input_kinds=["color_source_v3"])


class _FakeOBSClient:
    """Emula OBSClient interface esencial para CanalController."""

    def __init__(self):
        self.client = _FakeReqClient()
        self._client_lock = threading.RLock()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="canal_lifecycle_")) / "obs_manager_test.db"
    from core import database
    database.DB_PATH = str(tmp)

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel
    from models.scene_model import SceneModel
    from controllers.canal_controller import CanalController

    init_db()

    # Preparar 2 secuencias + 3 canales (2 habilitados + 1 apagado)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden, tipo, contenido) "
            "VALUES (?, ?, ?, ?, ?)",
            ("SeqA", 5, 1, "file", "x"),
        )
        seq_a = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    cm = CanalModel()
    sm = SceneModel()

    c_on1 = cm.add_canal("CanalOn1", "udp://127.0.0.1:9001", habilitado=True)
    cm.add_item(c_on1, seq_a)
    c_on2 = cm.add_canal("CanalOn2", "udp://127.0.0.1:9002", habilitado=True)
    cm.add_item(c_on2, seq_a)
    c_off = cm.add_canal("CanalOff", "udp://127.0.0.1:9003", habilitado=False)
    cm.add_item(c_off, seq_a)

    # QApplication (por QTimer/QObject en CanalController)
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    fake_obs = _FakeOBSClient()
    ctrl = CanalController(cm, sm, fake_obs)

    # === apply_all_habilitados ===
    print("\n[apply_all_habilitados]")
    results = ctrl.apply_all_habilitados()
    _check(len(results) == 2, f"resultados sólo para los 2 canales habilitados (dio {len(results)})")
    ids_applied = {r["canal_id"] for r in results}
    _check(c_on1 in ids_applied and c_on2 in ids_applied, "CanalOn1 y CanalOn2 aplicados")
    _check(c_off not in ids_applied, "CanalOff NO aplicado (habilitado=False)")
    _check(all(r["ok"] for r in results), "todos los applies exitosos")

    # El fake registra las escenas creadas
    _check("CanalOn1" in fake_obs.client._scenes, "CanalOn1 creada en OBS")
    _check("CanalOn2" in fake_obs.client._scenes, "CanalOn2 creada en OBS")
    _check("CanalOff" not in fake_obs.client._scenes, "CanalOff NO creada en OBS")

    # Filter aplicado a cada canal habilitado
    filter_creates = [
        c for c in fake_obs.client.calls
        if c[0] == "create_source_filter"
    ]
    scenes_with_filter = {c[1][0] for c in filter_creates}
    _check(scenes_with_filter == {"CanalOn1", "CanalOn2"},
           f"filters creados en CanalOn1+CanalOn2 (dio {scenes_with_filter})")

    # === shutdown_keeping_filters ===
    print("\n[shutdown_keeping_filters]")
    # Snapshot de llamadas ANTES del shutdown para poder detectar nuevas
    n_calls_before = len(fake_obs.client.calls)
    # Timers deben estar corriendo (canales habilitados con playlist)
    running_timers = sum(
        1 for s in ctrl._rotators.values()
        if s.timer is not None and s.timer.isActive()
    )
    _check(running_timers >= 1, f"al menos 1 rotator timer corriendo antes de shutdown ({running_timers})")

    ctrl.shutdown_keeping_filters()

    # Ningún timer debe seguir asignado
    still_alive = [s for s in ctrl._rotators.values() if s.timer is not None]
    _check(len(still_alive) == 0, "todos los timers desasignados tras shutdown")

    # No debe haber llamadas nuevas al fake — la regla es NO tocar OBS
    n_calls_after = len(fake_obs.client.calls)
    _check(n_calls_after == n_calls_before,
           f"shutdown no invocó métodos de OBS "
           f"(antes={n_calls_before}, después={n_calls_after})")

    # Verificar específicamente que no se llamó a los métodos "peligrosos"
    forbidden = {"set_source_filter_enabled", "remove_source_filter",
                 "remove_scene", "set_scene_item_enabled", "remove_scene_item"}
    calls_since = fake_obs.client.calls[n_calls_before:]
    forbidden_hits = [c for c in calls_since if c[0] in forbidden]
    _check(len(forbidden_hits) == 0,
           f"ningún método destructivo de OBS invocado durante shutdown "
           f"(intrusiones: {forbidden_hits})")

    # === apply_all_habilitados es idempotente ===
    print("\n[apply_all_habilitados idempotente]")
    ctrl2 = CanalController(cm, sm, fake_obs)  # nuevo controller
    results2 = ctrl2.apply_all_habilitados()
    _check(len(results2) == 2 and all(r["ok"] for r in results2),
           "segunda pasada aplica también sin errores")

    # Cleanup
    try:
        tmp.unlink()
        tmp.parent.rmdir()
    except OSError:
        pass

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
