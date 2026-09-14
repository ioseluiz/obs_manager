"""Vista de gestión de canales multi-salida.

Master-detail:
- Panel superior: tabla de canales configurados con toolbar de acciones
  (crear, editar, eliminar, aplicar a OBS, toggle habilitado).
- Panel inferior: playlist (canal_items) del canal seleccionado con
  botones para agregar / quitar / reordenar.

La vista es delgada — orquestra pero no persiste ni habla con OBS. Delega
a `CanalController` (para OBS) y a `CanalModel` (para persistencia).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QSizePolicy, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from views.canal_edit_dialog import CanalEditDialog
from views.canal_item_picker_dialog import CanalItemPickerDialog


_COL_NOMBRE = 0
_COL_URL = 1
_COL_ENCODER = 2
_COL_BITRATE = 3
_COL_HABILITADO = 4
_COL_ESTADO = 5

_CANAL_HEADERS = [
    "Nombre", "URL destino", "Encoder", "Bitrate", "Habilitado", "Estado OBS",
]

_ITEM_HEADERS = ["#", "Escena", "Duración (s)"]


class CanalView(QWidget):
    """Tab de canales multi-salida (Fase 1)."""

    # Emitida cuando el user hace algo que requiere refrescar el status de
    # canales en OBS (arranque, tras applies, etc.). El main controller la
    # conecta si quiere logging global.
    status_refreshed = pyqtSignal()

    def __init__(self, canal_model, scene_model, canal_controller, parent=None):
        super().__init__(parent)
        self.canal_model = canal_model
        self.scene_model = scene_model
        self.canal_controller = canal_controller
        self._current_canal_id: int | None = None
        self._setup_ui()
        self._connect_signals()
        self.refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # --- Header ---
        header = QHBoxLayout()
        title = QLabel("Canales Multi-Salida")
        f = QFont()
        f.setBold(True)
        f.setPointSize(12)
        title.setFont(f)
        header.addWidget(title)
        header.addStretch(1)
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #6C757D;")
        header.addWidget(self.lbl_status)
        root.addLayout(header)

        # --- Splitter master/detail ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_canales_panel())
        splitter.addWidget(self._build_items_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

    def _build_canales_panel(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        # Toolbar
        toolbar = QHBoxLayout()
        self.btn_nuevo = QPushButton("➕ Nuevo canal")
        self.btn_editar = QPushButton("✏ Editar")
        self.btn_eliminar = QPushButton("🗑 Eliminar")
        self.btn_aplicar = QPushButton("📡 Aplicar a OBS")
        self.btn_aplicar.setToolTip(
            "Crea/actualiza la escena contenedora en OBS, adjunta el filtro "
            "y sincroniza los items del canal seleccionado."
        )
        self.btn_refrescar = QPushButton("🔄 Refrescar")
        for b in (self.btn_nuevo, self.btn_editar, self.btn_eliminar,
                  self.btn_aplicar, self.btn_refrescar):
            b.setFixedHeight(30)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        # Tabla
        self.tbl_canales = QTableWidget(0, len(_CANAL_HEADERS))
        self.tbl_canales.setHorizontalHeaderLabels(_CANAL_HEADERS)
        self.tbl_canales.setAlternatingRowColors(True)
        self.tbl_canales.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_canales.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tbl_canales.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tbl_canales.verticalHeader().setVisible(False)
        hdr = self.tbl_canales.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NOMBRE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_URL, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_ENCODER, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_BITRATE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_HABILITADO, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ESTADO, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tbl_canales, 1)

        return frame

    def _build_items_panel(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_items_header = QLabel("Playlist del canal seleccionado")
        f = QFont()
        f.setBold(True)
        self.lbl_items_header.setFont(f)
        layout.addWidget(self.lbl_items_header)

        # Toolbar items
        item_toolbar = QHBoxLayout()
        self.btn_add_item = QPushButton("➕ Agregar")
        self.btn_remove_item = QPushButton("➖ Quitar")
        self.btn_up_item = QPushButton("▲ Subir")
        self.btn_down_item = QPushButton("▼ Bajar")
        for b in (self.btn_add_item, self.btn_remove_item,
                  self.btn_up_item, self.btn_down_item):
            b.setFixedHeight(28)
            item_toolbar.addWidget(b)
        item_toolbar.addStretch(1)
        layout.addLayout(item_toolbar)

        # Tabla items
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
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.tbl_items, 1)

        return frame

    def _connect_signals(self):
        self.btn_nuevo.clicked.connect(self._on_nuevo_canal)
        self.btn_editar.clicked.connect(self._on_editar_canal)
        self.btn_eliminar.clicked.connect(self._on_eliminar_canal)
        self.btn_aplicar.clicked.connect(self._on_aplicar_canal)
        self.btn_refrescar.clicked.connect(self.refresh)
        self.tbl_canales.itemSelectionChanged.connect(self._on_canal_selection)
        self.tbl_canales.itemDoubleClicked.connect(lambda _i: self._on_editar_canal())

        self.btn_add_item.clicked.connect(self._on_add_item)
        self.btn_remove_item.clicked.connect(self._on_remove_item)
        self.btn_up_item.clicked.connect(lambda: self._on_reorder_item(-1))
        self.btn_down_item.clicked.connect(lambda: self._on_reorder_item(+1))

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self):
        """Recarga tabla de canales + items del actual desde el modelo."""
        canales = self.canal_model.get_all_canales()
        self.tbl_canales.blockSignals(True)
        self.tbl_canales.setRowCount(len(canales))
        for row, c in enumerate(canales):
            self._fill_canal_row(row, c)
        self.tbl_canales.blockSignals(False)

        # Restaurar selección si el canal previo sigue existiendo
        if self._current_canal_id is not None:
            for row in range(self.tbl_canales.rowCount()):
                item = self.tbl_canales.item(row, _COL_NOMBRE)
                if item and int(item.data(Qt.ItemDataRole.UserRole)) == self._current_canal_id:
                    self.tbl_canales.selectRow(row)
                    break
            else:
                self._current_canal_id = None

        self.lbl_status.setText(f"{len(canales)} canal(es) configurados")
        self._refresh_items()

    def _fill_canal_row(self, row: int, canal: dict):
        # Nombre (guarda canal_id en UserRole)
        it_nombre = QTableWidgetItem(canal["nombre"])
        it_nombre.setData(Qt.ItemDataRole.UserRole, int(canal["id"]))
        self.tbl_canales.setItem(row, _COL_NOMBRE, it_nombre)

        self.tbl_canales.setItem(row, _COL_URL, QTableWidgetItem(canal["url_destino"]))
        self.tbl_canales.setItem(row, _COL_ENCODER, QTableWidgetItem(canal["encoder"]))
        self.tbl_canales.setItem(
            row, _COL_BITRATE, QTableWidgetItem(f"{canal['bitrate_kbps']} kbps")
        )

        # Habilitado como checkbox widget en la celda
        chk = QCheckBox()
        chk.setChecked(bool(canal["habilitado"]))
        chk.stateChanged.connect(
            lambda st, cid=int(canal["id"]): self._on_toggle_habilitado(cid, st)
        )
        # Envolver en QWidget para centrar
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        h.addWidget(chk)
        h.addStretch(1)
        self.tbl_canales.setCellWidget(row, _COL_HABILITADO, wrap)

        # Estado OBS — pregunta al controller
        status = self.canal_controller.get_status(int(canal["id"]))
        if not status.get("applied"):
            estado_txt = "No aplicado"
            color = "#6C757D"
        elif status.get("rotator_running"):
            estado_txt = "En vivo"
            color = "#198754"
        else:
            estado_txt = "Aplicado (apagado)"
            color = "#FD7E14"
        it_estado = QTableWidgetItem(estado_txt)
        it_estado.setForeground(Qt.GlobalColor.darkGray)
        self.tbl_canales.setItem(row, _COL_ESTADO, it_estado)

    def _refresh_items(self):
        cid = self._current_canal_id
        if cid is None:
            self.tbl_items.setRowCount(0)
            self.lbl_items_header.setText("Playlist — (seleccione un canal)")
            return

        canal = self.canal_model.get_canal(cid)
        self.lbl_items_header.setText(
            f"Playlist del canal «{canal['nombre'] if canal else '?'}»"
        )

        items = self.canal_model.get_items(cid)
        self.tbl_items.setRowCount(len(items))
        for row, it in enumerate(items):
            # Orden (#)
            self.tbl_items.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            # Escena — resolver el nombre desde scene_model
            seq = self.scene_model.get_scene(it["secuencia_id"])
            seq_name = seq["name"] if seq else f"(secuencia {it['secuencia_id']} eliminada)"
            name_item = QTableWidgetItem(seq_name)
            name_item.setData(Qt.ItemDataRole.UserRole, int(it["id"]))  # item_id
            self.tbl_items.setItem(row, 1, name_item)
            # Duración (override o default)
            override = it["duracion_override_seg"]
            if override is not None:
                dur_text = f"{override} (override)"
            elif seq:
                dur_text = f"{seq['duration']}"
            else:
                dur_text = "?"
            self.tbl_items.setItem(row, 2, QTableWidgetItem(dur_text))

    # ------------------------------------------------------------------
    # Slots de canales
    # ------------------------------------------------------------------

    def _selected_canal_id(self) -> int | None:
        row = self.tbl_canales.currentRow()
        if row < 0:
            return None
        item = self.tbl_canales.item(row, _COL_NOMBRE)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _on_canal_selection(self):
        self._current_canal_id = self._selected_canal_id()
        self._refresh_items()

    def _on_nuevo_canal(self):
        existing = {c["nombre"] for c in self.canal_model.get_all_canales()}
        dlg = CanalEditDialog(parent=self, existing_names=existing)
        if dlg.exec() != CanalEditDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            new_id = self.canal_model.add_canal(
                nombre=data["nombre"], url_destino=data["url_destino"],
                encoder=data["encoder"], bitrate_kbps=data["bitrate_kbps"],
                habilitado=data["habilitado"], descripcion=data["descripcion"],
            )
            self._current_canal_id = new_id
        except Exception as e:
            QMessageBox.critical(self, "Error al crear canal", str(e))
            return
        self.refresh()

    def _on_editar_canal(self):
        cid = self._selected_canal_id()
        if cid is None:
            QMessageBox.information(self, "Editar", "Seleccione un canal primero.")
            return
        canal = self.canal_model.get_canal(cid)
        if not canal:
            return
        existing = {
            c["nombre"] for c in self.canal_model.get_all_canales()
            if c["id"] != cid
        }
        dlg = CanalEditDialog(parent=self, canal=canal, existing_names=existing)
        if dlg.exec() != CanalEditDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            self.canal_model.update_canal(
                cid,
                nombre=data["nombre"], url_destino=data["url_destino"],
                encoder=data["encoder"], bitrate_kbps=data["bitrate_kbps"],
                habilitado=data["habilitado"], descripcion=data["descripcion"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al editar canal", str(e))
            return
        self.refresh()

    def _on_eliminar_canal(self):
        cid = self._selected_canal_id()
        if cid is None:
            QMessageBox.information(self, "Eliminar", "Seleccione un canal primero.")
            return
        canal = self.canal_model.get_canal(cid)
        if not canal:
            return
        confirm = QMessageBox.question(
            self, "Eliminar canal",
            f"¿Eliminar el canal «{canal['nombre']}» y todos sus items?\n\n"
            "También intentaré quitar la escena contenedora de OBS si está aplicada.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        # Intentar limpiar OBS primero (no fatal si falla)
        try:
            self.canal_controller.remove_canal_from_obs(cid)
        except Exception:
            pass
        try:
            self.canal_model.delete_canal(cid)
        except Exception as e:
            QMessageBox.critical(self, "Error al eliminar", str(e))
            return
        self._current_canal_id = None
        self.refresh()

    def _on_aplicar_canal(self):
        cid = self._selected_canal_id()
        if cid is None:
            QMessageBox.information(self, "Aplicar", "Seleccione un canal primero.")
            return
        ok, msg = self.canal_controller.apply_canal(cid)
        if not ok:
            QMessageBox.warning(self, "Aplicar canal", msg)
        self.refresh()
        self.status_refreshed.emit()

    def _on_toggle_habilitado(self, canal_id: int, state: int):
        habilitado = state == Qt.CheckState.Checked.value
        ok, msg = self.canal_controller.set_habilitado(canal_id, habilitado)
        if not ok:
            QMessageBox.warning(self, "Toggle habilitado", msg)
        # No hacemos refresh() completo — dispararía cambios en el widget que
        # emitió el evento. Solo refrescamos el estado OBS del row afectado.
        for row in range(self.tbl_canales.rowCount()):
            item = self.tbl_canales.item(row, _COL_NOMBRE)
            if item and int(item.data(Qt.ItemDataRole.UserRole)) == canal_id:
                canal = self.canal_model.get_canal(canal_id)
                if canal:
                    # Update sólo columna estado — evita rebuild del checkbox
                    status = self.canal_controller.get_status(canal_id)
                    if status.get("applied"):
                        txt = "En vivo" if status.get("rotator_running") else "Aplicado (apagado)"
                    else:
                        txt = "No aplicado"
                    self.tbl_canales.item(row, _COL_ESTADO).setText(txt)
                break

    # ------------------------------------------------------------------
    # Slots de items
    # ------------------------------------------------------------------

    def _selected_item_id(self) -> int | None:
        row = self.tbl_items.currentRow()
        if row < 0:
            return None
        it = self.tbl_items.item(row, 1)  # columna escena guarda item_id
        return int(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _on_add_item(self):
        cid = self._selected_canal_id()
        if cid is None:
            QMessageBox.information(self, "Agregar item", "Seleccione un canal primero.")
            return
        secuencias = self.scene_model.get_all_scenes()
        if not secuencias:
            QMessageBox.information(
                self, "Agregar item",
                "No hay escenas en el Rotador para agregar. "
                "Primero cree escenas en la pestaña Rotador.",
            )
            return
        dlg = CanalItemPickerDialog(secuencias, parent=self)
        if dlg.exec() != CanalItemPickerDialog.DialogCode.Accepted:
            return
        secuencia_id, override = dlg.get_selection()
        try:
            self.canal_model.add_item(cid, secuencia_id, duracion_override_seg=override)
        except Exception as e:
            QMessageBox.critical(self, "Error al agregar item", str(e))
            return
        self._refresh_items()

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

    def _on_reorder_item(self, direction: int):
        item_id = self._selected_item_id()
        if item_id is None:
            return
        if self.canal_model.reorder_item(item_id, direction):
            self._refresh_items()
