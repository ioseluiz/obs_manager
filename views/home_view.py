"""Pestana Inicio del rediseno UI.

Composicion:

    [ Hero: titulo + descripcion                                       ]
    [ KPI1 ] [ KPI2 ] [ KPI3 ] [ KPI4 ]
    [ Acciones rapidas ---------------------------------------------- ]
    [ [BT 1] [BT 2] [BT 3] [BT 4]                                      ]
    [ Estado de OBS Studio       |     Vista previa de canales         ]

El controller (`controllers/home_controller.py`) refresca los KPIs y
conecta las acciones a los handlers del MainController existentes
(open_settings, connect_to_obs, etc.).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS, SPACING
from views.widgets import ActionButton, ChannelPreviewCard, KpiCard
from views.widgets.obs_status_card import ObsStatusCard
from views.widgets.responsive_layout import arrange_grid


class HomeView(QWidget):
    # Senales expuestas al controller para encadenar a los handlers
    # existentes del MainController sin acoplar vistas.
    action_new_canal = pyqtSignal()
    action_connect_obs = pyqtSignal()
    action_import = pyqtSignal()
    action_open_schedule = pyqtSignal()
    action_disconnect_obs = pyqtSignal()
    action_open_settings = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.setProperty("responsive-scroll", True)
        scroll = QScrollArea(self)
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {COLORS['bg_app']}; border: none; }}"
        )

        root_box = QVBoxLayout(self)
        root_box.setContentsMargins(0, 0, 0, 0)
        root_box.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(SPACING["xl"], SPACING["xl"],
                                 SPACING["xl"], SPACING["xl"])
        root.setSpacing(SPACING["lg"])

        root.addWidget(self._build_hero())
        root.addLayout(self._build_kpi_row())
        root.addWidget(self._build_section_label("Acciones rápidas"))
        root.addLayout(self._build_actions_row())
        root.addLayout(self._build_bottom_row(), 1)

    # ------------------------------------------------------------------
    # Hero
    # ------------------------------------------------------------------

    def _build_hero(self) -> QWidget:
        hero = QWidget()
        hero.setObjectName("HomeHero")
        hero.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hero.setStyleSheet(
            f"#HomeHero {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 10px; }}"
        )
        col = QVBoxLayout(hero)
        col.setContentsMargins(SPACING["xl"], SPACING["lg"],
                                SPACING["xl"], SPACING["lg"])
        col.setSpacing(SPACING["xs"])

        kicker = QLabel("BIENVENIDO")
        kicker.setStyleSheet(
            f"background: transparent; color: {COLORS['text_muted']}; "
            "font-size: 11px; font-weight: bold; letter-spacing: 2px;"
        )
        title = QLabel("Centro de control de canales y automatización OBS")
        title.setStyleSheet(
            f"background: transparent; color: {COLORS['text_primary']}; "
            "font-size: 24px; font-weight: bold;"
        )
        title.setWordWrap(True)
        subtitle = QLabel(
            "Administra canales, escenas, programaciones y contenido "
            "automatizado en tus pantallas corporativas con una solución "
            "centralizada, segura y confiable."
        )
        subtitle.setStyleSheet(
            f"background: transparent; color: {COLORS['text_secondary']}; "
            "font-size: 13px;"
        )
        subtitle.setWordWrap(True)

        col.addWidget(kicker)
        col.addWidget(title)
        col.addWidget(subtitle)
        return hero

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    def _build_kpi_row(self) -> QGridLayout:
        row = QGridLayout()
        self._kpi_grid = row
        row.setSpacing(SPACING["md"])

        self.kpi_canales = KpiCard(
            "app_tv", "Canales Activos", "0", "de 0 configurados",
            variant="blue",
        )
        self.kpi_escenas = KpiCard(
            "escenas", "Escenas Programadas", "0", "en la programación",
            variant="red",
        )
        self.kpi_dashboards = KpiCard(
            "monitor_canvas", "Dashboards", "0", "escenas tipo URL",
            variant="blue",
        )
        self.kpi_conexion = KpiCard(
            "conectar", "Estado de Conexión", "—", "Sin conectar",
            variant="green",
        )
        self._kpis = [self.kpi_canales, self.kpi_escenas, self.kpi_dashboards, self.kpi_conexion]
        arrange_grid(row, self._kpis, 4)
        return row

    # ------------------------------------------------------------------
    # Acciones rapidas
    # ------------------------------------------------------------------

    def _build_section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 16px; "
            "font-weight: bold; background: transparent;"
        )
        return lbl

    def _build_actions_row(self) -> QGridLayout:
        row = QGridLayout()
        self._actions_grid = row
        row.setSpacing(SPACING["md"])

        self.btn_new_canal = ActionButton(
            "agregar", "Nuevo Canal", "Crear canal de pantalla",
            variant="primary",
        )
        self.btn_connect = ActionButton(
            "conectar", "Conectar OBS", "Vincular con OBS Studio",
            variant="danger",
        )
        self.btn_import = ActionButton(
            "bajar", "Importar Configuración",
            "Cargar canales y escenas", variant="neutral",
        )
        self.btn_schedule = ActionButton(
            "calendario", "Ver Programación", "Administrar horarios",
            variant="neutral",
        )
        self._actions = [self.btn_new_canal, self.btn_connect, self.btn_import, self.btn_schedule]
        arrange_grid(row, self._actions, 4)

        self.btn_new_canal.clicked.connect(self.action_new_canal.emit)
        self.btn_connect.clicked.connect(self.action_connect_obs.emit)
        self.btn_import.clicked.connect(self.action_import.emit)
        self.btn_schedule.clicked.connect(self.action_open_schedule.emit)
        return row

    # ------------------------------------------------------------------
    # Fila inferior: estado OBS + vista previa de canales
    # ------------------------------------------------------------------

    def _build_bottom_row(self) -> QGridLayout:
        row = QGridLayout()
        self._bottom_grid = row
        row.setSpacing(SPACING["md"])
        row.addWidget(self._build_obs_status_card(), 0, 0)
        self.channels_card = self._build_channels_preview_card()
        row.addWidget(self.channels_card, 0, 1)
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 2)
        return row

    def _build_obs_status_card(self) -> QWidget:
        self.obs_card = ObsStatusCard()
        self.btn_obs_settings = self.obs_card.btn_settings
        self.btn_obs_disconnect = self.obs_card.btn_disconnect
        self.btn_obs_settings.clicked.connect(self.action_open_settings.emit)
        self.btn_obs_disconnect.clicked.connect(self.action_disconnect_obs.emit)
        return self.obs_card

    def _build_channels_preview_card(self) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("HomePreviewsCard")
        wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wrap.setStyleSheet(
            f"#HomePreviewsCard {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 10px; }}"
        )
        col = QVBoxLayout(wrap)
        col.setContentsMargins(SPACING["lg"], SPACING["lg"],
                                SPACING["lg"], SPACING["lg"])
        col.setSpacing(SPACING["md"])

        header = QHBoxLayout()
        title = QLabel("Vista previa de canales")
        title.setStyleSheet(
            f"background: transparent; color: {COLORS['text_primary']}; "
            "font-size: 14px; font-weight: bold;"
        )
        header.addWidget(title)
        header.addStretch(1)
        self.lbl_more = QLabel("")
        self.lbl_more.setStyleSheet(
            f"background: transparent; color: {COLORS['accent_primary']}; "
            "font-size: 12px;"
        )
        header.addWidget(self.lbl_more)
        col.addLayout(header)

        self._channels_row = QGridLayout()
        self._preview_widgets = []
        self._channels_row.setSpacing(SPACING["md"])
        col.addLayout(self._channels_row, 1)
        return wrap

    # ------------------------------------------------------------------
    # API publica (consumida por el HomeController)
    # ------------------------------------------------------------------

    def set_kpi_canales(self, activos: int, total: int) -> None:
        self.kpi_canales.set_value(str(activos))
        self.kpi_canales.set_subtitle(f"de {total} configurados")

    def set_kpi_escenas(self, programadas: int) -> None:
        self.kpi_escenas.set_value(str(programadas))
        self.kpi_escenas.set_subtitle("en la programación")

    def set_kpi_dashboards(self, count: int) -> None:
        self.kpi_dashboards.set_value(str(count))
        self.kpi_dashboards.set_subtitle("escenas tipo URL")

    def set_kpi_conexion(self, connected: bool, version: str = "") -> None:
        if connected:
            self.kpi_conexion.set_value("OK")
            self.kpi_conexion.set_subtitle(version or "Conectado")
        else:
            self.kpi_conexion.set_value("—")
            self.kpi_conexion.set_subtitle("Sin conectar")

    def set_obs_card(self, connected: bool, version: str = "",
                     host: str = "", port: int = 0,
                     scene_count: int | None = None, profile: str = "",
                     connected_seconds: float | None = None) -> None:
        self.obs_card.set_status(connected, version, host, port,
                                 scene_count, profile, connected_seconds)

    def set_channel_previews(self, items: list[tuple[str, str, bool]],
                              total: int) -> None:
        """items: hasta 3 tuplas (nombre, escena_actual, is_live)."""
        self._preview_widgets = []
        # Limpiar previas
        while self._channels_row.count():
            child = self._channels_row.takeAt(0)
            if child and child.widget():
                child.widget().deleteLater()
        if not items:
            empty = QLabel("No hay canales configurados todavía.")
            empty.setStyleSheet(
                f"background: transparent; color: {COLORS['text_muted']}; "
                "font-size: 12px; padding: 24px;"
            )
            self._preview_widgets.append(empty)
        else:
            for name, scene_name, is_live in items[:3]:
                card = ChannelPreviewCard(name, scene_name, is_live)
                self._preview_widgets.append(card)
        self._reflow()
        if total > len(items):
            self.lbl_more.setText(f"Ver todos ({total})")
        else:
            self.lbl_more.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self):
        if not hasattr(self, "_bottom_grid"):
            return
        available = max(1, self.width() - 64)
        columns = 4 if available >= 1040 else 2 if available >= 560 else 1
        arrange_grid(self._kpi_grid, self._kpis, columns)
        arrange_grid(self._actions_grid, self._actions, columns)
        side_by_side = available >= 1040
        arrange_grid(self._bottom_grid, [self.obs_card, self.channels_card], 2 if side_by_side else 1)
        if side_by_side:
            self._bottom_grid.setColumnStretch(0, 1)
            self._bottom_grid.setColumnStretch(1, 2)
        self.obs_card.setMinimumHeight(220)
        self.channels_card.setMinimumHeight(220)
        preview_width = int(available * 2 / 3) - 32 if side_by_side else available - 32
        preview_columns = max(1, min(len(self._preview_widgets), preview_width // 240))
        arrange_grid(self._channels_row, self._preview_widgets, preview_columns)
