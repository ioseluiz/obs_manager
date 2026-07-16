import logging
import unicodedata

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QSpinBox,
                             QLabel, QHeaderView, QGroupBox, QSlider)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QBrush, QColor, QIcon, QPixmap
from views.schedule_widget import format_schedule_summary

log = logging.getLogger(__name__)

ACTIVE_ROW_BG = QColor("#CCE5FF")  # azul claro, alta legibilidad sobre texto oscuro


def _norm_scene_name(s):
    """Normaliza para comparar nombres de escena: NFC + strip.

    NFC evita falsos negativos si un nombre lleva diacríticos combinantes
    (p. ej. 'N' + U+0303 vs 'Ñ' U+00D1). El strip cubre whitespace en
    extremos que podría filtrarse en algún flujo de guardado.
    """
    if not s:
        return ""
    return unicodedata.normalize("NFC", str(s)).strip()

CSS_PLACEHOLDER = (
    "/* CSS opcional inyectado en la página (dashboards, etc.) */\n"
    "body { background: transparent; margin: 0; overflow: hidden; }\n"
    "::-webkit-scrollbar { display: none; }"
)


class SceneView(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self._active_scene_name = None

        # --- PANEL SUPERIOR: Controles de Reproducción ---
        controls_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ Iniciar Rotador")
        self.btn_start.setStyleSheet("background-color: #198754;")

        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setToolTip("Escena anterior (cancela el countdown actual)")
        self.btn_prev.setStyleSheet("background-color: #6C757D;")
        self.btn_prev.setMaximumWidth(50)
        self.btn_prev.setEnabled(False)

        self.btn_pause = QPushButton("⏸ Pausar")
        self.btn_pause.setToolTip("Congelar el countdown en la escena actual")
        self.btn_pause.setStyleSheet("background-color: #FD7E14;")
        self.btn_pause.setEnabled(False)

        self.btn_next = QPushButton("⏭")
        self.btn_next.setToolTip("Escena siguiente (cancela el countdown actual)")
        self.btn_next.setStyleSheet("background-color: #6C757D;")
        self.btn_next.setMaximumWidth(50)
        self.btn_next.setEnabled(False)

        self.btn_stop = QPushButton("⏹ Detener Rotador")
        self.btn_stop.setStyleSheet("background-color: #DC3545;")
        self.btn_stop.setEnabled(False)

        self.btn_refresh_previews = QPushButton("🔄 Previews")
        self.btn_refresh_previews.setToolTip("Actualizar las miniaturas de todas las escenas")
        self.btn_refresh_previews.setStyleSheet("background-color: #17A2B8;")

        self.lbl_status = QLabel("Estado: Detenido")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #6C757D;")

        self.lbl_date = QLabel("Fecha...")
        self.lbl_date.setStyleSheet("font-weight: bold; color: #495057; font-size: 15px;")
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        controls_layout.addWidget(self.btn_start)
        controls_layout.addWidget(self.btn_prev)
        controls_layout.addWidget(self.btn_pause)
        controls_layout.addWidget(self.btn_next)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addWidget(self.btn_refresh_previews)
        controls_layout.addWidget(self.lbl_status)
        controls_layout.addStretch()
        controls_layout.addWidget(self.lbl_date)

        self.layout.addLayout(controls_layout)

        # --- TABLA DE ESCENAS ---
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Preview", "Nombre de Escena en OBS", "Tipo", "Contenido", "Duración (s)", "Programación"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.hideColumn(0)
        self.table.setColumnWidth(1, 100)
        self.table.setIconSize(QSize(80, 45))
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # Stretch=1 → la tabla absorbe todo el espacio vertical libre
        self.layout.addWidget(self.table, 1)

        # --- FILA DE BOTONES DE ACCIÓN sobre escenas seleccionadas ---
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.btn_add = QPushButton("➕ Agregar Nueva Escena")
        self.btn_add.setStyleSheet("background-color: #198754; color: white; font-weight: bold;")
        self.btn_edit = QPushButton("✏ Editar Seleccionada")
        self.btn_edit.setStyleSheet("background-color: #0D6EFD; color: white;")
        self.btn_duplicate = QPushButton("📋 Duplicar")
        self.btn_duplicate.setToolTip("Clonar la escena seleccionada con todos sus ajustes")
        self.btn_duplicate.setStyleSheet("background-color: #6F42C1; color: white;")
        self.btn_move_up = QPushButton("▲  Subir")
        self.btn_move_up.setToolTip("Mover escena seleccionada hacia arriba en el orden")
        self.btn_move_up.setStyleSheet("background-color: #6C757D; color: white; font-weight: bold;")
        self.btn_move_down = QPushButton("▼  Bajar")
        self.btn_move_down.setToolTip("Mover escena seleccionada hacia abajo en el orden")
        self.btn_move_down.setStyleSheet("background-color: #6C757D; color: white; font-weight: bold;")
        self.btn_delete = QPushButton("🗑 Eliminar Seleccionada")
        self.btn_delete.setStyleSheet("background-color: #DC3545; color: white;")
        action_row.addWidget(self.btn_add)
        action_row.addWidget(self.btn_edit)
        action_row.addWidget(self.btn_duplicate)
        action_row.addWidget(self.btn_move_up)
        action_row.addWidget(self.btn_move_down)
        action_row.addWidget(self.btn_delete)
        self.layout.addLayout(action_row)

        # --- PANEL AJUSTE EN VIVO ---
        self.layout.addWidget(self._build_live_panel(), 0)

    def _build_live_panel(self):
        """Panel de zoom/pan en vivo. Actúa sobre la escena seleccionada en la tabla."""
        group = QGroupBox("Ajuste en vivo (selecciona una escena y arrastra los sliders)")
        group.setMaximumHeight(160)
        outer = QVBoxLayout()
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(2)

        self.live_zoom_slider, self.live_zoom_spin = self._make_live_row(
            outer, "Zoom:", 10, 500, 100, " %"
        )
        self.live_panx_slider, self.live_panx_spin = self._make_live_row(
            outer, "Pan X:", -2000, 2000, 0, " px"
        )
        self.live_pany_slider, self.live_pany_spin = self._make_live_row(
            outer, "Pan Y:", -2000, 2000, 0, " px"
        )

        bottom = QHBoxLayout()
        self.lbl_live_target = QLabel("Sin escena seleccionada")
        self.lbl_live_target.setStyleSheet("color: #6C757D; font-style: italic;")
        bottom.addWidget(self.lbl_live_target, 1)
        self.btn_live_reset = QPushButton("🔄 Reset")
        self.btn_live_reset.setToolTip("Restaurar zoom 100% y pan 0,0")
        self.btn_live_reset.setStyleSheet("background-color: #6C757D;")
        bottom.addWidget(self.btn_live_reset)
        outer.addLayout(bottom)

        group.setLayout(outer)
        self._live_widgets = [
            self.live_zoom_slider, self.live_zoom_spin,
            self.live_panx_slider, self.live_panx_spin,
            self.live_pany_slider, self.live_pany_spin,
        ]
        self._set_live_enabled(False)

        # Linkear slider ↔ spinbox
        self._link_slider_spin(self.live_zoom_slider, self.live_zoom_spin)
        self._link_slider_spin(self.live_panx_slider, self.live_panx_spin)
        self._link_slider_spin(self.live_pany_slider, self.live_pany_spin)

        return group

    def _make_live_row(self, parent_layout, label, mn, mx, default, suffix):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(50)
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(mn, mx)
        slider.setValue(default)
        row.addWidget(slider, 1)
        spin = QSpinBox()
        spin.setRange(mn, mx)
        spin.setValue(default)
        spin.setSuffix(suffix)
        spin.setMinimumWidth(90)
        row.addWidget(spin)
        parent_layout.addLayout(row)
        return slider, spin

    def _link_slider_spin(self, slider, spin):
        """Mantiene slider y spinbox sincronizados. Emite ambas señales normalmente."""
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)

    def _set_live_enabled(self, enabled):
        for w in self._live_widgets:
            w.setEnabled(enabled)
        self.btn_live_reset.setEnabled(enabled)

    def set_live_values(self, zoom_pct, pan_x, pan_y, target_label=None):
        """Carga valores en el panel sin disparar señales (para selección de fila)."""
        for w in self._live_widgets:
            w.blockSignals(True)
        self.live_zoom_slider.setValue(int(zoom_pct))
        self.live_zoom_spin.setValue(int(zoom_pct))
        self.live_panx_slider.setValue(int(pan_x))
        self.live_panx_spin.setValue(int(pan_x))
        self.live_pany_slider.setValue(int(pan_y))
        self.live_pany_spin.setValue(int(pan_y))
        for w in self._live_widgets:
            w.blockSignals(False)
        if target_label is not None:
            self.lbl_live_target.setText(target_label)
        self._set_live_enabled(target_label is not None)

    def clear_live_selection(self):
        self.lbl_live_target.setText("Sin escena seleccionada")
        self._set_live_enabled(False)

    def get_live_values(self):
        return (
            self.live_zoom_spin.value(),
            self.live_panx_spin.value(),
            self.live_pany_spin.value(),
        )

    def set_rotator_state(self, state):
        """state: 'stopped', 'running', 'paused'"""
        if state == "stopped":
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_pause.setText("⏸ Pausar")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_stop.setEnabled(False)
        elif state == "running":
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("⏸ Pausar")
            self.btn_prev.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_stop.setEnabled(True)
        elif state == "paused":
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_pause.setText("▶ Reanudar")
            self.btn_prev.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_stop.setEnabled(True)

    def get_selected_scene_id(self):
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            return int(self.table.item(row, 0).text())
        return None

    def select_row_by_scene_id(self, scene_id):
        """Selecciona la fila cuyo ID coincida (usado tras reorder)."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and int(item.text()) == scene_id:
                self.table.selectRow(row)
                return

    def populate_table(self, scenes, thumbnail_cache=None):
        thumbnail_cache = thumbnail_cache or {}
        self.table.setRowCount(0)
        for row, scene in enumerate(scenes):
            self.table.insertRow(row)
            tipo_label = "🌐 URL" if scene.get("tipo") == "url" else "📁 Archivo"
            contenido = scene.get("contenido") or ""
            schedule_label = format_schedule_summary(
                scene.get("active_days"),
                scene.get("active_time_start"),
                scene.get("active_time_end"),
            )
            self.table.setItem(row, 0, QTableWidgetItem(str(scene["id"])))
            preview_item = QTableWidgetItem()
            pixmap = thumbnail_cache.get(scene["id"])
            if pixmap:
                preview_item.setIcon(QIcon(pixmap))
            else:
                preview_item.setText("—")
                preview_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, preview_item)
            self.table.setItem(row, 2, QTableWidgetItem(scene["name"]))
            self.table.setItem(row, 3, QTableWidgetItem(tipo_label))
            self.table.setItem(row, 4, QTableWidgetItem(contenido))
            self.table.setItem(row, 5, QTableWidgetItem(str(scene["duration"])))
            self.table.setItem(row, 6, QTableWidgetItem(schedule_label))
        self._apply_active_highlight()

    def set_row_preview(self, scene_id, pixmap):
        """Actualiza solo la miniatura de una fila específica sin repopular."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and int(item.text()) == scene_id:
                preview_item = self.table.item(row, 1)
                if preview_item and pixmap:
                    preview_item.setIcon(QIcon(pixmap))
                    preview_item.setText("")
                return

    def highlight_active_scene(self, scene_name):
        """Marca la fila cuya escena está reproduciéndose. None = ninguna."""
        self._active_scene_name = scene_name
        self._apply_active_highlight()

    def _apply_active_highlight(self):
        default_brush = QBrush()
        active_brush = QBrush(ACTIVE_ROW_BG)
        target = _norm_scene_name(self._active_scene_name)
        matched = False
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 2)
            if not name_item:
                continue
            is_active = bool(target) and _norm_scene_name(name_item.text()) == target
            if is_active:
                matched = True
            brush = active_brush if is_active else default_brush
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(brush)
        if target and not matched:
            rows = [self.table.item(r, 2).text()
                    for r in range(self.table.rowCount())
                    if self.table.item(r, 2)]
            log.warning(
                "Highlight sin match. Buscado=%r (len=%d, norm=%r). Filas=%r",
                self._active_scene_name,
                len(self._active_scene_name or ""),
                target, rows,
            )
