"""Smoke test headless de CanalDetailView (R-3).

Verifica que el widget instancia, refresca sobre datos reales, y que los
slots delegan correctamente al CanalController sin crashear. No requiere
OBS conectado — el controller detecta client=None y skipea las llamadas
al socket, sólo persiste al modelo.
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
    tmp = Path(tempfile.mkdtemp(prefix="detailview_")) / "obs.db"
    from core import database
    database.DB_PATH = str(tmp)

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel
    from models.scene_model import SceneModel
    from models.obs_client import OBSClient
    from controllers.canal_controller import CanalController

    init_db()

    # Prep: 2 secuencias con distintos schedules
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO secuencias "
            "(nombre_escena, duracion_segundos, orden, tipo, contenido, "
            " active_days, active_time_start, active_time_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ScenaA", 8, 1, "file", "x", 127, None, None),
        )
        seq_a = cur.lastrowid
        cur.execute(
            "INSERT INTO secuencias "
            "(nombre_escena, duracion_segundos, orden, tipo, contenido, "
            " active_days, active_time_start, active_time_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ScenaB", 15, 2, "file", "x", 0b0011111, "09:00", "17:00"),
        )
        seq_b = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    cm = CanalModel()
    sm = SceneModel()
    canal_id = cm.add_canal(
        "Piso3", "udp://127.0.0.1:9800",
        encoder="x264", bitrate_kbps=3000, habilitado=True,
    )
    cm.add_item(canal_id, seq_a)
    cm.add_item(canal_id, seq_b, duracion_override_seg=20)

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    obs_client = OBSClient()  # sin conectar
    _check(obs_client.client is None, "OBSClient sin conexión (esperado en smoke)")
    ctrl = CanalController(cm, sm, obs_client)

    from views.canal_detail_view import CanalDetailView
    view = CanalDetailView(cm, sm, ctrl)
    _check(view is not None, "CanalDetailView instancia sin crash")

    # Sin selección → estado vacío
    _check(view.lbl_nombre.text() == "Sin selección", "sin selección al inicio")
    _check(view.btn_transmit.isEnabled() is False,
           "controles deshabilitados sin selección")

    # Seleccionar el canal
    print("\n[set_canal + refresh]")
    view.set_canal(canal_id)
    _check(view.lbl_nombre.text() == "Piso3", "nombre reflejado en header")
    _check("udp://127.0.0.1:9800" in view.lbl_url.text(), "URL en header")
    _check("x264" in view.lbl_url.text() and "3000 kbps" in view.lbl_url.text(),
           "encoder + bitrate en header")
    _check(view.btn_transmit.isChecked() is True,
           "btn_transmit refleja canal.habilitado=True")
    _check(view.btn_transmit.isEnabled() is True,
           "controles habilitados con selección")

    # Playlist tabla
    _check(view.tbl_items.rowCount() == 2, "playlist muestra 2 items")
    _check(view.tbl_items.item(0, 1).text() == "ScenaA", "primer item = ScenaA")
    _check("(override)" in view.tbl_items.item(1, 2).text(),
           "duración override anotada para el 2do item")
    # Schedule summary
    _check("Siempre" in view.tbl_items.item(0, 3).text(),
           "ScenaA muestra 'Siempre' en horario")
    _check("09:00–17:00" in view.tbl_items.item(1, 3).text(),
           "ScenaB muestra su ventana horaria")

    # OBS desconectado → status = "No aplicado en OBS"
    _check("No aplicado" in view.lbl_status.text(),
           "estado 'No aplicado' con OBS desconectado")

    # Toggle Transmitir (habilitado=True → False)
    print("\n[toggle Transmitir]")
    view.btn_transmit.setChecked(False)  # dispara _on_transmit_toggled
    # Verificar persistencia en DB
    canal_after = cm.get_canal(canal_id)
    _check(canal_after["habilitado"] is False,
           "habilitado=False persistió en el modelo tras toggle")

    view.btn_transmit.setChecked(True)
    _check(cm.get_canal(canal_id)["habilitado"] is True,
           "habilitado=True persistido tras segundo toggle")

    # Agregar item programáticamente y refrescar
    print("\n[agregar item + refresh]")
    initial_count = view.tbl_items.rowCount()
    cm.add_item(canal_id, seq_a, duracion_override_seg=99)
    view._refresh_items()
    _check(view.tbl_items.rowCount() == initial_count + 1,
           "playlist muestra el item nuevo tras refresh")
    _check("99 s (override)" in view.tbl_items.item(2, 2).text(),
           "override de 99s visible en el item nuevo")

    # Seleccionar el nuevo y quitar via _selected_item_id / model
    print("\n[quitar item seleccionado]")
    view.tbl_items.selectRow(2)
    item_id = view._selected_item_id()
    _check(item_id is not None, "selección expuesta via _selected_item_id")
    cm.remove_item(item_id)
    view._refresh_items()
    _check(view.tbl_items.rowCount() == initial_count,
           "playlist vuelve a tamaño original")

    # set_canal(None) → vuelve a vacío
    print("\n[deselección]")
    view.set_canal(None)
    _check(view.lbl_nombre.text() == "Sin selección", "deselección limpia header")
    _check(view.btn_transmit.isEnabled() is False,
           "controles vuelven a deshabilitados")

    # Instanciar el edit dialog para asegurar que no crashea
    from views.canal_item_edit_dialog import CanalItemEditDialog
    dlg = CanalItemEditDialog("SomeScene", 30, None)
    _check(dlg.chk_use_default.isChecked() is True,
           "edit dialog por defecto = usar duración de la escena")
    dlg.chk_use_default.setChecked(False)
    dlg.spin_override.setValue(45)
    _check(dlg.get_override() == 45, "get_override retorna 45 tras desactivar default")
    dlg.chk_use_default.setChecked(True)
    _check(dlg.get_override() is None,
           "get_override retorna None cuando 'usar default' está activo")

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
