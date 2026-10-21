"""Smoke test headless de core/legacy_migrator.py.

Verifica needs_migration + migrate_legacy_to_canal con BD temporal +
mocks de canal_controller. No requiere OBS.

Uso::

    python scripts/test_legacy_migrator.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


def _monkeypatch_db_path(path: str) -> None:
    from core import database
    database.DB_PATH = path


def _setup_db_with_scenes(count: int = 3):
    """Crea una BD limpia con N secuencias y devuelve
    (scene_model, canal_model, scene_ids)."""
    from core import database
    database.init_db()
    from models.scene_model import SceneModel
    from models.canal_model import CanalModel
    sm = SceneModel()
    cm = CanalModel()
    for i in range(count):
        sm.add_scene(
            name=f"Escena{i+1}", duration=10, tipo="file",
            contenido="/tmp/foo.png", ancho=1920, alto=1080, fps=30,
            reload_on_activate=False, keep_session=False,
        )
    # add_scene no retorna id; lo leemos despues con get_all_scenes.
    ids = [int(s["id"]) for s in sm.get_all_scenes()]
    return sm, cm, ids


def test_needs_migration_true_sin_flag():
    print("[needs_migration: True si hay secuencias y flag no marcado]")
    tmp = tempfile.mkdtemp(prefix="legacy_mig_")
    _monkeypatch_db_path(str(Path(tmp) / "test.db"))
    sm, _cm, _ids = _setup_db_with_scenes(3)
    settings = MagicMock()
    settings.get_flag.return_value = "false"
    from core.legacy_migrator import needs_migration
    _check(needs_migration(sm, settings) is True,
           "3 secuencias + flag=false → True")


def test_needs_migration_false_con_flag():
    print("[needs_migration: False si flag=true]")
    tmp = tempfile.mkdtemp(prefix="legacy_mig_")
    _monkeypatch_db_path(str(Path(tmp) / "test.db"))
    sm, _cm, _ids = _setup_db_with_scenes(3)
    settings = MagicMock()
    settings.get_flag.return_value = "true"
    from core.legacy_migrator import needs_migration
    _check(needs_migration(sm, settings) is False,
           "flag=true → False (ya migrado)")


def test_needs_migration_false_sin_secuencias():
    print("[needs_migration: False si no hay secuencias]")
    tmp = tempfile.mkdtemp(prefix="legacy_mig_")
    _monkeypatch_db_path(str(Path(tmp) / "test.db"))
    _sm, _cm, _ids = _setup_db_with_scenes(0)
    from models.scene_model import SceneModel
    sm = SceneModel()
    settings = MagicMock()
    settings.get_flag.return_value = "false"
    from core.legacy_migrator import needs_migration
    _check(needs_migration(sm, settings) is False,
           "0 secuencias → False")


def test_migrate_happy_path():
    print("[migrate_legacy_to_canal: happy path con 3 secuencias]")
    tmp = tempfile.mkdtemp(prefix="legacy_mig_")
    _monkeypatch_db_path(str(Path(tmp) / "test.db"))
    sm, cm, ids = _setup_db_with_scenes(3)

    # Mock canal_controller con apply_canal exitoso.
    canal_ctrl = MagicMock()
    canal_ctrl.apply_canal.return_value = (True, "Canal aplicado en OBS.")

    from core.legacy_migrator import migrate_legacy_to_canal
    ok, canal_id, msg = migrate_legacy_to_canal(
        canal_model=cm, scene_model=sm, canal_controller=canal_ctrl,
        canal_name="Canal Legacy", udp_url="udp://127.0.0.1:9001",
    )
    _check(ok is True, "ok=True")
    _check(canal_id is not None, f"canal_id={canal_id}")
    _check("3 items" in msg, "mensaje reporta 3 items")

    # Verificar BD: 1 canal + 3 items.
    canales = cm.get_all_canales()
    _check(len(canales) == 1, "1 canal creado en BD")
    _check(canales[0]["nombre"] == "Canal Legacy",
           "nombre correcto")
    _check(canales[0]["url_destino"] == "udp://127.0.0.1:9001",
           "url_destino correcta")

    items = cm.get_items(canal_id)
    _check(len(items) == 3, "3 items en canal_items")
    item_sec_ids = sorted(i["secuencia_id"] for i in items)
    _check(item_sec_ids == sorted(ids),
           "items apuntan a todas las secuencias originales")

    canal_ctrl.apply_canal.assert_called_once_with(canal_id)
    _check(True, "apply_canal(canal_id) fue llamado")


def test_migrate_subset_de_secuencias():
    print("[migrate_legacy_to_canal: solo subset de secuencias]")
    tmp = tempfile.mkdtemp(prefix="legacy_mig_")
    _monkeypatch_db_path(str(Path(tmp) / "test.db"))
    sm, cm, ids = _setup_db_with_scenes(5)

    canal_ctrl = MagicMock()
    canal_ctrl.apply_canal.return_value = (True, "ok")

    from core.legacy_migrator import migrate_legacy_to_canal
    # Elegir solo las 2 primeras.
    subset = ids[:2]
    ok, canal_id, _msg = migrate_legacy_to_canal(
        canal_model=cm, scene_model=sm, canal_controller=canal_ctrl,
        canal_name="Mini", udp_url="udp://10.0.0.1:7777",
        secuencia_ids=subset,
    )
    _check(ok is True, "ok=True")
    items = cm.get_items(canal_id)
    _check(len(items) == 2, "solo 2 items (subset)")


def test_migrate_validaciones():
    print("[migrate_legacy_to_canal: validaciones de input]")
    tmp = tempfile.mkdtemp(prefix="legacy_mig_")
    _monkeypatch_db_path(str(Path(tmp) / "test.db"))
    sm, cm, _ids = _setup_db_with_scenes(3)
    canal_ctrl = MagicMock()
    canal_ctrl.apply_canal.return_value = (True, "ok")
    from core.legacy_migrator import migrate_legacy_to_canal

    ok, _, msg = migrate_legacy_to_canal(
        cm, sm, canal_ctrl, canal_name="", udp_url="udp://x:1",
    )
    _check(not ok and "nombre" in msg.lower(), "nombre vacio rechazado")

    ok, _, msg = migrate_legacy_to_canal(
        cm, sm, canal_ctrl, canal_name="X", udp_url="",
    )
    _check(not ok and "url" in msg.lower(), "URL vacia rechazada")

    ok, _, msg = migrate_legacy_to_canal(
        cm, sm, canal_ctrl, canal_name="X", udp_url="udp://x:1",
        secuencia_ids=[],
    )
    _check(not ok and "secuencia" in msg.lower(),
           "secuencia_ids=[] rechazado")


def test_migrate_apply_falla():
    print("[migrate_legacy_to_canal: apply_canal falla → ok=False con canal_id]")
    tmp = tempfile.mkdtemp(prefix="legacy_mig_")
    _monkeypatch_db_path(str(Path(tmp) / "test.db"))
    sm, cm, _ids = _setup_db_with_scenes(2)

    canal_ctrl = MagicMock()
    canal_ctrl.apply_canal.return_value = (False, "OBS desconectado")

    from core.legacy_migrator import migrate_legacy_to_canal
    ok, canal_id, msg = migrate_legacy_to_canal(
        cm, sm, canal_ctrl,
        canal_name="Fail", udp_url="udp://x:1",
    )
    _check(ok is False, "ok=False cuando apply_canal falla")
    _check(canal_id is not None,
           f"canal_id devuelto para que el user pueda retry (id={canal_id})")
    _check("OBS desconectado" in msg,
           "mensaje contiene razon del apply_canal")


def main():
    print("=== legacy_migrator smoke tests ===")
    test_needs_migration_true_sin_flag()
    test_needs_migration_false_con_flag()
    test_needs_migration_false_sin_secuencias()
    test_migrate_happy_path()
    test_migrate_subset_de_secuencias()
    test_migrate_validaciones()
    test_migrate_apply_falla()
    print("\n=== TODO OK ===")


if __name__ == "__main__":
    main()
