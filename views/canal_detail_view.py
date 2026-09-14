"""Panel de detalle rico por canal seleccionado (R-3).

Vive dentro del futuro "Producción" tab (R-4) como el panel central que se
muestra cuando el user selecciona un canal en el sidebar. Ofrece:

- Header: nombre + URL destino + estado (En vivo / Aplicado apagado /
  No aplicado).
- Botón **▶ Transmitir** por canal (toggle habilitado, independiente del
  resto de canales).
- Controles ▶ Play / ⏮ Prev / ⏸ Pause / ⏭ Next / ⏹ Stop del rotador
  (delegan a los métodos de CanalController introducidos en R-1).
- Botón 📡 Aplicar cambios (re-sincroniza escena + items en OBS).
- Playlist del canal con reordenar (▲ ▼) y editar override de duración.
- Item activo mostrado en tiempo real (poll cada 500ms del estado).

Instanciable dentro de `ProduccionView` (R-4) como el panel central para
canales regulares. Canal Principal usa `CanalPrincipalDetailView`.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from views.canal_item_picker_dialog import CanalItemPickerDialog
from views.canal_item_edit_dialog import CanalItemEditDialog


_STATUS_POLL_MS = 500

_ITEM_COL_ORDER = 0
_ITEM_COL_ESCENA = 1
_ITEM_COL_DURACION = 2
_ITEM_COL_SCHEDULE = 3
_ITEM_HEADERS = ["#", "Escena", "Duración", "Horario"]


class CanalDetailView(QWidget):
    """Widget master-detail centralizado de un canal."""

    # Emitida cuando el user edita algo estructural del canal (habilitar,
    # aplicar, cambiar items) para que el sidebar externo refresque.
    canal_changed = pyqtSignal(int)

    def __init__(self, canal_model, scene_model, canal_controller, parent=None):
        super().__init__(parent)
        self.canal_model = canal_model
        self.scene_model = scene_model
        self.canal_controller = canal_controller
        self._canal_id: int | None = None
        self._setup_ui()
        self._connect_signals()
        # Poll de estado (item activo, running/paused) para reflejar cambios
        # del rotador automático.
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(_STATUS_POLL_MS)
        self._status_timer.timeout.connect(self._refresh_status_only)
        self._status_timer.start()
        self._render_empty()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Header
        header_frame = QFrame()
        header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 8, 10, 8)

        self.lbl_nombre = QLabel("—")
        f = QFont()
        f.setBold(True)
        f.setPointSize(14)
        self.lbl_nombre.setFont(f)

        self.lbl_url = QLabel("—")
        self.lbl_url.setStyleSheet("color: #495057;")
        self.lbl_status = QLabel("—")
        self.lbl_status.setStyleSheet("font-weight: bold;")
        self.lbl_active = QLabel("Item activo: —")
        self.lbl_active.setStyleSheet("color: #495057;")

        header_layout.addWidget(self.lbl_nombre)
        header_layout.addWidget(self.lbl_url)
        header_layout.addWidget(self.lbl_status)
        header_layout.addWidget(self.lbl_active)
        root.addWidget(header_frame)

        # Toolbar de transmisión y controles
        toolbar = QHBoxLayout()

        self.btn_transmit = QPushButton("▶ Transmitir")
        self.btn_transmit.setCheckable(True)
        self.btn_transmit.setMinimumHeight(36)
        bold = QFont()
        bold.setBold(True)
        self.btn_transmit.setFont(bold)
        toolbar.addWidget(self.btn_transmit)

        toolbar.addSpacing(20)

        self.btn_play = QPushButton("▶")
        self.btn_play.setToolTip("Iniciar rotador")
        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setToolTip("Item anterior")
        self.btn_pause = QPushButton("⏸")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setToolTip("Pausar / reanudar")
        self.btn_next = QPushButton("⏭")
        self.btn_next.setToolTip("Item siguiente")
        self.btn_stop = QPushButton("⏹")
        self.btn_stop.setToolTip("Detener rotador (oculta todo)")
        for b in (self.btn_play, self.btn_prev, self.btn_pause,
                  self.btn_next, self.btn_stop):
            b.setFixedWidth(46)
            b.setMinimumHeight(32)
            toolbar.addWidget(b)

        toolbar.addStretch(1)

        self.btn_apply = QPushButton("📡 Aplicar cambios en OBS")
        self.btn_apply.setMinimumHeight(32)
        self.btn_apply.setToolTip(
            "Re-sincroniza escena, filtro y scene items en OBS. Útil tras "
            "editar items o si OBS se reinició."
        )
        toolbar.addWidget(self.btn_apply)

        self.btn_diagnose = QPushButton("🔬 Diagnóstico")
        self.btn_diagnose.setMinimumHeight(32)
        self.btn_diagnose.setToolTip(
            "Lee los settings efectivos del filtro udp_out desde OBS. "
            "Útil cuando VLC recibe stream pero ve negro."
        )
        toolbar.addWidget(self.btn_diagnose)
        root.addLayout(toolbar)

        # Playlist frame
        playlist_frame = QFrame()
        playlist_frame.setFrameShape(QFrame.Shape.StyledPanel)
        playlist_layout = QVBoxLayout(playlist_frame)
        playlist_layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_playlist_header = QLabel("Playlist")
        f = QFont(); f.setBold(True)
        self.lbl_playlist_header.setFont(f)
        playlist_layout.addWidget(self.lbl_playlist_header)

        item_toolbar = QHBoxLayout()
        self.btn_add_item = QPushButton("➕ Agregar")
        self.btn_remove_item = QPushButton("➖ Quitar")
        self.btn_up_item = QPushButton("▲")
        self.btn_down_item = QPushButton("▼")
        self.btn_edit_item = QPushButton("✏ Editar duración")
        for b in (self.btn_add_item, self.btn_remove_item, self.btn_up_item,
                  self.btn_down_item, self.btn_edit_item):
            b.setFixedHeight(28)
            item_toolbar.addWidget(b)
        item_toolbar.addStretch(1)
        playlist_layout.addLayout(item_toolbar)

        self.tbl_items = QTableWidget(0, len(_ITEM_HEADERS))
        self.tbl_items.setHorizontalHeaderLabels(_ITEM_HEADERS)
        self.tbl_items.setAlternatingRowColors(True)
        self.tbl_items.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_items.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tbl_items.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tbl_items.verticalHeader().setVisible(False)
        hdr = self.tbl_items.horizontalHeader()
        hdr.setSectionResizeMode(_ITEM_COL_ORDER, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_ITEM_COL_ESCENA, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_ITEM_COL_DURACION, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_ITEM_COL_SCHEDULE, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_items.itemDoubleClicked.connect(lambda _: self._on_edit_item())
        playlist_layout.addWidget(self.tbl_items, 1)

        root.addWidget(playlist_frame, 1)

    def _connect_signals(self):
        self.btn_transmit.toggled.connect(self._on_transmit_toggled)
        self.btn_play.clicked.connect(self._on_play)
        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_pause.toggled.connect(self._on_pause_toggled)
        self.btn_next.clicked.connect(self._on_next)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_diagnose.clicked.connect(self._on_diagnose)

        self.btn_add_item.clicked.connect(self._on_add_item)
        self.btn_remove_item.clicked.connect(self._on_remove_item)
        self.btn_up_item.clicked.connect(lambda: self._on_reorder_item(-1))
        self.btn_down_item.clicked.connect(lambda: self._on_reorder_item(+1))
        self.btn_edit_item.clicked.connect(self._on_edit_item)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def set_canal(self, canal_id: int | None) -> None:
        """Cambia el canal mostrado. `None` deja el panel en blanco."""
        self._canal_id = canal_id
        self.refresh()

    def refresh(self) -> None:
        """Recarga todo el panel desde el modelo + controller."""
        if self._canal_id is None:
            self._render_empty()
            return
        canal = self.canal_model.get_canal(self._canal_id)
        if not canal:
            self._render_empty()
            return
        self.lbl_nombre.setText(canal["nombre"])
        self.lbl_url.setText(f"→ {canal['url_destino']}   ·   encoder: "
                             f"{canal['encoder']} @ {canal['bitrate_kbps']} kbps")
        # Bloquear signal temporalmente para no rebotar el toggle
        self.btn_transmit.blockSignals(True)
        self.btn_transmit.setChecked(bool(canal["habilitado"]))
        self.btn_transmit.blockSignals(False)
        self._refresh_status_only()
        self._refresh_items()
        self._set_controls_enabled(True)

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------

    def _render_empty(self):
        self.lbl_nombre.setText("Sin selección")
        self.lbl_url.setText("Seleccione un canal en el sidebar para ver su detalle.")
        self.lbl_status.setText("")
        self.lbl_active.setText("")
        self.btn_transmit.blockSignals(True)
        self.btn_transmit.setChecked(False)
        self.btn_transmit.blockSignals(False)
        self.tbl_items.setRowCount(0)
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool):
        for w in (self.btn_transmit, self.btn_play, self.btn_prev,
                  self.btn_pause, self.btn_next, self.btn_stop,
                  self.btn_apply, self.btn_diagnose, self.btn_add_item,
                  self.btn_remove_item, self.btn_up_item, self.btn_down_item,
                  self.btn_edit_item):
            w.setEnabled(enabled)

    def _refresh_status_only(self):
        if self._canal_id is None:
            return
        status = self.canal_controller.get_status(self._canal_id)
        if not status.get("applied"):
            self.lbl_status.setText("● No aplicado en OBS")
            self.lbl_status.setStyleSheet("color: #6C757D; font-weight: bold;")
            self.lbl_active.setText("Item activo: —")
        elif status.get("placeholder_visible"):
            self.lbl_status.setText("● Aplicado — placeholder (fuera de ventana)")
            self.lbl_status.setStyleSheet("color: #FD7E14; font-weight: bold;")
            self.lbl_active.setText("Item activo: (placeholder)")
        elif status.get("is_paused"):
            self.lbl_status.setText("● Pausado")
            self.lbl_status.setStyleSheet("color: #FD7E14; font-weight: bold;")
            self.lbl_active.setText(
                self._active_label(status.get("active_item_id"))
                + self._remaining_suffix(status, paused=True)
            )
        elif status.get("rotator_running"):
            self.lbl_status.setText("● En vivo")
            self.lbl_status.setStyleSheet("color: #198754; font-weight: bold;")
            self.lbl_active.setText(
                self._active_label(status.get("active_item_id"))
                + self._remaining_suffix(status, paused=False)
            )
        else:
            self.lbl_status.setText("● Aplicado (apagado)")
            self.lbl_status.setStyleSheet("color: #6C757D; font-weight: bold;")
            self.lbl_active.setText("Item activo: —")
        # Sincronizar botón pause con el estado
        self.btn_pause.blockSignals(True)
        self.btn_pause.setChecked(bool(status.get("is_paused")))
        self.btn_pause.blockSignals(False)

    def _remaining_suffix(self, status: dict, paused: bool) -> str:
        """Formatea ' (Ns restantes)' a partir de remaining_ms del status."""
        ms = status.get("remaining_ms")
        if ms is None or ms <= 0:
            return " (arrancando…)" if not paused else ""
        secs = max(1, ms // 1000)
        return f" ({secs}s restantes)" if not paused else f" ({secs}s pausados)"

    def _active_label(self, active_item_id) -> str:
        if active_item_id is None:
            return "Item activo: —"
        # Buscar el nombre de la escena
        items = self.canal_model.get_items(self._canal_id) if self._canal_id else []
        for it in items:
            if it["id"] == active_item_id:
                seq = self.scene_model.get_scene(it["secuencia_id"])
                name = seq["name"] if seq else f"(secuencia {it['secuencia_id']} borrada)"
                return f"Item activo: {name}"
        return f"Item activo: id={active_item_id}"

    def _refresh_items(self):
        if self._canal_id is None:
            self.tbl_items.setRowCount(0)
            return
        items = self.canal_model.get_items(self._canal_id)
        self.tbl_items.setRowCount(len(items))
        for row, it in enumerate(items):
            # Orden
            self.tbl_items.setItem(
                row, _ITEM_COL_ORDER, QTableWidgetItem(str(row + 1))
            )
            # Escena
            seq = self.scene_model.get_scene(it["secuencia_id"])
            name = seq["name"] if seq else f"(secuencia {it['secuencia_id']} borrada)"
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, int(it["id"]))
            self.tbl_items.setItem(row, _ITEM_COL_ESCENA, name_item)
            # Duración
            override = it["duracion_override_seg"]
            if override is not None:
                dur_text = f"{override} s (override)"
            elif seq:
                dur_text = f"{seq['duration']} s"
            else:
                dur_text = "?"
            self.tbl_items.setItem(row, _ITEM_COL_DURACION, QTableWidgetItem(dur_text))
            # Schedule resumido
            if seq:
                sched = self._schedule_summary(seq)
            else:
                sched = "—"
            self.tbl_items.setItem(row, _ITEM_COL_SCHEDULE, QTableWidgetItem(sched))

    def _schedule_summary(self, secuencia: dict) -> str:
        """Devuelve un resumen legible del schedule de la secuencia."""
        mask = int(secuencia.get("active_days") or 127)
        ts = secuencia.get("active_time_start")
        te = secuencia.get("active_time_end")
        if mask == 127 and (not ts or not te):
            return "Siempre"
        # Nombres cortos por bit
        dias = ["L", "M", "X", "J", "V", "S", "D"]
        activos = "".join(d if (mask & (1 << i)) else "·"
                          for i, d in enumerate(dias))
        if ts and te:
            return f"{activos}  {ts}–{te}"
        return activos

    # ------------------------------------------------------------------
    # Slots — controles del rotador
    # ------------------------------------------------------------------

    def _on_transmit_toggled(self, checked: bool):
        if self._canal_id is None:
            return
        ok, msg = self.canal_controller.set_habilitado(self._canal_id, checked)
        if not ok:
            QMessageBox.warning(self, "Transmisión", msg)
            # Revertir el toggle si falló
            self.btn_transmit.blockSignals(True)
            self.btn_transmit.setChecked(not checked)
            self.btn_transmit.blockSignals(False)
            return
        self.canal_changed.emit(self._canal_id)
        self._refresh_status_only()

    def _on_play(self):
        if self._canal_id is None:
            return
        self.canal_controller.start_rotator(self._canal_id)
        self._refresh_status_only()

    def _on_pause_toggled(self, checked: bool):
        if self._canal_id is None:
            return
        if checked:
            self.canal_controller.pause_rotator(self._canal_id)
        else:
            self.canal_controller.resume_rotator(self._canal_id)
        self._refresh_status_only()

    def _on_prev(self):
        if self._canal_id is None:
            return
        self.canal_controller.prev_item(self._canal_id)
        self._refresh_status_only()

    def _on_next(self):
        if self._canal_id is None:
            return
        self.canal_controller.next_item(self._canal_id)
        self._refresh_status_only()

    def _on_stop(self):
        if self._canal_id is None:
            return
        self.canal_controller.stop_rotator(self._canal_id)
        self._refresh_status_only()

    def _on_apply(self):
        if self._canal_id is None:
            return
        ok, msg = self.canal_controller.apply_canal(self._canal_id)
        if not ok:
            QMessageBox.warning(self, "Aplicar en OBS", msg)
            return
        self.canal_changed.emit(self._canal_id)
        self.refresh()

    def _on_diagnose(self):
        """Muestra los settings efectivos del filtro udp_out en un diálogo.

        Usa la conexión OBS ya autenticada de la app — evita el problema del
        script standalone que falla el auth handshake con Python 3.14.
        """
        if self._canal_id is None:
            return
        result = self.canal_controller.diagnose_filter(self._canal_id)
        if not result.get("ok"):
            err = result.get("error", "razón desconocida")
            QMessageBox.warning(
                self, "Diagnóstico del filtro",
                f"No se pudo leer el filtro udp_out.\n\n{err}\n\n"
                f"Verifique que el canal esté aplicado en OBS "
                f"(📡 Aplicar cambios).",
            )
            return
        settings = result["settings"]
        lines = [
            f"Escena: {result['scene_name']}",
            f"Filtro udp_out habilitado: {result['filter_enabled']}",
            "",
            "SETTINGS EFECTIVOS:",
        ]
        for k in sorted(settings.keys()):
            lines.append(f"  {k:<24} {settings[k]!r}")
        lines.append("")
        # Chequeo de settings clave para stream UDP decodable
        lines.append("CHECKLIST STREAM UDP DECODABLE:")
        checks = [
            ("stream_mode", 1, "streaming ON"),
            ("keyint_sec", None, "keyframes frecuentes — 0 o ausente = malo"),
            ("profile", None, "perfil H.264 — 'high' recomendado"),
            ("tune", None, "'zerolatency' para stream en vivo"),
            ("preset", None, "'veryfast' default OBS"),
        ]
        for key, expected, note in checks:
            val = settings.get(key, "<ausente>")
            ok_mark = "OK " if (key in settings and (
                expected is None or val == expected
            )) else "?? "
            lines.append(f"  {ok_mark}{key} = {val!r}  — {note}")

        # Diálogo con selección/copia
        from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Diagnóstico del filtro udp_out")
        dlg.resize(600, 500)
        v = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setFontFamily("Consolas")
        txt.setPlainText("\n".join(lines))
        v.addWidget(txt)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.exec()

    # ------------------------------------------------------------------
    # Slots — items
    # ------------------------------------------------------------------

    def _selected_item_id(self) -> int | None:
        row = self.tbl_items.currentRow()
        if row < 0:
            return None
        it = self.tbl_items.item(row, _ITEM_COL_ESCENA)
        return int(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _on_add_item(self):
        if self._canal_id is None:
            return
        secuencias = self.scene_model.get_all_scenes()
        if not secuencias:
            QMessageBox.information(
                self, "Agregar item",
                "No hay escenas en la Biblioteca para agregar. "
                "Primero cree escenas.",
            )
            return
        dlg = CanalItemPickerDialog(secuencias, parent=self)
        if dlg.exec() != CanalItemPickerDialog.DialogCode.Accepted:
            return
        secuencia_id, override = dlg.get_selection()
        try:
            self.canal_model.add_item(
                self._canal_id, secuencia_id, duracion_override_seg=override,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al agregar item", str(e))
            return
        self._refresh_items()
        self.canal_changed.emit(self._canal_id)

    def _on_remove_item(self):
        item_id = self._selected_item_id()
        if item_id is None:
            QMessageBox.information(self, "Quitar item", "Seleccione un item primero.")
            return
        confirm = QMessageBox.question(
            self, "Quitar item", "¿Quitar este item del canal?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self.canal_model.remove_item(item_id)
        except Exception as e:
            QMessageBox.critical(self, "Error al quitar item", str(e))
            return
        self._refresh_items()
        self.canal_changed.emit(self._canal_id)

    def _on_reorder_item(self, direction: int):
        item_id = self._selected_item_id()
        if item_id is None:
            return
        if self.canal_model.reorder_item(item_id, direction):
            self._refresh_items()
            self.canal_changed.emit(self._canal_id)

    def _on_edit_item(self):
        item_id = self._selected_item_id()
        if item_id is None:
            QMessageBox.information(
                self, "Editar duración", "Seleccione un item primero."
            )
            return
        items = self.canal_model.get_items(self._canal_id)
        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            return
        seq = self.scene_model.get_scene(item["secuencia_id"])
        if not seq:
            QMessageBox.warning(
                self, "Editar duración",
                "La escena referenciada por este item ya no existe.",
            )
            return
        dlg = CanalItemEditDialog(
            seq["name"], int(seq["duration"]), item["duracion_override_seg"],
            parent=self,
        )
        if dlg.exec() != CanalItemEditDialog.DialogCode.Accepted:
            return
        try:
            self.canal_model.update_item_duracion(item_id, dlg.get_override())
        except Exception as e:
            QMessageBox.critical(self, "Error al editar", str(e))
            return
        self._refresh_items()
        self.canal_changed.emit(self._canal_id)
