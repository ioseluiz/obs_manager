"""Validación de capacidad al conectar OBS (Fase 2d).

Función pura que compara los canales habilitados vs la calibración
persistida del equipo actual. Devuelve un `ValidationResult` que
la UI usa para decidir si mostrar advertencia.

Regla firme (memoria Fase 2): **nunca auto-degradar**. El validador
sólo detecta y sugiere — el user es quien decide qué canal apagar
o si sigue de todas formas.

Sin calibración persistida (equipo nuevo, o cancelada), el validador
devuelve `ok=True` con `reason='sin calibración — no se validó'`.
Es responsabilidad del caller invitar a calibrar en ese caso.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.calibration_engine import budget_cost
from core.capacity_repo import CapacityEntry


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de validar capacidad."""
    ok: bool
    reason: str
    # {encoder: costo_total_configurado_en_unidades_de_1080p30}
    used_by_encoder: dict[str, float] = field(default_factory=dict)
    # {encoder: nmax_1080p30_medido}
    capacity_by_encoder: dict[str, int] = field(default_factory=dict)
    # Lista de encoders que exceden capacidad
    overloaded_encoders: list[str] = field(default_factory=list)
    # Lista de sugerencias legibles para mostrar al user
    suggestions: list[str] = field(default_factory=list)


def _derive_preset(canal: dict[str, Any]) -> str:
    """Deriva un preset ('1080p30', '720p60', ...) del output_width/height/fps
    del canal. Fallback a '1080p30' si faltan datos.

    Regla: usar la altura (más estable en presets de video) + fps.
    """
    height = int(canal.get("output_height") or 1080)
    fps = int(canal.get("output_fps") or 30)
    # Redondear al preset conocido más cercano (720/1080/1440/2160)
    if height >= 1800:
        h_label = "4k"
    elif height >= 1300:
        h_label = "1440p"
    elif height >= 900:
        h_label = "1080p"
    elif height >= 600:
        h_label = "720p"
    else:
        h_label = "1080p"  # muy baja, no la castigamos
    # fps: 30 o 60 mayoritariamente
    fps_label = "60" if fps >= 50 else "30"
    return f"{h_label}{fps_label}"


def validate_capacity(
    canales: list[dict[str, Any]],
    entry: CapacityEntry | None,
) -> ValidationResult:
    """Compara canales habilitados vs calibración persistida.

    canales: lista de dicts como los devuelve `CanalModel.get_all_canales`.
        Solo se cuentan los que tienen `habilitado=True`.
    entry: CapacityEntry del equipo actual, o None si no hay calibración.

    Reglas:
    - Sin entry → ok=True, reason=falta calibración.
    - Sin canales habilitados → ok=True, reason=sin canales.
    - Con entry + canales: agrupa costo por encoder (cada canal aporta
      `budget_cost(preset)` — actualmente todos asumen 1080p30 = 1.0
      porque el modelo aún no guarda resolution/fps).
    - Si `costo(encoder) > entry.encoders[encoder]` → overloaded.
    """
    used_habilitados = [c for c in canales if c.get("habilitado")]
    if not used_habilitados:
        return ValidationResult(ok=True, reason="Sin canales habilitados.")

    if entry is None:
        return ValidationResult(
            ok=True,
            reason="Sin calibración previa para este equipo — no se validó.",
        )

    # Agrupar costo por encoder — cada canal aporta budget_cost(preset).
    # Deriva el preset del output_width/height/fps del canal (Opción B,
    # Fase 2). Sin esos fields (DB legacy), asume 1080p30.
    used: dict[str, float] = {}
    for c in used_habilitados:
        enc = (c.get("encoder") or "x264").lower()
        preset = c.get("preset") or _derive_preset(c)
        cost = budget_cost(preset)
        used[enc] = used.get(enc, 0.0) + cost

    capacity = {k: int(v) for k, v in entry.encoders.items()}
    overloaded: list[str] = []
    suggestions: list[str] = []

    for enc, cost in used.items():
        nmax = capacity.get(enc)
        if nmax is None:
            # Encoder usado pero no calibrado — no bloquear, sólo warning.
            suggestions.append(
                f"Encoder '{enc}' usado por {int(cost)} canal(es) pero "
                f"NO fue calibrado en este equipo. Re-calibrar."
            )
            continue
        if cost > nmax:
            overloaded.append(enc)
            faltan = int(cost - nmax)
            canales_del_encoder = [
                c["nombre"] for c in used_habilitados
                if (c.get("encoder") or "x264").lower() == enc
            ]
            suggestions.append(
                f"Encoder '{enc}': tenés {int(cost)} canales configurados pero "
                f"el equipo aguanta {nmax}. Sobra{'n' if faltan > 1 else ''} "
                f"{faltan}. Canales afectados: {', '.join(canales_del_encoder)}. "
                f"Sugerencia: deshabilitar {faltan}, bajar bitrate, o cambiar "
                f"algún canal a otro encoder."
            )

    if overloaded:
        return ValidationResult(
            ok=False,
            reason=f"{len(overloaded)} encoder(s) excedido(s): "
                   f"{', '.join(overloaded)}",
            used_by_encoder=used,
            capacity_by_encoder=capacity,
            overloaded_encoders=overloaded,
            suggestions=suggestions,
        )

    return ValidationResult(
        ok=True,
        reason="Todos los encoders dentro del presupuesto calibrado.",
        used_by_encoder=used,
        capacity_by_encoder=capacity,
        suggestions=suggestions,  # puede haber warnings (encoder no calibrado)
    )
