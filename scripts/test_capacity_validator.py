"""Smoke test del capacity_validator (Fase 2d) — puro, sin OBS.

Uso: venv\\Scripts\\python.exe scripts\\test_capacity_validator.py
"""
from __future__ import annotations

import sys
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
    from core.capacity_repo import CapacityEntry, detect_fingerprint
    from core.capacity_validator import validate_capacity

    fp = detect_fingerprint(obs_major=30, gpu_override="TestGPU")

    # === Test 1: sin canales habilitados → ok ===
    print("\n[Sin canales habilitados]")
    r = validate_capacity([], None)
    _check(r.ok is True, "ok=True cuando no hay canales")

    r = validate_capacity(
        [{"nombre": "c1", "habilitado": False, "encoder": "x264"}],
        None,
    )
    _check(r.ok is True, "ok=True cuando todos deshabilitados")

    # === Test 2: sin calibración → ok con reason apropiada ===
    print("\n[Sin calibración]")
    canales = [
        {"nombre": "c1", "habilitado": True, "encoder": "x264"},
        {"nombre": "c2", "habilitado": True, "encoder": "x264"},
    ]
    r = validate_capacity(canales, None)
    _check(r.ok is True, "ok=True sin entry (no bloquear equipo sin calibrar)")
    _check("Sin calibración" in r.reason, f"reason apropiada (dio {r.reason!r})")

    # === Test 3: canales dentro del presupuesto → ok ===
    print("\n[Dentro del presupuesto]")
    entry = CapacityEntry.new(fp).with_encoder("x264", 4)
    r = validate_capacity(canales, entry)
    _check(r.ok is True, "ok=True con 2 canales y nmax=4")
    _check(r.used_by_encoder.get("x264") == 2.0, "used_by_encoder x264=2")
    _check(r.capacity_by_encoder.get("x264") == 4, "capacity_by_encoder x264=4")
    _check(r.overloaded_encoders == [], "sin overloaded")

    # === Test 4: canales exceden → ok=False + suggestions ===
    print("\n[Exceso]")
    entry = CapacityEntry.new(fp).with_encoder("x264", 1)
    canales = [
        {"nombre": "canal_a", "habilitado": True, "encoder": "x264"},
        {"nombre": "canal_b", "habilitado": True, "encoder": "x264"},
        {"nombre": "canal_c", "habilitado": True, "encoder": "x264"},
    ]
    r = validate_capacity(canales, entry)
    _check(r.ok is False, "ok=False con 3 canales y nmax=1")
    _check("x264" in r.overloaded_encoders, "x264 marcado overloaded")
    _check(r.used_by_encoder.get("x264") == 3.0, "used=3")
    _check(r.capacity_by_encoder.get("x264") == 1, "capacity=1")
    _check(len(r.suggestions) >= 1, "hay al menos 1 sugerencia")
    joined = " ".join(r.suggestions)
    _check("canal_a" in joined and "canal_b" in joined and "canal_c" in joined,
           "sugerencias listan canales afectados")

    # === Test 5: encoder mixto — sólo uno excede ===
    print("\n[Encoder mixto]")
    entry = (
        CapacityEntry.new(fp)
        .with_encoder("x264", 5)
        .with_encoder("qsv", 1)
    )
    canales = [
        {"nombre": "cA", "habilitado": True, "encoder": "x264"},
        {"nombre": "cB", "habilitado": True, "encoder": "x264"},
        {"nombre": "cQ1", "habilitado": True, "encoder": "qsv"},
        {"nombre": "cQ2", "habilitado": True, "encoder": "qsv"},
    ]
    r = validate_capacity(canales, entry)
    _check(r.ok is False, "ok=False (qsv excedido)")
    _check(r.overloaded_encoders == ["qsv"], "sólo qsv overloaded")
    _check("qsv" in " ".join(r.suggestions), "sugerencia menciona qsv")

    # === Test 6: encoder usado pero no calibrado → warning en suggestions, no bloquea ===
    print("\n[Encoder no calibrado en el entry]")
    entry = CapacityEntry.new(fp).with_encoder("x264", 5)
    canales = [
        {"nombre": "cN", "habilitado": True, "encoder": "nvenc"},
    ]
    r = validate_capacity(canales, entry)
    _check(r.ok is True, "no bloquea cuando el encoder no fue calibrado")
    _check(any("nvenc" in s and "NO fue calibrado" in s for s in r.suggestions),
           "suggestion advierte que nvenc no está calibrado")

    # === Test 7: canal sin encoder → default x264 ===
    print("\n[Canal sin encoder explícito]")
    entry = CapacityEntry.new(fp).with_encoder("x264", 1)
    canales = [
        {"nombre": "c_default", "habilitado": True},
        {"nombre": "c_default2", "habilitado": True},
    ]
    r = validate_capacity(canales, entry)
    _check(r.ok is False, "canales sin encoder cuentan como x264 y exceden")
    _check("x264" in r.overloaded_encoders, "marcado x264 overloaded")

    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
