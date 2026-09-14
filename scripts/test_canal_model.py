"""Smoke test headless de CanalModel — DB temporal, sin OBS.

Se ejerce cada operación pública del modelo contra una SQLite en un tmpfile,
verifica invariantes básicos, y limpia. Corre en <1 s.

Uso::

    python scripts/test_canal_model.py

Exit code 0 si todos los checks pasan, 1 en la primera falla.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Poner project root en sys.path — el script se corre desde project root
# via `venv\Scripts\python scripts\test_canal_model.py` y necesita importar
# `core.*` y `models.*`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _monkeypatch_db_path(path: str) -> None:
    """Redirige DB_PATH a un tmpfile antes de que se use en cualquier get_connection."""
    from core import database
    database.DB_PATH = path


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok — {msg}")


def main():
    tmp_dir = Path(tempfile.mkdtemp(prefix="canal_test_"))
    tmp_db = tmp_dir / "obs_manager_test.db"

    _monkeypatch_db_path(str(tmp_db))

    from core.database import init_db, get_connection
    from models.canal_model import CanalModel

    # Inicializar el schema en la DB temporal
    init_db()

    # También poblar 1 fila en `secuencias` para poder crear items válidos
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO secuencias (nombre_escena, duracion_segundos, orden, tipo, contenido) "
            "VALUES (?, ?, ?, ?, ?)",
            ("dummy_scene", 10, 1, "file", r"C:\dummy.png"),
        )
        conn.commit()
        cur.execute("SELECT id FROM secuencias")
        secuencia_id = cur.fetchone()[0]
    finally:
        conn.close()

    m = CanalModel()

    # === Canales: alta ===
    print("\n[Canales — alta]")
    c1_id = m.add_canal("Piso3", "udp://192.168.1.100:9998")
    _check(c1_id > 0, "add_canal devuelve id positivo")
    c2_id = m.add_canal("Piso4", "udp://192.168.1.100:9999",
                        encoder="qsv", bitrate_kbps=4000, habilitado=False,
                        audio_track=1, descripcion="Piso 4 lobby")
    _check(c2_id > c1_id, "ids incrementan")

    # === Canales: get ===
    print("\n[Canales — lectura]")
    c1 = m.get_canal(c1_id)
    _check(c1 is not None and c1["nombre"] == "Piso3", "get_canal por id devuelve el correcto")
    _check(c1["encoder"] == "x264" and c1["bitrate_kbps"] == 2500, "defaults aplicados")
    _check(c1["habilitado"] is True, "habilitado default True")
    _check(m.get_canal(99999) is None, "get_canal de id inexistente = None")

    c2 = m.get_canal_by_nombre("Piso4")
    _check(c2 and c2["id"] == c2_id, "get_canal_by_nombre resuelve")
    _check(c2["habilitado"] is False and c2["encoder"] == "qsv", "overrides aplicados")

    _check(m.canal_nombre_exists("Piso3") is True, "canal_nombre_exists positivo")
    _check(m.canal_nombre_exists("NoExiste") is False, "canal_nombre_exists negativo")

    canales = m.get_all_canales()
    _check(len(canales) == 2, f"get_all_canales devuelve 2 (dio {len(canales)})")
    _check(canales[0]["orden"] < canales[1]["orden"], "get_all_canales ordenado por orden asc")

    # === Canales: nombre único ===
    print("\n[Canales — constraint de unicidad]")
    try:
        m.add_canal("Piso3", "udp://x:1")
        _check(False, "add_canal con nombre duplicado debería fallar")
    except Exception as e:
        _check("UNIQUE" in str(e).upper() or "unique" in str(e), f"UNIQUE constraint activo ({e})")

    # === Canales: update ===
    print("\n[Canales — update]")
    m.update_canal(c1_id, nombre="Piso3-renamed", url_destino="udp://x:2000",
                   encoder="qsv", bitrate_kbps=5000, habilitado=False,
                   audio_track=2, descripcion="renamed")
    c1_v2 = m.get_canal(c1_id)
    _check(c1_v2["nombre"] == "Piso3-renamed", "update_canal aplica nombre")
    _check(c1_v2["bitrate_kbps"] == 5000, "update_canal aplica bitrate")
    _check(c1_v2["habilitado"] is False, "update_canal aplica habilitado False")

    # === Canales: set_habilitado ===
    print("\n[Canales — set_habilitado]")
    m.set_habilitado(c1_id, True)
    _check(m.get_canal(c1_id)["habilitado"] is True, "set_habilitado True")
    m.set_habilitado(c1_id, False)
    _check(m.get_canal(c1_id)["habilitado"] is False, "set_habilitado False")

    # === Canales: reorder ===
    print("\n[Canales — reorder]")
    ord_before = [c["id"] for c in m.get_all_canales()]
    _check(ord_before == [c1_id, c2_id], "orden inicial [c1, c2]")
    _check(m.reorder_canal(c2_id, -1) is True, "reorder c2 hacia arriba retorna True")
    ord_after = [c["id"] for c in m.get_all_canales()]
    _check(ord_after == [c2_id, c1_id], "orden tras swap [c2, c1]")
    _check(m.reorder_canal(c2_id, -1) is False, "reorder en el borde retorna False")

    # === Items: alta, lectura, reorder, borrado ===
    print("\n[Items — alta y lectura]")
    it1_id = m.add_item(c1_id, secuencia_id)
    it2_id = m.add_item(c1_id, secuencia_id, duracion_override_seg=25)
    _check(it2_id > it1_id, "item ids incrementan")
    items = m.get_items(c1_id)
    _check(len(items) == 2, "get_items devuelve 2")
    _check(items[0]["duracion_override_seg"] is None, "item sin override tiene NULL")
    _check(items[1]["duracion_override_seg"] == 25, "item con override guarda valor")

    print("\n[Items — update duracion]")
    m.update_item_duracion(it1_id, 90)
    _check(m.get_items(c1_id)[0]["duracion_override_seg"] == 90, "duración actualizada")
    m.update_item_duracion(it1_id, None)
    _check(m.get_items(c1_id)[0]["duracion_override_seg"] is None, "duración limpiada a NULL")

    print("\n[Items — reorder]")
    ids_before = [i["id"] for i in m.get_items(c1_id)]
    _check(ids_before == [it1_id, it2_id], "orden items inicial")
    _check(m.reorder_item(it2_id, -1) is True, "reorder item hacia arriba")
    ids_after = [i["id"] for i in m.get_items(c1_id)]
    _check(ids_after == [it2_id, it1_id], "orden items tras swap")

    print("\n[Items — remove individual]")
    m.remove_item(it1_id)
    _check(len(m.get_items(c1_id)) == 1, "remove_item deja 1")

    print("\n[Items — clear]")
    m.add_item(c1_id, secuencia_id)
    m.add_item(c1_id, secuencia_id)
    _check(len(m.get_items(c1_id)) == 3, "3 items antes de clear")
    m.clear_items(c1_id)
    _check(m.get_items(c1_id) == [], "clear_items deja lista vacía")

    # === Cascade delete: borrar canal borra sus items ===
    print("\n[Cascade — delete_canal borra items]")
    m.add_item(c1_id, secuencia_id)
    m.add_item(c1_id, secuencia_id)
    m.delete_canal(c1_id)
    _check(m.get_canal(c1_id) is None, "canal borrado no encontrable")
    _check(m.get_items(c1_id) == [], "items del canal borrado no quedan huérfanos")
    # El otro canal sigue intacto
    _check(m.get_canal(c2_id) is not None, "otros canales intactos")

    # === Cleanup ===
    try:
        tmp_db.unlink()
        tmp_dir.rmdir()
    except OSError:
        pass

    print("\n✓ TODOS LOS CHECKS PASARON")
    sys.exit(0)


if __name__ == "__main__":
    main()
