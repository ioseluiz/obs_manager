"""Tests headless de programación horaria + placeholder (R-2).

Verifica:
- Items con active_days/active_time fuera de la ventana se saltan.
- Cuando TODOS los items caen fuera de ventana, se muestra el placeholder
  scene item y el rotator agenda re-check en 60s.
- Cuando la hora cambia y un item entra en ventana, el rotator lo muestra
  y ocult el placeholder.
- Un canal sin ningún item aún así muestra placeholder si existe.

Usa un FakeReqClient extendido con create_input/get_scene_item_id para
simular la creación del placeholder color source. Time injection via
ctrl._time_provider.
"""
from __future__ import annotations

import sys
import tempfile
import threading
from datetime import datetime, timedelta
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
        self._inputs: set[str] = set()

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

    def create_input(self, scene_name, input_name, input_kind,
                     input_settings, enabled):
        if input_name in self._inputs:
            raise Exception("Input already exists")
        self._inputs.add(input_name)
        sid = self._next_id
        self._next_id += 1
        self._items_by_scene.setdefault(scene_name, []).append(
            {"sceneItemId": sid, "sceneItemEnabled": bool(enabled),
             "sourceName": input_name}
        )
        return _FakeResp(scene_item_id=sid, input_uuid=f"fake-{input_name}")

    def get_scene_item_id(self, scene_name, source_name, offset=None):
        for it in self._items_by_scene.get(scene_name, []):
            if it["sourceName"] == source_name:
                return _FakeResp(scene_item_id=it["sceneItemId"])
        raise Exception(f"Scene item {source_name} not found")

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


