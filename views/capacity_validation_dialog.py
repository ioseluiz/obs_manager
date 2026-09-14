"""Diálogo modal para mostrar sobrecarga de capacidad detectada al conectar (Fase 2d).

Se abre cuando `validate_capacity` devuelve `ok=False`. Muestra:
- Título con "n encoders excedidos".
- Tabla comparativa: encoder | usado | capacidad calibrada.
- Lista de sugerencias específicas por encoder.
- Botón "Ir a Producción" (cierra el dialog y trae al foco la pestaña) +
  botón "Ignorar y continuar" (registra en log y sigue).

Regla firme: nunca auto-degrada. El dialog sólo informa.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel, QListWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QFrame,
)


class CapacityValidationDialog(QDialog):
    """Muestra un ValidationResult con overloaded_encoders != []."""

    def __init__(
        self, validation_result, parent=None,
        on_go_to_produccion: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self._result = validation_result
        self._on_go = on_go_to_produccion
        self._setup_ui()

    def _setup_ui(self):
        r = self._result
        self.setWindowTitle("Capacidad excedida")
        self.setModal(True)
        self.resize(720, 480)

        root = QVBoxLayout(self)

        title = QLabel("⚠ Capacidad de encoder excedida")
        f = QFont(); f.setBold(True); f.setPointSize(14)
        title.setFont(f)
        title.setStyleSheet("color: #B02A37;")
        root.addWidget(title)

        subtitle = QLabel(r.reason)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #495057;")
        root.addWidget(subtitle)

        # Tabla comparativa
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.addWidget(QLabel("Comparativa por encoder:"))

        encoders_all = set(r.used_by_encoder.keys()) | set(r.capacity_by_encoder.keys())
        tbl = QTableWidget(len(encoders_all), 3)
        tbl.setHorizontalHeaderLabels(["Encoder", "Usado", "Capacidad"])
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for row, enc in enumerate(sorted(encoders_all)):
            tbl.setItem(row, 0, QTableWidgetItem(enc))
            used = r.used_by_encoder.get(enc, 0)
            cap = r.capacity_by_encoder.get(enc, "?")
            used_item = QTableWidgetItem(f"{used:g}")
            cap_item = QTableWidgetItem(str(cap))
            if enc in r.overloaded_encoders:
                for it in (used_item, cap_item):
                    it.setForeground(Qt.GlobalColor.red)
                # Marcar la fila entera
                for c in range(3):
                    cell = tbl.item(row, c)
                    if cell is None:
                        continue
                    f_bold = cell.font(); f_bold.setBold(True); cell.setFont(f_bold)
            tbl.setItem(row, 1, used_item)
            tbl.setItem(row, 2, cap_item)
        tbl.resizeRowsToContents()
        frame_layout.addWidget(tbl)
        root.addWidget(frame)

        # Sugerencias
        if r.suggestions:
            root.addWidget(QLabel("Sugerencias:"))
            lst = QListWidget()
            for s in r.suggestions:
                lst.addItem(s)
            lst.setWordWrap(True)
            root.addWidget(lst, 1)

        # Botonera
        bb = QDialogButtonBox()
        btn_go = bb.addButton("Ir a Producción", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_ignore = bb.addButton("Ignorar y continuar", QDialogButtonBox.ButtonRole.RejectRole)
        btn_go.clicked.connect(self._on_go_clicked)
        btn_ignore.clicked.connect(self.reject)
        root.addWidget(bb)

    def _on_go_clicked(self):
        if self._on_go is not None:
            try:
                self._on_go()
            except Exception:
                # No romper si el callback falla; el user cerrará manualmente.
                pass
        self.accept()
