"""Stylesheet global generado desde los design tokens.

En Fase 0 este QSS es **equivalente al anterior** (`views/styles.py`)
pero construido desde `tokens.py` y con property roles agregados —
para que las vistas puedan declarar su rol semantico en vez de
hardcodear colores. Las fases siguientes del rediseno extienden este
QSS con reglas para widgets nuevos (sidebar, hero, kpi cards).

Convencion de property roles:

- `QPushButton[role="primary"]`   — accion principal, fondo azul.
- `QPushButton[role="success"]`   — confirmacion, fondo verde.
- `QPushButton[role="danger"]`    — accion destructiva, fondo rojo.
- `QPushButton[role="warning"]`   — alerta, fondo naranja.
- `QPushButton[role="muted"]`     — accion secundaria, fondo gris.
- `QPushButton[role="link"]`      — enlace plano sin fondo.
- `QLabel[role="hero-title"]`     — titulo grande de hero section.
- `QLabel[role="kpi-number"]`     — numero grande de tarjeta KPI.
- `QLabel[role="status-ok"]`      — texto verde para estado OK.
- `QLabel[role="status-warn"]`    — texto naranja para estado alerta.
- `QLabel[role="status-danger"]`  — texto rojo para estado peligro.
- `QLabel[role="status-muted"]`   — texto gris para estado secundario.

Para que un property role surta efecto, el widget debe llamar
`setProperty("role", "xxx")` y luego, si cambia en runtime,
`style().unpolish(w); style().polish(w)` o emitir
`setStyleSheet(w.styleSheet())` para forzar re-aplicacion.
"""
from __future__ import annotations

from .tokens import COLORS, FONT_FAMILY, FONT_SIZES, RADII, SPACING


def _build_qss() -> str:
    c = COLORS
    s = SPACING
    r = RADII
    f = FONT_SIZES

    return f"""
    /* ============================================================
       Base
       ============================================================ */

    QWidget {{
        background-color: {c["bg_app"]};
        color: {c["text_primary"]};
        font-family: {FONT_FAMILY};
        font-size: {f["md"]}px;
    }}

    QFrame {{
        background-color: {c["bg_panel"]};
        border: 1px solid {c["border_default"]};
        border-radius: {r["md"]}px;
    }}

    /* ============================================================
       QGroupBox — paneles con titulo azul
       ============================================================ */

    QGroupBox {{
        background-color: {c["bg_panel"]};
        border: 1px solid {c["border_default"]};
        border-radius: {r["md"]}px;
        margin-top: 14px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 {s["xs"]}px;
        left: {s["md"]}px;
        top: 0px;
        color: {c["accent_primary"]};
        font-weight: bold;
    }}

    /* ============================================================
       QPushButton — base + property roles
       ============================================================ */

    QPushButton {{
        background-color: {c["accent_primary"]};
        color: {c["text_inverse"]};
        border: none;
        border-radius: {r["sm"]}px;
        padding: {s["xs"]}px {s["md"]}px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {c["accent_primary_hover"]};
    }}
    QPushButton:pressed {{
        background-color: {c["accent_primary_pressed"]};
    }}
    QPushButton:disabled {{
        background-color: {c["bg_muted"]};
        color: {c["text_muted"]};
    }}

    QPushButton[role="primary"] {{
        background-color: {c["accent_primary"]};
        color: {c["text_inverse"]};
    }}
    QPushButton[role="primary"]:hover {{
        background-color: {c["accent_primary_hover"]};
    }}

    QPushButton[role="success"] {{
        background-color: {c["state_success"]};
        color: {c["text_inverse"]};
    }}
    QPushButton[role="success"]:hover {{
        background-color: {c["state_success_hover"]};
    }}

    QPushButton[role="danger"] {{
        background-color: {c["state_danger"]};
        color: {c["text_inverse"]};
    }}
    QPushButton[role="danger"]:hover {{
        background-color: {c["state_danger_hover"]};
    }}

    QPushButton[role="warning"] {{
        background-color: {c["state_warning"]};
        color: {c["text_inverse"]};
    }}
    QPushButton[role="warning"]:hover {{
        background-color: {c["state_warning_hover"]};
    }}

    QPushButton[role="muted"] {{
        background-color: {c["state_muted"]};
        color: {c["text_inverse"]};
    }}

    QPushButton[role="link"] {{
        background-color: transparent;
        color: {c["accent_primary"]};
        text-decoration: underline;
        padding: {s["xs"]}px {s["sm"]}px;
    }}
    QPushButton[role="link"]:hover {{
        color: {c["accent_primary_hover"]};
    }}

    /* ============================================================
       Entradas de texto, spin, combo, date
       ============================================================ */

    QLineEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QDateEdit,
    QTimeEdit, QComboBox, QTableWidget, QPlainTextEdit {{
        background-color: {c["bg_input"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border_strong"]};
        border-radius: {r["sm"]}px;
        padding: {s["xs"]}px;
    }}

    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QDateTimeEdit:focus, QDateEdit:focus, QTimeEdit:focus,
    QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {c["border_focus"]};
    }}

    /* ============================================================
       QTabWidget (legacy — se mantiene mientras no se complete Fase 2)
       ============================================================ */

    QTabWidget::pane {{
        border: 1px solid {c["border_default"]};
        background-color: {c["bg_panel"]};
    }}

    QTabBar::tab {{
        background-color: {c["bg_muted"]};
        color: {c["text_secondary"]};
        padding: {s["sm"]}px {s["md"]}px;
        border: 1px solid {c["border_default"]};
        border-bottom-color: transparent;
        border-top-left-radius: {r["sm"]}px;
        border-top-right-radius: {r["sm"]}px;
    }}

    QTabBar::tab:selected {{
        background-color: {c["bg_panel"]};
        color: {c["accent_primary"]};
        font-weight: bold;
    }}

    /* ============================================================
       QLabel — property roles semanticos
       ============================================================ */

    QLabel[role="hero-title"] {{
        font-size: {f["2xl"]}px;
        font-weight: bold;
        color: {c["text_primary"]};
    }}

    QLabel[role="hero-subtitle"] {{
        font-size: {f["md"]}px;
        color: {c["text_secondary"]};
    }}

    QLabel[role="kpi-number"] {{
        font-size: {f["display"]}px;
        font-weight: bold;
        color: {c["text_primary"]};
    }}

    QLabel[role="kpi-label"] {{
        font-size: {f["sm"]}px;
        color: {c["text_muted"]};
    }}

    QLabel[role="status-ok"] {{
        color: {c["state_success"]};
        font-weight: bold;
    }}

    QLabel[role="status-warn"] {{
        color: {c["state_warning"]};
        font-weight: bold;
    }}

    QLabel[role="status-danger"] {{
        color: {c["state_danger"]};
        font-weight: bold;
    }}

    QLabel[role="status-muted"] {{
        color: {c["text_muted"]};
    }}

    QLabel[role="section-header"] {{
        font-size: {f["lg"]}px;
        font-weight: bold;
        color: {c["text_primary"]};
    }}
    """


LIGHT_THEME_QSS = _build_qss()
