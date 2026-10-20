"""Widgets reutilizables del rediseno UI.

- `sidebar.Sidebar`: navegacion vertical oscura.
- `app_header.AppHeader`: cabecera blanca con logo app + branding CP.
- (fases siguientes agregan HeroHeader, KpiCard, ActionButton,
  ChannelPreviewCard).
"""
from .app_header import AppHeader
from .sidebar import Sidebar

__all__ = ["AppHeader", "Sidebar"]