def _visible_items(fake: _FakeReqClient, scene: str) -> list[str]:
    return [
        it["sourceName"] for it in fake._items_by_scene.get(scene, [])
        if it["sceneItemEnabled"]
    ]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sched_")) / "obs.db"
    from core import database
    database.DB_PATH = str(tmp)

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel
    from models.scene_model import SceneModel
    from controllers.canal_controller import CanalController, _RETRY_MS_WHEN_NO_ACTIVE

    init_db()

    # Prep 3 secuencias:
    # - SeqAlways: sin restricciones (siempre activa)
    # - SeqWeekend: sólo sábado/domingo (bits 5 y 6)
    # - SeqMorning: sólo lunes-viernes 09:00-12:00 (bits 0-4)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO secuencias "
            "(nombre_escena, duracion_segundos, orden, tipo, contenido, "
            " active_days, active_time_start, active_time_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SeqAlways", 5, 1, "file", "x", 127, None, None),
        )
        id_always = cur.lastrowid
        cur.execute(
            "INSERT INTO secuencias "
            "(nombre_escena, duracion_segundos, orden, tipo, contenido, "
            " active_days, active_time_start, active_time_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SeqWeekend", 5, 2, "file", "x", 0b1100000, None, None),  # sáb+dom
        )
        id_weekend = cur.lastrowid
        cur.execute(
            "INSERT INTO secuencias "
            "(nombre_escena, duracion_segundos, orden, tipo, contenido, "
            " active_days, active_time_start, active_time_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SeqMorning", 5, 3, "file", "x", 0b0011111, "09:00", "12:00"),
        )
        id_morning = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    cm = CanalModel()
    sm = SceneModel()

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    fake = _FakeOBSClient()
    ctrl = CanalController(cm, sm, fake)

    # === Canal 1: sólo SeqMorning + SeqWeekend (nada always-on) ===
    canal_id = cm.add_canal("SchedTest1", "udp://127.0.0.1:9800", habilitado=True)
    cm.add_item(canal_id, id_morning)   # lun-vie 09-12
    cm.add_item(canal_id, id_weekend)   # sáb+dom

    # Fijar "now" a un lunes 10:30 → sólo SeqMorning está en ventana
    ctrl._time_provider = lambda: datetime(2026, 1, 5, 10, 30)  # lunes 5-ene-2026

    ok, _ = ctrl.apply_canal(canal_id)
    _check(ok, "apply_canal ok (con schedule)")

    st = ctrl.get_status(canal_id)
    _check(st["item_count"] == 2, "playlist tiene 2 items")

    # Debe haber saltado a SeqMorning (el único en ventana en lunes 10:30)
    visible = _visible_items(fake.client, "SchedTest1")
    print(f"\n[Lunes 10:30 — sólo SeqMorning debe estar visible]")
    _check("SeqMorning" in visible, f"SeqMorning visible ({visible})")
    _check("SeqWeekend" not in visible, "SeqWeekend NO visible (fuera de ventana)")
    _check(not st["placeholder_visible"], "placeholder NO visible con item disponible")

    # === Cambio de tiempo: jueves 15:00 → NADA está en ventana ===
    print("\n[Jueves 15:00 — nadie en ventana, placeholder ON]")
    ctrl._time_provider = lambda: datetime(2026, 1, 8, 15, 0)  # jueves 15:00
    ctrl._test_tick(canal_id)  # fuerza un _advance

    st = ctrl.get_status(canal_id)
    _check(st["placeholder_visible"] is True, "placeholder visible")
    _check(st["active_index"] == -1, "active_index=-1 cuando todo fuera de ventana")
    visible = _visible_items(fake.client, "SchedTest1")
    _check("SeqMorning" not in visible and "SeqWeekend" not in visible,
           f"ningún item de playlist visible ({visible})")
    # Placeholder input debe estar visible
    _check(any("__placeholder" in v for v in visible),
           f"placeholder color source visible ({visible})")

    # Verificar que el timer fue agendado con _RETRY_MS_WHEN_NO_ACTIVE
    from controllers.canal_controller import _RETRY_MS_WHEN_NO_ACTIVE
    state = ctrl._rotators[canal_id]
    _check(state.timer is not None and state.timer.isActive(),
           "timer sigue corriendo (esperando retry)")
    # remainingTime debe estar cerca de _RETRY_MS_WHEN_NO_ACTIVE
    remaining = state.timer.remainingTime()
    _check(remaining >= _RETRY_MS_WHEN_NO_ACTIVE - 1000,
           f"remaining ~{_RETRY_MS_WHEN_NO_ACTIVE}ms para retry (dio {remaining})")

    # === Cambio de tiempo: sábado 20:00 → SeqWeekend entra en ventana ===
    print("\n[Sábado 20:00 — SeqWeekend disponible]")
    ctrl._time_provider = lambda: datetime(2026, 1, 10, 20, 0)  # sábado
    ctrl._test_tick(canal_id)

    st = ctrl.get_status(canal_id)
    _check(not st["placeholder_visible"], "placeholder oculto tras transición")
    _check(st["active_index"] >= 0, f"active_index >= 0 (dio {st['active_index']})")
    active_id = st["active_item_id"]
    # SeqWeekend debe ser el activo
    items = cm.get_items(canal_id)
    weekend_canal_item_id = next(i["id"] for i in items if i["secuencia_id"] == id_weekend)
    _check(active_id == weekend_canal_item_id,
           f"SeqWeekend activo (esperado item_id {weekend_canal_item_id}, dio {active_id})")

    visible = _visible_items(fake.client, "SchedTest1")
    _check("SeqWeekend" in visible, "SeqWeekend visible")
    _check(not any("__placeholder" in v for v in visible),
           f"placeholder NO visible cuando hay item activo ({visible})")

    # === Otro tick el sábado → SeqWeekend sigue (única en ventana), round-robin
    # se salta SeqMorning. active_index debe seguir en el mismo item.
    print("\n[Sábado tick otra vez — sigue en SeqWeekend]")
    ctrl._test_tick(canal_id)
    st = ctrl.get_status(canal_id)
    _check(st["active_item_id"] == weekend_canal_item_id,
           "sigue en SeqWeekend porque es el único en ventana el sábado")

    # === Canal 2: sin items → placeholder directo ===
    print("\n[Canal sin items — placeholder directo]")
    empty_id = cm.add_canal("SchedEmpty", "udp://127.0.0.1:9801", habilitado=True)
    ctrl.apply_canal(empty_id)
    st = ctrl.get_status(empty_id)
    _check(st["item_count"] == 0, "sin items en playlist")
    _check(st["placeholder_visible"] is True,
           "placeholder visible cuando canal está vacío")

    # === Canal 3: con SeqAlways + tick — siempre entra siempre ===
    print("\n[Canal con SeqAlways — siempre activo]")
    always_id = cm.add_canal("SchedAlways", "udp://127.0.0.1:9802", habilitado=True)
    cm.add_item(always_id, id_always)
    ctrl._time_provider = lambda: datetime(2026, 1, 8, 15, 0)  # jueves 15:00
    ctrl.apply_canal(always_id)
    st = ctrl.get_status(always_id)
    _check(not st["placeholder_visible"], "placeholder NO visible con item always-on")
    _check(st["active_index"] == 0, "SeqAlways es el item activo")

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
