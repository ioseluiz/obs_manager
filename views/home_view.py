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
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from views.theme import COLORS, SPACING
from views.widgets import ActionButton, ChannelPreviewCard, KpiCard


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

        scroll = QScrollArea(self)
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
        root.addStretch(1)

    # ------------------------------------------------------------------
    # Hero
    # ------------------------------------------------------------------

    def _build_hero(self) -> QWidget:
        hero = QFrame()
        hero.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hero.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 8px; }}"
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

    def _build_kpi_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
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
        for k in (self.kpi_canales, self.kpi_escenas,
                   self.kpi_dashboards, self.kpi_conexion):
            row.addWidget(k, 1)
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

    def _build_actions_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
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
        for b in (self.btn_new_canal, self.btn_connect,
                   self.btn_import, self.btn_schedule):
            row.addWidget(b, 1)

        self.btn_new_canal.clicked.connect(self.action_new_canal.emit)
        self.btn_connect.clicked.connect(self.action_connect_obs.emit)
        self.btn_import.clicked.connect(self.action_import.emit)
        self.btn_schedule.clicked.connect(self.action_open_schedule.emit)
        return row

    # ------------------------------------------------------------------
    # Fila inferior: estado OBS + vista previa de canales
    # ------------------------------------------------------------------

    def _build_bottom_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(SPACING["md"])
        row.addWidget(self._build_obs_status_card(), 1)
        row.addWidget(self._build_channels_preview_card(), 2)
        return row

    def _build_obs_status_card(self) -> QFrame:
        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 8px; }}"
        )
        col = QVBoxLayout(card)
        col.setContentsMargins(SPACING["lg"], SPACING["lg"],
                                SPACING["lg"], SPACING["lg"])
        col.setSpacing(SPACING["sm"])

        header = QHBoxLayout()
        title = QLabel("Estado de OBS Studio")
        title.setStyleSheet(
            f"background: transparent; color: {COLORS['text_primary']}; "
            "font-size: 14px; font-weight: bold;"
        )
        self.lbl_obs_badge = QLabel("● Desconectado")
        self.lbl_obs_badge.setStyleSheet(
            f"background: transparent; color: {COLORS['state_muted']}; "
            "font-size: 12px; font-weight: bold;"
        )
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.lbl_obs_badge)
        col.addLayout(header)

        self.lbl_obs_version = QLabel("—")
        self.lbl_obs_version.setStyleSheet(
            f"background: transparent; color: {COLORS['text_secondary']}; "
            "font-size: 13px;"
        )
        col.addWidget(self.lbl_obs_version)

        self.lbl_obs_detail = QLabel("Sin información todavía.")
        self.lbl_obs_detail.setStyleSheet(
            f"background: transparent; color: {COLORS['text_muted']}; "
            "font-size: 12px;"
        )
        self.lbl_obs_detail.setWordWrap(True)
        col.addWidget(self.lbl_obs_detail)

        col.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACING["sm"])
        self.btn_obs_settings = ActionButton(
            "configuracion", "Configuración", "Ajustes de conexión",
            variant="neutral",
        )
        self.btn_obs_disconnect = ActionButton(
            "prohibido_desconectado", "Desconectar",
            "Cerrar conexión OBS", variant="neutral",
        )
        btn_row.addWidget(self.btn_obs_settings, 1)
        btn_row.addWidget(self.btn_obs_disconnect, 1)
        col.addLayout(btn_row)

        self.btn_obs_settings.clicked.connect(self.action_open_settings.emit)
        self.btn_obs_disconnect.clicked.connect(self.action_disconnect_obs.emit)
        return card

    def _build_channels_preview_card(self) -> QFrame:
        wrap = QFrame()
        wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        wrap.setStyleSheet(
            f"QFrame {{ background: {COLORS['bg_panel']}; "
            f"border: 1px solid {COLORS['border_default']}; "
            f"border-radius: 8px; }}"
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

        self._channels_row = QHBoxLayout()
        self._channels_row.setSpacing(SPACING["md"])
        col.addLayout(self._channels_row)
        col.addStretch(1)
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
                      scene_count: int = 0) -> None:
        if connected:
            self.lbl_obs_badge.setText("● Conectado")
            self.lbl_obs_badge.setStyleSheet(
                f"background: transparent; color: {COLORS['state_success']}; "
                "font-size: 12px; font-weight: bold;"
            )
            self.lbl_obs_version.setText(
                f"OBS Studio {version}" if version else "OBS Studio"
            )
            lines = []
            if host and port:
                lines.append(f"Dirección:  {host}:{port}")
            if scene_count:
                lines.append(f"Escenas cargadas:  {scene_count}")
            self.lbl_obs_detail.setText("  ·  ".join(lines) if lines else "")
        else:
            self.lbl_obs_badge.setText("● Desconectado")
            self.lbl_obs_badge.setStyleSheet(
                f"background: transparent; color: {COLORS['state_muted']}; "
                "font-size: 12px; font-weight: bold;"
            )
            self.lbl_obs_version.setText("—")
            self.lbl_obs_detail.setText("Sin información todavía.")

    def set_channel_previews(self, items: list[tuple[str, str, bool]],
                              total: int) -> None:
        """items: hasta 3 tuplas (nombre, escena_actual, is_live)."""
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
            self._channels_row.addWidget(empty)
        else:
            for name, scene_name, is_live in items[:3]:
                card = ChannelPreviewCard(name, scene_name, is_live)
                self._channels_row.addWidget(card, 1)
        if total > len(items):
            self.lbl_more.setText(f"Ver todos ({total})")
        else:
            self.lbl_more.setText("")
