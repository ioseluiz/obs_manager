"""Design tokens — fuente unica de verdad para la paleta corporativa.

Reemplaza los hex hardcodeados dispersos en 20 archivos de `views/`.
Las vistas no deben hardcodear colores ni espaciados — importan desde
aqui o usan property roles del QSS global.

Paleta derivada del branding Canal de Panama (ACP, Division de
Ingenieria): azul marino institucional + azul moderno de accion +
estados funcionales (verde ok, rojo peligro, naranja aviso).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------

COLORS = {
    # Fondos base
    "bg_app": "#F8F9FA",
    "bg_panel": "#FFFFFF",
    "bg_muted": "#E9ECEF",
    "bg_input": "#FFFFFF",

    # Texto
    "text_primary": "#212529",
    "text_secondary": "#495057",
    "text_muted": "#6C757D",
    "text_inverse": "#FFFFFF",

    # Bordes
    "border_default": "#DEE2E6",
    "border_strong": "#CED4DA",
    "border_focus": "#86B7FE",

    # Branding corporativo
    "brand_navy": "#0D3B66",      # Azul marino ACP (logo, credito INI)
    "brand_navy_dark": "#0A1F3D", # Sidebar oscuro del rediseno
    "brand_red": "#C8102E",       # Rojo CP (franjas, item sidebar activo)
    "brand_accent": "#0D6EFD",    # Azul moderno — botones primary
    "toolbar_primary": "#0D3B65",  # Azul profundo de la vista previa
    "toolbar_hover": "#164973",
    "toolbar_pressed": "#0A2948",

    # Accion / estados
    "accent_primary": "#0D6EFD",
    "accent_primary_hover": "#0B5ED7",
    "accent_primary_pressed": "#0A58CA",

    "state_success": "#198754",
    "state_success_hover": "#157347",
    "state_success_bg": "#D1E7DD",
    "state_success_fg": "#0F5132",

    "state_danger": "#DC3545",
    "state_danger_hover": "#BB2D3B",

    "state_warning": "#FD7E14",
    "state_warning_hover": "#E66A00",
    "state_warning_bg": "#FFF3CD",
    "state_warning_fg": "#664D03",

    "state_info": "#17A2B8",
    "state_muted": "#6C757D",
}


# ---------------------------------------------------------------------------
# Espaciados (px). Multiplos de 4 para consistencia.
# ---------------------------------------------------------------------------

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "2xl": 32,
}


# ---------------------------------------------------------------------------
# Radios de borde.
# ---------------------------------------------------------------------------

RADII = {
    "sm": 4,
    "md": 6,
    "lg": 8,
    "xl": 12,
    "pill": 999,
}


# ---------------------------------------------------------------------------
# Tamanos de fuente.
# ---------------------------------------------------------------------------

FONT_SIZES = {
    "xs": 11,
    "sm": 12,
    "md": 14,     # base
    "lg": 16,
    "xl": 20,
    "2xl": 24,
    "display": 32,
}


FONT_FAMILY = "'Segoe UI', Arial, sans-serif"
