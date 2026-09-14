"""Pestaña "Producción" — sidebar de canales + panel central por canal (R-4).

Reemplaza las viejas pestañas "Rotador de Escenas" y "Canales Multi-Salida"
con una vista unificada:

- Sidebar (izquierda): lista de canales configurados. El primero, siempre
  presente, es **Canal Principal (Global)** que representa el rotador
  legacy (SceneController + StartRecord de OBS). Los demás son canales
  regulares de la tabla `canales` (Fase 1a-1e).
- Panel central (derecha): un `CanalPrincipalDetailView` o un
  `CanalDetailView` según lo seleccionado.
- Toolbar arriba del sidebar: crear canal / eliminar canal / refrescar.

La vista no habla con OBS ni persiste — delega en `CanalController` (por
canal) o en el callback `on_transmit_toggle` (para Canal Principal).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from views.canal_detail_view import CanalDetailView
from views.canal_principal_detail_view import CanalPrincipalDetailView
from views.canal_edit_dialog import CanalEditDialog


# Sentinel para Canal Principal en la sidebar (siempre en index 0).
_CANAL_PRINCIPAL_ID = -1


class ProduccionView(QWidget):
    """Vista unificada de Canales."""

    def __init__(self, canal_model, scene_model, canal_controller,
                 scene_controller, on_transmit_principal_toggle: Callable[[], None],
                 parent=None):
        super().__init__(parent)
        self.canal_model = canal_model
        self.scene_model = scene_model
        self.canal_controller = canal_controller
        self.scene_controller = scene_controller
        self._on_transmit_principal_toggle = on_transmit_principal_toggle
        # Mapa canal_id -> índice en el QStackedWidget
        self._canal_id_to_stack_index: dict[int, int] = {}
        self._setup_ui()
        self._connect_signals()
        self.refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ----- SIDEBAR -----
        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(4, 4, 4, 4)
        sidebar_layout.setSpacing(6)

        title = QLabel("Canales")
        f = QFont(); f.setBold(True); f.setPointSize(12)
        title.setFont(f)
        sidebar_layout.addWidget(title)

        self.lst_canales = QListWidget()
        self.lst_canales.setAlternatingRowColors(True)
        self.lst_canales.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        sidebar_layout.addWidget(self.lst_canales, 1)

        sidebar_toolbar = QHBoxLayout()
        self.btn_new_canal = QPushButton("➕ Nuevo canal")
        self.btn_edit_canal = QPushButton("✏")
        self.btn_edit_canal.setToolTip("Editar canal seleccionado (nombre, URL, encoder, bitrate)")
        self.btn_edit_canal.setFixedWidth(40)
        self.btn_duplicate_canal = QPushButton("📋")
        self.btn_duplicate_canal.setToolTip(
            "Duplicar canal seleccionado (copia su playlist; arranca deshabilitado)"
        )
        self.btn_duplicate_canal.setFixedWidth(40)
        self.btn_delete_canal = QPushButton("🗑")
        self.btn_delete_canal.setToolTip("Eliminar canal seleccionado")
        self.btn_delete_canal.setFixedWidth(40)
        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("Recargar desde la BD")
        self.btn_refresh.setFixedWidth(40)
        sidebar_toolbar.addWidget(self.btn_new_canal, 1)
        sidebar_toolbar.addWidget(self.btn_edit_canal)
        sidebar_toolbar.addWidget(self.btn_duplicate_canal)
        sidebar_toolbar.addWidget(self.btn_delete_canal)
        sidebar_toolbar.addWidget(self.btn_refresh)
        sidebar_layout.addLayout(sidebar_toolbar)

        splitter.addWidget(sidebar_widget)

        # ----- PANEL CENTRAL -----
        self.stack = QStackedWidget()

        # Index 0: Canal Principal (legacy)
        self.canal_principal_panel = CanalPrincipalDetailView(
            self.scene_controller,
            self._on_transmit_principal_toggle,
        )
        self.stack.addWidget(self.canal_principal_panel)

        # Index 1: panel único CanalDetailView que reasignamos al canal
        # seleccionado — evita crear N panels y sincronizarlos todos.
        self.canal_detail = CanalDetailView(
            self.canal_model, self.scene_model, self.canal_controller,
        )
        self.canal_detail.canal_changed.connect(self._on_detail_changed)
        self.stack.addWidget(self.canal_detail)

        splitter.addWidget(self.stack)

        # Proporción: sidebar chico, panel grande
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([260, 900])

        root.addWidget(splitter, 1)

    def _connect_signals(self):
        self.lst_canales.currentItemChanged.connect(self._on_sidebar_selection)
        self.btn_new_canal.clicked.connect(self._on_new_canal)
        self.btn_edit_canal.clicked.connect(self._on_edit_canal)
        self.btn_duplicate_canal.clicked.connect(self._on_duplicate_canal)
        self.btn_delete_canal.clicked.connect(self._on_delete_canal)
        self.btn_refresh.clicked.connect(self.refresh)

    # ------------------------------------------------------------------
    # Refresh / API pública
    # ------------------------------------------------------------------

    def refresh(self):
        """Reconstruye el sidebar desde la BD, preservando la selección."""
        selected_before = self._selected_canal_id()

        self.lst_canales.blockSignals(True)
        self.lst_canales.clear()
        self._canal_id_to_stack_index.clear()

        # Canal Principal siempre primero
        principal_item = QListWidgetItem("🌐 Canal Principal (Global)")
        principal_item.setData(Qt.ItemDataRole.UserRole, _CANAL_PRINCIPAL_ID)
        self.lst_canales.addItem(principal_item)

        # Canales regulares
        for canal in self.canal_model.get_all_canales():
            estado = "🟢" if canal["habilitado"] else "⚪"
            item = QListWidgetItem(f"{estado}  {canal['nombre']}")
            item.setData(Qt.ItemDataRole.UserRole, int(canal["id"]))
            item.setToolTip(f"{canal['nombre']}\n{canal['url_destino']}")
            self.lst_canales.addItem(item)

        self.lst_canales.blockSignals(False)

        # Restaurar selección o caer en Canal Principal
        self._select_by_canal_id(selected_before if selected_before is not None
                                 else _CANAL_PRINCIPAL_ID)

    def set_transmit_principal_enabled(self, enabled: bool) -> None:
        """Delegado al panel de Canal Principal (usado por MainController al
        conectar/desconectar OBS)."""
        self.canal_principal_panel.set_transmit_enabled(enabled)

    def set_recording_ui_principal(self, active: bool, timecode: str = "00:00:00") -> None:
        """Sincroniza el estado del botón Transmit de Canal Principal."""
        self.canal_principal_panel.set_recording_ui(active, timecode)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _selected_canal_id(self) -> int | None:
        item = self.lst_canales.currentItem()
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _select_by_canal_id(self, canal_id: int) -> None:
        for row in range(self.lst_canales.count()):
            it = self.lst_canales.item(row)
            if int(it.data(Qt.ItemDataRole.UserRole)) == canal_id:
                self.lst_canales.setCurrentRow(row)
                return
        # Si no lo encontramos (canal borrado), volver a Canal Principal
        self.lst_canales.setCurrentRow(0)

    def _on_sidebar_selection(self, current: QListWidgetItem | None, _prev):
        if current is None:
            self.stack.setCurrentIndex(0)
            self.canal_detail.set_canal(None)
            return
        canal_id = int(current.data(Qt.ItemDataRole.UserRole))
        if canal_id == _CANAL_PRINCIPAL_ID:
            self.stack.setCurrentWidget(self.canal_principal_panel)
            self.canal_detail.set_canal(None)  # libera el poll
        else:
            self.canal_detail.set_canal(canal_id)
            self.stack.setCurrentWidget(self.canal_detail)

    def _on_new_canal(self):
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
        except Exception as e:
            QMessageBox.critical(self, "Error al crear canal", str(e))
            return
        self.refresh()
        self._select_by_canal_id(new_id)

    def _on_edit_canal(self):
        canal_id = self._selected_canal_id()
        if canal_id is None or canal_id == _CANAL_PRINCIPAL_ID:
            QMessageBox.information(
                self, "Editar canal",
                "Seleccione un canal regular (Canal Principal se edita en OBS)."
            )
            return
        canal = self.canal_model.get_canal(canal_id)
        if not canal:
            return
        existing = {
            c["nombre"] for c in self.canal_model.get_all_canales()
            if c["id"] != canal_id
        }
        dlg = CanalEditDialog(parent=self, canal=canal, existing_names=existing)
        if dlg.exec() != CanalEditDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            self.canal_model.update_canal(
                canal_id,
                nombre=data["nombre"], url_destino=data["url_destino"],
                encoder=data["encoder"], bitrate_kbps=data["bitrate_kbps"],
                habilitado=data["habilitado"], descripcion=data["descripcion"],
            )
        except Exception as e:
            QMessageBox.critical(self, "Error al editar canal", str(e))
            return
        self.refresh()
        self._select_by_canal_id(canal_id)
        # Si el canal ya estaba aplicado en OBS, re-apply para propagar cambios
        # de URL/encoder/bitrate/etc. sin obligar al user a clickearlo.
        status = self.canal_controller.get_status(canal_id)
        if status.get("applied"):
            self.canal_controller.apply_canal(canal_id)

    def _on_duplicate_canal(self):
        canal_id = self._selected_canal_id()
        if canal_id is None or canal_id == _CANAL_PRINCIPAL_ID:
            QMessageBox.information(
                self, "Duplicar canal",
                "Seleccione un canal regular (Canal Principal no se duplica)."
            )
            return
        try:
            new_id = self.canal_model.duplicate_canal(canal_id)
        except Exception as e:
            QMessageBox.critical(self, "Error al duplicar", str(e))
            return
        self.refresh()
        self._select_by_canal_id(new_id)
        QMessageBox.information(
            self, "Canal duplicado",
            "El canal se duplicó y arranca deshabilitado.\n\n"
            "Revise su URL de destino, ajuste lo necesario y luego "
            "habilite el Transmit desde su panel."
        )

    def _on_delete_canal(self):
        canal_id = self._selected_canal_id()
        if canal_id is None or canal_id == _CANAL_PRINCIPAL_ID:
            QMessageBox.information(
                self, "Eliminar canal",
                "Seleccione un canal regular (Canal Principal no se puede borrar)."
            )
            return
        canal = self.canal_model.get_canal(canal_id)
        if not canal:
            return
        confirm = QMessageBox.question(
            self, "Eliminar canal",
            f"¿Eliminar el canal «{canal['nombre']}» y todos sus items?\n\n"
            "También se quitará su escena contenedora de OBS si está aplicada.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            self.canal_controller.remove_canal_from_obs(canal_id)
        except Exception:
            pass
        try:
            self.canal_model.delete_canal(canal_id)
        except Exception as e:
            QMessageBox.critical(self, "Error al eliminar", str(e))
            return
        self.refresh()
        # Vuelve a Canal Principal tras borrar
        self._select_by_canal_id(_CANAL_PRINCIPAL_ID)

    def _on_detail_changed(self, _canal_id: int):
        """El detail view emite esto tras editar el canal (toggle habilitado,
        apply, add/remove item). Refrescamos el sidebar para actualizar los
        indicadores 🟢/⚪ y los tooltips."""
        self.refresh()
