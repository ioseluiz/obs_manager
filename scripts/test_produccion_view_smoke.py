"""Smoke test headless de ProduccionView (modelo unificado, v2.0.0).

Verifica que:
- La sidebar lista SOLO los canales de la DB (ya no existe "Canal Principal").
- Sin seleccion el stack muestra el placeholder; seleccionar un canal
  conmuta a CanalDetailView apuntando a ese canal.
- Los indicadores 🟢/⚪ reflejan `habilitado`.
- refresh() reconstruye desde la BD (nuevo canal, duplicado).
- Botones de sidebar (nuevo / editar / duplicar / eliminar) existen.
- _selected_canal_id() devuelve None sin seleccion.

Requiere QApplication (usar QT_QPA_PLATFORM=offscreen). No requiere OBS.
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
    tmp = Path(tempfile.mkdtemp(prefix="produccion_")) / "obs.db"
    from core import database
    database.DB_PATH = str(tmp)

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel
    from models.scene_model import SceneModel
    from models.obs_client import OBSClient
    from controllers.canal_controller import CanalController

    init_db()

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden, tipo, contenido) "
            "VALUES (?, ?, ?, ?, ?)",
            ("SeqX", 10, 1, "file", "x"),
        )
        conn.commit()
    finally:
        conn.close()

    cm = CanalModel()
    sm = SceneModel()
    canal_a = cm.add_canal("CanalA", "udp://127.0.0.1:9100", habilitado=True)
    canal_b = cm.add_canal("CanalB", "udp://127.0.0.1:9101", habilitado=False)

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    obs_client = OBSClient()
    canal_ctrl = CanalController(cm, sm, obs_client)

    from views.produccion_view import ProduccionView
    view = ProduccionView(cm, sm, canal_ctrl)

    # === Sidebar: solo canales reales ===
    print("[Sidebar — solo canales de la DB]")
    _check(view.lst_canales.count() == 2,
           f"sidebar con 2 items (dio {view.lst_canales.count()})")
    texts = [view.lst_canales.item(i).text() for i in range(view.lst_canales.count())]
    _check(not any("Canal Principal" in t for t in texts),
           "ningun item 'Canal Principal' (modelo unificado)")
    _check("CanalA" in texts[0], "primer item es CanalA")
    _check("CanalB" in texts[1], "segundo item es CanalB")
    _check("🟢" in texts[0], "CanalA muestra indicador 🟢 (habilitado)")
    _check("⚪" in texts[1], "CanalB muestra indicador ⚪ (deshabilitado)")

    # === Sin seleccion: placeholder ===
    print("\n[Sin seleccion → placeholder]")
    view.lst_canales.setCurrentRow(-1)
    _check(view.stack.currentIndex() == 0, "stack en placeholder (index 0)")
    _check(view._selected_canal_id() is None,
           "_selected_canal_id() es None sin seleccion")

    # === Seleccion de canal regular ===
    print("\n[Seleccion CanalA → CanalDetailView]")
    view.lst_canales.setCurrentRow(0)
    _check(view.stack.currentWidget() is view.canal_detail,
           "stack muestra CanalDetailView")
    _check(view.canal_detail._canal_id == canal_a,
           "CanalDetailView apuntando a canal_a")
    _check(view._selected_canal_id() == canal_a,
           "_selected_canal_id() devuelve canal_a")

    view.lst_canales.setCurrentRow(1)
    _check(view.canal_detail._canal_id == canal_b,
           "cambiar seleccion apunta a canal_b")

    # === refresh() reconstruye desde la BD ===
    print("\n[refresh reconstruye sidebar]")
    cm.add_canal("CanalC", "udp://127.0.0.1:9102", habilitado=True)
    view.refresh()
    _check(view.lst_canales.count() == 3, "sidebar refleja el nuevo CanalC")
    _check(view._selected_canal_id() == canal_b,
           "refresh preserva la seleccion (canal_b)")

    # === Botones del sidebar ===
    print("\n[Botones sidebar]")
    for attr in ("btn_new_canal", "btn_edit_canal",
                 "btn_duplicate_canal", "btn_delete_canal"):
        _check(hasattr(view, attr), f"{attr} existe")

    # === Duplicate via modelo + refresh ===
    print("\n[Duplicate canal]")
    before = len(cm.get_all_canales())
    new_id = cm.duplicate_canal(canal_a)
    view.refresh()
    _check(cm.get_canal(new_id)["nombre"] == "CanalA (copia)",
           "nombre auto-generado (copia)")
    _check(view.lst_canales.count() == before + 1,
           f"sidebar tras duplicar contiene el clon (dio {view.lst_canales.count()})")
    _check(cm.get_canal(new_id)["habilitado"] is False,
           "duplicado arranca deshabilitado")

    # === Cleanup ===
    try:
        tmp.unlink()
        tmp.parent.rmdir()
    except OSError:
        pass

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
