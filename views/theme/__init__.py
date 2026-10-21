"""Design tokens + QSS centralizado del rediseno UI.

- `tokens`: paleta corporativa Canal de Panama, espaciados, radios,
  tamanos de fuente. Constantes puras.
- `qss`: genera el stylesheet global desde los tokens. Expone
  `LIGHT_THEME_QSS` como fuente unica de verdad.
- `icons`: helper para cargar iconos corporativos (Fase 1).

Las vistas deben importar colores y espaciados desde `tokens` en vez
de hardcodear hex, y aplicar `property roles` (p. ej.
`setProperty("role", "danger")`) en vez de `setStyleSheet` inline.
"""
from __future__ import annotations

from .qss import LIGHT_THEME_QSS
from .tokens import COLORS, FONT_SIZES, RADII, SPACING

__all__ = [
    "COLORS",
    "FONT_SIZES",
    "LIGHT_THEME_QSS",
    "RADII",
    "SPACING",
]
