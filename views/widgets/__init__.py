"""Widgets reutilizables del rediseno UI.

- `sidebar.Sidebar`: navegacion vertical oscura.
- `app_header.AppHeader`: cabecera blanca con logo app + branding CP.
- (fases siguientes agregan HeroHeader, KpiCard, ActionButton,
  ChannelPreviewCard).
"""
from .action_button import ActionButton
from .app_header import AppHeader
from .channel_preview_card import ChannelPreviewCard
from .kpi_card import KpiCard
from .sidebar import Sidebar

__all__ = [
    "ActionButton",
    "AppHeader",
    "ChannelPreviewCard",
    "KpiCard",
    "Sidebar",
]
