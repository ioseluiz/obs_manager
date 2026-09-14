"""Smoke test headless de CapacityRepo (Fase 2a).

Verifica load/save/upsert/delete + fingerprint stability. Sin OBS,
sin PyQt. Corre en <1 s.

Uso: venv\\Scripts\\python.exe scripts\\test_capacity_repo.py
"""
from __future__ import annotations

import json
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
    print(f"  ok - {msg}")


def main():
    from core.capacity_repo import (
        Fingerprint, CapacityEntry, CapacityRepo,
        detect_fingerprint, default_repo_path,
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="capacity_test_"))
    repo_path = tmp_dir / "calibrations.json"

    # === Fingerprint ===
    print("\n[Fingerprint - detect y equality]")
    fp1 = detect_fingerprint(obs_major=30, gpu_override="TestGPU")
    _check(fp1.obs_major == 30, "obs_major se propaga")
    _check(fp1.gpu == "TestGPU", "gpu_override se aplica")
    _check(fp1.cpu_threads > 0, f"cpu_threads detectados ({fp1.cpu_threads})")

    fp2 = detect_fingerprint(obs_major=30, gpu_override="TestGPU")
    _check(fp1 == fp2, "detect_fingerprint estable en llamadas sucesivas")

    fp3 = detect_fingerprint(obs_major=31, gpu_override="TestGPU")
    _check(fp1 != fp3, "obs_major distinto -> fingerprint distinto")

    fp4 = detect_fingerprint(obs_major=30, gpu_override="OtraGPU")
    _check(fp1 != fp4, "gpu distinta -> fingerprint distinto")

    # === Fingerprint dict roundtrip ===
    print("\n[Fingerprint - to/from dict]")
    d = fp1.as_dict()
    _check(set(d.keys()) == {"hostname", "cpu_threads", "gpu", "obs_major"},
           "as_dict tiene las 4 keys esperadas")
    fp1_back = Fingerprint.from_dict(d)
    _check(fp1_back == fp1, "roundtrip preserva igualdad")

    # === CapacityEntry ===
    print("\n[CapacityEntry - construccion y with_encoder]")
    e0 = CapacityEntry.new(fp1, notes="prueba inicial")
    _check(e0.fingerprint == fp1, "fingerprint asignado")
    _check(e0.encoders == {}, "encoders arranca vacio")
    _check(e0.calibrated_at.startswith("20"), "calibrated_at es ISO")
    _check(e0.notes == "prueba inicial", "notes preservado")

    e1 = e0.with_encoder("x264", 2)
    _check(e1.encoders == {"x264": 2}, "with_encoder agrega el encoder")
    _check(e0.encoders == {}, "with_encoder no muta el original")

    e2 = e1.with_encoder("qsv", 3).with_encoder("x264", 1)
    _check(e2.encoders == {"x264": 1, "qsv": 3},
           "with_encoder encadena y sobrescribe")

    # === CapacityEntry dict roundtrip ===
    print("\n[CapacityEntry - to/from dict]")
    d = e2.as_dict()
    _check("fingerprint" in d and "encoders" in d, "as_dict tiene keys principales")
    e2_back = CapacityEntry.from_dict(d)
    _check(e2_back.fingerprint == e2.fingerprint, "fingerprint roundtrip")
    _check(e2_back.encoders == e2.encoders, "encoders roundtrip")

    # === Repo empty ===
    print("\n[Repo - vacio inicial]")
    repo = CapacityRepo(path=repo_path)
    _check(repo.load_all() == [], "load_all() sin file = []")
    _check(repo.get(fp1) is None, "get(fp) sin entries = None")

    # === Repo upsert ===
    print("\n[Repo - upsert inserta y actualiza]")
    repo.upsert(e2)
    _check(repo_path.exists(), "archivo se creo")
    e2_reloaded = repo.get(fp1)
    _check(e2_reloaded is not None, "get(fp1) devuelve la entry")
    _check(e2_reloaded.encoders == {"x264": 1, "qsv": 3},
           "encoders persistidos correctamente")

    # Upsert del mismo fingerprint sobrescribe
    e2_upd = e2.with_encoder("nvenc", 5)
    repo.upsert(e2_upd)
    _check(len(repo.load_all()) == 1, "upsert de mismo fp NO duplica entry")
    _check(repo.get(fp1).encoders.get("nvenc") == 5, "nvenc agregado")

    # Upsert de otro fingerprint agrega
    e_other = CapacityEntry.new(fp3).with_encoder("x264", 4)
    repo.upsert(e_other)
    _check(len(repo.load_all()) == 2, "upsert de otro fp agrega segunda entry")
    _check(repo.get(fp3).encoders == {"x264": 4}, "segunda entry recuperable")
    _check(repo.get(fp1).encoders.get("nvenc") == 5, "primera entry intacta")

    # === Repo delete ===
    print("\n[Repo - delete]")
    _check(repo.delete(fp1) is True, "delete(fp1) devuelve True")
    _check(repo.get(fp1) is None, "fp1 borrado")
    _check(repo.get(fp3) is not None, "fp3 sigue estando")
    _check(repo.delete(fp1) is False, "delete de fp inexistente devuelve False")

    # === Repo robustez ===
    print("\n[Repo - robustez frente a archivo corrupto]")
    # Archivo corrupto se comporta como "vacio" tras log warning
    repo_path.write_text("this is not json {[")
    repo_bad = CapacityRepo(path=repo_path)
    _check(repo_bad.load_all() == [], "JSON corrupto -> []")

    # Archivo con schema desconocido pero JSON válido
    repo_path.write_text(json.dumps({"lo_que_sea": True}))
    _check(repo_bad.load_all() == [], "JSON sin 'entries' -> []")

    # Archivo con entries[] pero una entry inválida — las válidas sobreviven
    repo_path.write_text(json.dumps({
        "schema_version": 1,
        "entries": [
            {"fingerprint": {"broken": "yes"}},  # falta keys
            e_other.as_dict(),  # válida
        ]
    }))
    survived = repo_bad.load_all()
    _check(len(survived) == 1, "entries invalidas se saltan, validas sobreviven")
    _check(survived[0].fingerprint == fp3, "entry sobreviviente es la correcta")

    # === Default path (no acceder al filesystem, solo formar el path) ===
    print("\n[default_repo_path]")
    p = default_repo_path()
    _check("OBS_Automation_Manager" in str(p), "path incluye la carpeta app")
    _check(p.name == "calibrations.json", "filename correcto")

    # Cleanup
    try:
        repo_path.unlink()
        (repo_path.parent).rmdir()
    except OSError:
        pass

    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
