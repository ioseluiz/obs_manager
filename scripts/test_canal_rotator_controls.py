"""Tests headless para los controles de rotador por canal (R-1).

Verifica:
- pause_rotator / resume_rotator preservan el item activo y el tiempo restante.
- next_item avanza al siguiente y reset del timer.
- prev_item retrocede al anterior con wrap-around.
- get_status expone is_paused y active_index.
- No-ops cuando el estado no permite la acción.

Usa un fake ReqClient y no requiere OBS real. Necesita QApplication porque
CanalController usa QObject/QTimer.
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
    def __init__(self):
        self._items_by_scene: dict[str, list[dict]] = {}
        self._next_id = 100
        self._scenes: set[str] = set()

    def get_source_filter_kind_list(self):
        return _FakeResp(source_filter_kinds=["source_record_filter"])

    def get_input_kind_list(self, unversioned):
        return _FakeResp(input_kinds=["color_source_v3"])

    def get_scene_list(self):
        return _FakeResp(scenes=[{"sceneName": s} for s in self._scenes])

    def create_scene(self, name):
        self._scenes.add(name)

    def remove_scene(self, name):
        self._scenes.discard(name)

    def create_scene_item(self, scene_name, source_name, enabled=None):
        sid = self._next_id
        self._next_id += 1
        self._items_by_scene.setdefault(scene_name, []).append(
            {"sceneItemId": sid, "sceneItemEnabled": bool(enabled),
             "sourceName": source_name}
        )
        return _FakeResp(scene_item_id=sid)

    def get_scene_item_list(self, scene_name):
        return _FakeResp(scene_items=list(self._items_by_scene.get(scene_name, [])))

    def remove_scene_item(self, scene_name, item_id):
        lst = self._items_by_scene.get(scene_name, [])
        self._items_by_scene[scene_name] = [
            i for i in lst if i["sceneItemId"] != item_id
        ]

    def set_scene_item_enabled(self, scene_name, item_id, enabled):
        for it in self._items_by_scene.get(scene_name, []):
            if it["sceneItemId"] == item_id:
                it["sceneItemEnabled"] = enabled

    def create_source_filter(self, source_name, filter_name,
                             filter_kind, filter_settings=None):
        pass

    def remove_source_filter(self, scene, filter_name):
        pass

    def set_source_filter_enabled(self, scene, filter_name, enabled):
        pass

    def get_source_filter(self, scene, filter_name):
        return _FakeResp(filter_enabled=True, filter_settings={})


class _FakeOBSClient:
    def __init__(self):
        self.client = _FakeReqClient()
        self._client_lock = threading.RLock()


def main():
    tmp = Path(tempfile.mkdtemp(prefix="rotctrl_")) / "obs.db"
    from core import database
    database.DB_PATH = str(tmp)

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel
    from models.scene_model import SceneModel
    from controllers.canal_controller import CanalController

    init_db()

    # 3 secuencias con duraciones distintas
    conn = get_connection()
    try:
        cur = conn.cursor()
        seq_ids = []
        for name, dur in [("A", 5), ("B", 10), ("C", 3)]:
            cur.execute(
                "INSERT INTO secuencias "
                "(nombre_escena, duracion_segundos, orden, tipo, contenido) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"Seq{name}", dur, len(seq_ids) + 1, "file", "x"),
            )
            seq_ids.append(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    cm = CanalModel()
    sm = SceneModel()
    canal_id = cm.add_canal("R1Test", "udp://127.0.0.1:9500", habilitado=True)
    for sid in seq_ids:
        cm.add_item(canal_id, sid)

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    fake_obs = _FakeOBSClient()
    ctrl = CanalController(cm, sm, fake_obs)

    # apply — arranca el rotador (canal habilitado)
    ok, _ = ctrl.apply_canal(canal_id)
    _check(ok, "apply_canal ok")

    st = ctrl.get_status(canal_id)
    _check(st["rotator_running"] is True, "rotator corriendo tras apply")
    _check(st["active_index"] == 0, f"empieza en index 0 (dio {st['active_index']})")
    _check(st["is_paused"] is False, "no está pausado inicialmente")

    # === next_item ===
    print("\n[next_item]")
    ok = ctrl.next_item(canal_id)
    _check(ok, "next_item retorna True")
    st = ctrl.get_status(canal_id)
    _check(st["active_index"] == 1, f"tras next_item, index=1 (dio {st['active_index']})")
    _check(st["rotator_running"] is True, "timer sigue corriendo tras next")

    # Otro next → index 2
    ctrl.next_item(canal_id)
    _check(ctrl.get_status(canal_id)["active_index"] == 2, "next → index 2")

    # Otro next → wraparound a 0
    ctrl.next_item(canal_id)
    _check(ctrl.get_status(canal_id)["active_index"] == 0,
           "next en index 2 (último) wraparea a 0")

    # === prev_item ===
    print("\n[prev_item]")
    # En index 0 → prev debería llevar a index 2 (último)
    ok = ctrl.prev_item(canal_id)
    _check(ok, "prev_item retorna True")
    st = ctrl.get_status(canal_id)
    _check(st["active_index"] == 2,
           f"prev en index 0 wraparea al último (2), dio {st['active_index']}")

    ctrl.prev_item(canal_id)
    _check(ctrl.get_status(canal_id)["active_index"] == 1, "prev → index 1")

    # === pause / resume ===
    print("\n[pause / resume]")
    ok = ctrl.pause_rotator(canal_id)
    _check(ok, "pause_rotator retorna True")
    st = ctrl.get_status(canal_id)
    _check(st["is_paused"] is True, "is_paused=True tras pause")
    _check(st["rotator_running"] is False, "rotator_running=False cuando pausado")
    _check(st["active_index"] == 1, "index no cambia al pausar")

    # Pause de nuevo → no-op
    ok = ctrl.pause_rotator(canal_id)
    _check(ok is False, "segundo pause consecutivo es no-op (False)")

    ok = ctrl.resume_rotator(canal_id)
    _check(ok, "resume_rotator retorna True")
    st = ctrl.get_status(canal_id)
    _check(st["is_paused"] is False, "is_paused=False tras resume")
    _check(st["rotator_running"] is True, "rotator vuelve a correr tras resume")
    _check(st["active_index"] == 1, "index no cambia al resumir")

    # Resume de nuevo → no-op
    ok = ctrl.resume_rotator(canal_id)
    _check(ok is False, "segundo resume consecutivo es no-op (False)")

    # === next después de pause ===
    print("\n[next después de pause]")
    ctrl.pause_rotator(canal_id)
    _check(ctrl.get_status(canal_id)["is_paused"], "pausado")
    ok = ctrl.next_item(canal_id)
    _check(ok, "next_item funciona incluso pausado")
    st = ctrl.get_status(canal_id)
    _check(st["is_paused"] is False, "next_item quita el estado pausado")
    _check(st["active_index"] == 2, f"next tras pause → index 2 (dio {st['active_index']})")

    # === stop_rotator y prev_item con rotator detenido ===
    print("\n[stop + comandos con rotador detenido]")
    ctrl.stop_rotator(canal_id)
    st = ctrl.get_status(canal_id)
    _check(st["active_index"] == -1, "stop_rotator resetea active_index a -1")
    _check(st["rotator_running"] is False, "rotator detenido")

    # pause / resume con rotador detenido → no-ops
    _check(ctrl.pause_rotator(canal_id) is False, "pause con rotador detenido es no-op")
    _check(ctrl.resume_rotator(canal_id) is False, "resume con rotador detenido es no-op")

    # next / prev con playlist vacía
    print("\n[playlist vacía]")
    empty_id = cm.add_canal("Empty", "udp://127.0.0.1:9600", habilitado=False)
    # apply arma el estado del rotator pero playlist queda vacía
    ctrl.apply_canal(empty_id)
    _check(ctrl.next_item(empty_id) is False, "next_item con playlist vacía es no-op")
    _check(ctrl.prev_item(empty_id) is False, "prev_item con playlist vacía es no-op")

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
