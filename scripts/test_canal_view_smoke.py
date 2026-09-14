"""Smoke test headless de CanalView — verifica que instancia + refresca.

No requiere OBS: crea un CanalController con un obs_client desconectado
para que las operaciones no se disparen. Sí requiere QApplication.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok — {msg}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="canal_view_smoke_")) / "obs_manager_test.db"
    from core import database
    database.DB_PATH = str(tmp)

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel
    from models.scene_model import SceneModel
    from models.obs_client import OBSClient
    from controllers.canal_controller import CanalController

    init_db()

    # Populate: 2 secuencias + 1 canal + 2 items
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden, tipo, contenido) "
            "VALUES (?, ?, ?, ?, ?)",
            ("SmokeA", 5, 1, "file", "x"),
        )
        seq_a = cur.lastrowid
        cur.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden, tipo, contenido) "
            "VALUES (?, ?, ?, ?, ?)",
            ("SmokeB", 8, 2, "file", "y"),
        )
        seq_b = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    cm = CanalModel()
    sm = SceneModel()
    canal_id = cm.add_canal("SmokeCanal", "udp://127.0.0.1:9000",
                            encoder="x264", bitrate_kbps=3000)
    cm.add_item(canal_id, seq_a)
    cm.add_item(canal_id, seq_b, duracion_override_seg=20)

    # OBS desconectado — CanalController tolera esto
    obs_client = OBSClient()
    _check(obs_client.client is None, "OBSClient inicial sin conexión")

    ctrl = CanalController(cm, sm, obs_client)

    # QApplication + view
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from views.canal_view import CanalView
    view = CanalView(cm, sm, ctrl)
    _check(view is not None, "CanalView instancia sin crash")
    _check(view.tbl_canales.rowCount() == 1, "tabla tiene 1 canal")
    _check(view.tbl_canales.item(0, 0).text() == "SmokeCanal", "nombre en tabla")

    # Simular selección del canal para poblar items
    view.tbl_canales.selectRow(0)
    _check(view.tbl_items.rowCount() == 2, "tabla items tiene 2 filas al seleccionar canal")
    _check(view.tbl_items.item(0, 1).text() == "SmokeA", "primer item es SmokeA")
    _check("20" in view.tbl_items.item(1, 2).text(), "segundo item muestra duración override 20")

    # get_status con desconectado → not applied
    status = ctrl.get_status(canal_id)
    _check(not status.get("applied"), "canal reportado como not applied (OBS desconectado)")

    # Dialogs instancian sin crashear
    from views.canal_edit_dialog import CanalEditDialog
    from views.canal_item_picker_dialog import CanalItemPickerDialog

    dlg_edit = CanalEditDialog(existing_names=set())
    _check(dlg_edit is not None, "CanalEditDialog (nuevo) instancia")

    dlg_edit_existing = CanalEditDialog(canal=cm.get_canal(canal_id),
                                        existing_names=set())
    _check(dlg_edit_existing.ed_nombre.text() == "SmokeCanal",
           "CanalEditDialog en modo edit prefills nombre")

    dlg_picker = CanalItemPickerDialog(sm.get_all_scenes())
    _check(dlg_picker is not None, "CanalItemPickerDialog instancia con 2 secuencias")

    # Cleanup
    try:
        tmp.unlink()
        tmp.parent.rmdir()
    except OSError:
        pass

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
