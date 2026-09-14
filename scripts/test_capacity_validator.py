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

    # === Test 8: preset derivado del output_width/height/fps ===
    print("\n[Preset derivado por canal — 720p60 y 1080p60 cuestan más]")
    from core.capacity_validator import _derive_preset

    _check(_derive_preset({"output_height": 1080, "output_fps": 30}) == "1080p30",
           "1080/30 → 1080p30")
    _check(_derive_preset({"output_height": 720, "output_fps": 60}) == "720p60",
           "720/60 → 720p60")
    _check(_derive_preset({"output_height": 1080, "output_fps": 60}) == "1080p60",
           "1080/60 → 1080p60")
    _check(_derive_preset({"output_height": 2160, "output_fps": 30}) == "4k30",
           "2160/30 → 4k30")
    _check(_derive_preset({}) == "1080p30", "sin fields → 1080p30 fallback")

    # === Test 9: canal 1080p60 cuesta 2 en el validador ===
    print("\n[Canal 1080p60 cuesta 2 vs 1080p30 cuesta 1]")
    entry = CapacityEntry.new(fp).with_encoder("x264", 2)
    canales = [
        # Un solo canal 1080p60 = costo 2 = exactamente al límite
        {"nombre": "c1", "habilitado": True, "encoder": "x264",
         "output_height": 1080, "output_fps": 60},
    ]
    r = validate_capacity(canales, entry)
    _check(r.ok is True, "un canal 1080p60 con nmax=2 pasa exacto")
    _check(r.used_by_encoder.get("x264") == 2.0, "used=2.0 (1080p60)")

    # Dos canales 1080p60 = costo 4, con nmax=2 → excede
    canales.append(dict(canales[0], nombre="c2"))
    r = validate_capacity(canales, entry)
    _check(r.ok is False, "dos canales 1080p60 con nmax=2 excede")
    _check(r.used_by_encoder.get("x264") == 4.0, "used=4.0")

    # Un 1080p30 + un 720p30 = 1 + 0.5 = 1.5 < 2 → ok
    canales_mix = [
        {"nombre": "cA", "habilitado": True, "encoder": "x264",
         "output_height": 1080, "output_fps": 30},
        {"nombre": "cB", "habilitado": True, "encoder": "x264",
         "output_height": 720, "output_fps": 30},
    ]
    r = validate_capacity(canales_mix, entry)
    _check(r.ok is True, "1080p30 + 720p30 = 1.5 pasa con nmax=2")
    _check(r.used_by_encoder.get("x264") == 1.5, "used=1.5 (1.0 + 0.5)")

    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
