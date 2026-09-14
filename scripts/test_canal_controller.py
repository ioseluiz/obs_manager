"""Test end-to-end de CanalController — requiere OBS real.

Usa una DB temporal (monkeypatch DB_PATH) y escenas prefijadas con `TCC_`
en OBS para no tocar el entorno del user. Al final limpia todo.

Ejercita:
- apply_canal crea escena contenedora, adjunta filtro deshabilitado (canal
  arranca con habilitado=False), reconcilia scene items desde canal_items.
- set_habilitado(True) enciende el filter y arranca el rotador.
- _test_tick manual avanza al siguiente item (verifica SetSceneItemEnabled).
- set_habilitado(False) apaga filter + oculta todos los items.
- remove_canal_from_obs limpia escena + filter de OBS.

Uso::

    python scripts/test_canal_controller.py --password <pwd>
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok — {msg}")


def _quiet(fn, *args):
    import logging
    lg = logging.getLogger("obsws_python.reqs")
    prev = lg.level
    lg.setLevel(logging.CRITICAL)
    try:
        try:
            return fn(*args)
        except Exception:
            return None
    finally:
        lg.setLevel(prev)


def main():
    ap = argparse.ArgumentParser(description="Test CanalController (live)")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=4455)
    ap.add_argument("--password", default="")
    ap.add_argument("--udp-port", type=int, default=9997)
    args = ap.parse_args()

    # 1. DB temporal
    tmp_dir = Path(tempfile.mkdtemp(prefix="canal_ctrl_test_"))
    tmp_db = tmp_dir / "obs_manager_test.db"
    from core import database
    database.DB_PATH = str(tmp_db)

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel
    from models.scene_model import SceneModel
    from models.obs_client import OBSClient
    from controllers.canal_controller import CanalController

    init_db()

    # 2. QApplication (CanalController usa QObject / QTimer)
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    # 3. Preparar secuencias en la DB apuntando a nombres de escenas que
    #    vamos a crear en OBS con prefijo TCC_ para no colisionar.
    scene_a_name = "TCC_ScenaA"
    scene_b_name = "TCC_ScenaB"
    canal_scene_name = "TCC_CanalContenedor"

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden, tipo, contenido) "
            "VALUES (?, ?, ?, ?, ?)",
            (scene_a_name, 3, 1, "file", "dummy"),
        )
        seq_a_id = cur.lastrowid
        cur.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden, tipo, contenido) "
            "VALUES (?, ?, ?, ?, ?)",
            (scene_b_name, 3, 2, "file", "dummy"),
        )
        seq_b_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    # 4. Conectar a OBS y crear las escenas fuente (TCC_ScenaA/B con un color source)
    obs_client = OBSClient()
    ok, msg = obs_client.connect(args.host, args.port, args.password)
    if not ok:
        print(f"FAIL: no se pudo conectar a OBS: {msg}")
        sys.exit(2)
    print(f"[OBS conectado — {msg}]")

    def cleanup_obs():
        client = obs_client.client
        if client is None:
            return
        # Remove filter, scene items, and scenes we may have created
        _quiet(client.remove_source_filter, canal_scene_name, "udp_out")
        _quiet(client.remove_scene, canal_scene_name)
        _quiet(client.remove_input, f"{scene_a_name}_color")
        _quiet(client.remove_input, f"{scene_b_name}_color")
        _quiet(client.remove_scene, scene_a_name)
        _quiet(client.remove_scene, scene_b_name)

    try:
        cleanup_obs()

        client = obs_client.client
        # Crear TCC_ScenaA y TCC_ScenaB con un color source cada una
        client.create_scene(scene_a_name)
        client.create_input(scene_a_name, f"{scene_a_name}_color", "color_source_v3",
                            {"color": 0xFFFF0000, "width": 1920, "height": 1080}, True)
        client.create_scene(scene_b_name)
        client.create_input(scene_b_name, f"{scene_b_name}_color", "color_source_v3",
                            {"color": 0xFF00FF00, "width": 1920, "height": 1080}, True)
        print(f"[Escenas fuente creadas en OBS: {scene_a_name}, {scene_b_name}]")

        # 5. Configurar canal + items en la DB
        cm = CanalModel()
        sm = SceneModel()
        canal_id = cm.add_canal(
            canal_scene_name,
            f"udp://127.0.0.1:{args.udp_port}",
            encoder="x264", bitrate_kbps=2500,
            habilitado=False,  # arranca apagado para tests deterministas
        )
        cm.add_item(canal_id, seq_a_id)
        cm.add_item(canal_id, seq_b_id)
        print(f"[Canal id={canal_id} + 2 items creados en DB]")

        # 6. Instanciar controller
        ctrl = CanalController(cm, sm, obs_client)

        # === apply_canal ===
        print("\n[apply_canal — crea escena + items + filter deshabilitado]")
        ok, msg = ctrl.apply_canal(canal_id)
        _check(ok, f"apply_canal ok ({msg})")

        # Verificar en OBS
        scenes = {s["sceneName"] for s in getattr(client, "_inner", client).get_scene_list().scenes}
        _check(canal_scene_name in scenes, "escena contenedora existe en OBS")

        items = getattr(client, "_inner", client).get_scene_item_list(canal_scene_name).scene_items
        _check(len(items) == 2, f"contenedor tiene 2 scene items (dio {len(items)})")

        # Filter presente y deshabilitado (canal.habilitado=False)
        from core.output_adapter import OutputAdapter
        adapter = OutputAdapter(client)
        _check(adapter.is_present(canal_scene_name), "filter udp_out presente")
        _check(adapter.is_enabled(canal_scene_name) is False,
               "filter deshabilitado (canal.habilitado=False)")

        # status
        st = ctrl.get_status(canal_id)
        _check(st["applied"] is True, "status.applied True")
        _check(st["item_count"] == 2, "status.item_count 2")
        _check(st["rotator_running"] is False, "rotator no corre con canal apagado")

        # === set_habilitado(True) — enciende filter + arranca rotador ===
        print("\n[set_habilitado(True) — enciende filter + arranca rotador]")
        ok, _ = ctrl.set_habilitado(canal_id, True)
        _check(ok, "set_habilitado(True) ok")
        _check(adapter.is_enabled(canal_scene_name) is True, "filter enabled tras toggle")

        # El _advance ya hizo el primer tick al arrancar — item 0 debe estar visible
        st = ctrl.get_status(canal_id)
        _check(st["rotator_running"] is True, "rotator corriendo")
        _check(st["active_item_id"] is not None, "hay item activo")
        first_active = st["active_item_id"]

        # Confirmar en OBS: exactamente 1 scene item enabled
        items = getattr(client, "_inner", client).get_scene_item_list(canal_scene_name).scene_items
        enabled = [it for it in items if it["sceneItemEnabled"]]
        _check(len(enabled) == 1, f"exactamente 1 scene item visible (dio {len(enabled)})")

        # === Tick manual — avanza al siguiente item ===
        print("\n[_test_tick — avanza al siguiente item]")
        ctrl._test_tick(canal_id)
        st2 = ctrl.get_status(canal_id)
        _check(st2["active_item_id"] != first_active,
               f"active_item cambió tras tick ({first_active} → {st2['active_item_id']})")

        items = getattr(client, "_inner", client).get_scene_item_list(canal_scene_name).scene_items
        enabled = [it for it in items if it["sceneItemEnabled"]]
        _check(len(enabled) == 1, "sigue habiendo exactamente 1 visible tras tick")

        # === Tick de nuevo — vuelve al primero (round-robin) ===
        print("\n[_test_tick — round-robin al primer item]")
        ctrl._test_tick(canal_id)
        st3 = ctrl.get_status(canal_id)
        _check(st3["active_item_id"] == first_active,
               "round-robin — vuelve al primer item")

        # === set_habilitado(False) — apaga filter + oculta todo ===
        print("\n[set_habilitado(False) — apaga filter + oculta items]")
        ok, _ = ctrl.set_habilitado(canal_id, False)
        _check(ok, "set_habilitado(False) ok")
        _check(adapter.is_enabled(canal_scene_name) is False,
               "filter deshabilitado")

        # Todos los scene items ocultos
        items = getattr(client, "_inner", client).get_scene_item_list(canal_scene_name).scene_items
        enabled = [it for it in items if it["sceneItemEnabled"]]
        _check(len(enabled) == 0, "todos los items ocultos tras apagar canal")
        st4 = ctrl.get_status(canal_id)
        _check(st4["rotator_running"] is False, "rotator parado")

        # === remove_canal_from_obs ===
        print("\n[remove_canal_from_obs — limpia OBS]")
        ok, _ = ctrl.remove_canal_from_obs(canal_id)
        _check(ok, "remove_canal_from_obs ok")
        # OBS puede tomar unos ms en reflejar la remoción en get_scene_list.
        # La escena aparece en el log de OBS como removida, pero un query
        # inmediato puede leer estado stale del canvas manager.
        time.sleep(0.5)
        scenes = {s["sceneName"] for s in getattr(client, "_inner", client).get_scene_list().scenes}
        _check(canal_scene_name not in scenes,
               f"escena contenedora removida de OBS (scenes actuales: {sorted(scenes)})")

    finally:
        cleanup_obs()
        obs_client.disconnect()
        try:
            tmp_db.unlink()
            tmp_dir.rmdir()
        except OSError:
            pass

    print("\n✓ TODOS LOS CHECKS PASARON")
    sys.exit(0)


if __name__ == "__main__":
    main()
