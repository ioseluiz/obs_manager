"""Shim de compatibilidad.

El QSS global se mudo a `views.theme.qss` como parte del rediseno UI.
Este modulo redirecciona la importacion para no romper
`from views.styles import LIGHT_THEME_QSS` que usa `main.py` y
cualquier otro consumidor existente.
"""
from __future__ import annotations

from views.theme import LIGHT_THEME_QSS

__all__ = ["LIGHT_THEME_QSS"]
