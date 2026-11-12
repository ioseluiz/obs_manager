"""Diálogo para marcar una o varias escenas de la Biblioteca como items de canal.

Lista con checkboxes (patrón de `views/legacy_migration_dialog.py`), filtro
por nombre, "Seleccionar todas / Ninguna" y un único override de duración
que aplica a todas las marcadas. Las secuencias que ya están en la playlist
se señalan en gris ("ya en el canal ×N") pero no se bloquean: los
duplicados siguen permitidos, como antes.

`get_selections()` devuelve `[(secuencia_id, override_o_None), ...]` en el
orden de la Biblioteca. `get_selection()` se conserva por compatibilidad.
"""
from __future__ import annotations

from views.widgets.responsive_dialog import ResponsiveDialog

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from views.theme.tokens import COLORS

_ROLE_ID = Qt.ItemDataRole.UserRole
_ROLE_DURATION = Qt.ItemDataRole.UserRole.value + 1


class CanalItemPickerDialog(ResponsiveDialog):
    """Marca una o varias `secuencias` (escenas de la Biblioteca) para
    agregarlas como items del canal.

    Args:
        secuencias: dicts con `id`, `name`, `duration` (orden de la Biblioteca).
        existing_counts: secuencia_id -> veces que ya está en la playlist;
            solo se usa para señalarlas en gris.
    """

    def __init__(self, secuencias: list[dict], parent=None,
                 existing_counts: dict[int, int] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Agregar items al canal")
        self.setMinimumSize(480, 460)
        existing_counts = existing_counts or {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Marque las escenas de la Biblioteca que quiere incluir en el canal:"
        ))

        self.input_filter = QLineEdit()
        self.input_filter.setPlaceholderText("Filtrar por nombre…")
        self.input_filter.setClearButtonEnabled(True)
        layout.addWidget(self.input_filter)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        for s in secuencias:
            sid = int(s["id"])
            dur = int(s.get("duration") or 0)
            text = f"{s['name']}   ·   {dur}s"
            item = QListWidgetItem()
            n = int(existing_counts.get(sid, 0))
            if n > 0:
                text += f"   ·   ya en el canal ×{n}"
                item.setForeground(QColor(COLORS["text_muted"]))
                item.setToolTip(
                    f"Ya está {n} {'vez' if n == 1 else 'veces'} en la playlist; "
                    "puede agregarla de nuevo."
                )
            item.setText(text)
            item.setData(_ROLE_ID, sid)
            item.setData(_ROLE_DURATION, dur)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        layout.addWidget(self._list, 1)

        sel_row = QHBoxLayout()
        self.btn_all = QPushButton("Seleccionar todas")
        self.btn_all.setToolTip("Marca las escenas visibles con el filtro actual.")
        self.btn_none = QPushButton("Ninguna")
        self.btn_none.setToolTip("Desmarca todas, incluidas las ocultas por el filtro.")
        self.lbl_count = QLabel()
        self.lbl_count.setProperty("role", "status-muted")
        sel_row.addWidget(self.btn_all)
        sel_row.addWidget(self.btn_none)
        sel_row.addStretch(1)
        sel_row.addWidget(self.lbl_count)
        layout.addLayout(sel_row)

        row = QHBoxLayout()
        row.addWidget(QLabel(
            "Duración override para todas las marcadas "
            "(segundos, 0 = usar la de cada escena):"
        ))
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(0, 3600)
        self.spin_duration.setValue(0)
        row.addWidget(self.spin_duration)
        row.addStretch(1)
        layout.addLayout(row)

        # Directo en el layout raíz: ResponsiveDialog lo fija bajo el scroll.
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.input_filter.textChanged.connect(self._apply_filter)
        self._list.itemChanged.connect(self._update_count)
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        self._update_count()

    # ------------------------------------------------------------------
    # Filtro / selección
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _set_all(self, checked: bool) -> None:
        """Marcar solo afecta a las filas visibles; desmarcar, a todas."""
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._list.count()):
            item = self._list.item(i)
            if checked and item.isHidden():
                continue
            item.setCheckState(state)
        self._update_count()

    def _collect_checked_ids(self) -> list[int]:
        """Ids marcados en orden de lista (= de la Biblioteca), ocultos incluidos."""
        ids: list[int] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                sid = item.data(_ROLE_ID)
                if sid is not None:
                    ids.append(int(sid))
        return ids

    def _update_count(self, *_args) -> None:
        n = len(self._collect_checked_ids())
        self.lbl_count.setText(f"{n} marcada" if n == 1 else f"{n} marcadas")

    def _on_accept(self):
        if not self._collect_checked_ids():
            QMessageBox.warning(self, "Validación", "Marque al menos una escena.")
            return
        self.accept()

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------

    def _override(self) -> int | None:
        value = self.spin_duration.value()
        return value if value > 0 else None

    def get_selections(self) -> list[tuple[int, int | None]]:
        """[(secuencia_id, duracion_override_seg_o_None), ...] en orden de la
        Biblioteca. El override del spin aplica a todas."""
        override = self._override()
        return [(sid, override) for sid in self._collect_checked_ids()]

    def get_selection(self) -> tuple[int, int | None]:
        """Compatibilidad: primera marcada (o la fila actual si no hay
        ninguna marcada). Preferir `get_selections()`."""
        selections = self.get_selections()
        if selections:
            return selections[0]
        item = self._list.currentItem()
        if item is None:
            raise ValueError("No hay escena seleccionada")
        return int(item.data(_ROLE_ID)), self._override()
