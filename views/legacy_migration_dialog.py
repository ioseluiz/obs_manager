"""Dialog para ofrecer la migracion del rotador legacy a un canal.

Se abre al primer launch tras la unificacion si:
- Hay secuencias en la Biblioteca (potencialmente contenido del rotador
  legacy que el user quisiera convertir en un canal).
- El flag `LEGACY_MIGRATION_DONE` no esta marcado en el .env.

Opciones para el user:
- **Convertir**: crea un canal "Canal Legacy" con las secuencias
  seleccionadas como items. Deja flag en "true".
- **Omitir por ahora**: cierra sin marcar flag — el dialog vuelve a
  aparecer en el proximo launch.
- **No volver a preguntar**: marca flag en "true" sin crear canal.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

try:
    from views.theme import COLORS
except Exception:  # pragma: no cover — fallback si theme no esta
    COLORS = {
        "text_primary": "#212529",
        "text_secondary": "#495057",
        "text_muted": "#6C757D",
        "state_warning_bg": "#FFF3CD",
        "state_warning_fg": "#664D03",
    }


class LegacyMigrationDialog(QDialog):
    """Dialog modal para la migracion del rotador legacy."""

    # Resultado publico — el main_controller lee estos atributos tras
    # exec() en lugar de un modelo mas complejo.
    DO_CONVERT = "convert"
    DO_SKIP = "skip"
    DO_NEVER = "never"

    def __init__(self, secuencias: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Convertir rotador legacy a canal")
        self.setMinimumSize(560, 440)
        self._decision = self.DO_SKIP  # default si cierran con X
        self._selected_ids: list[int] = []
        self._canal_name = "Canal Legacy"
        self._udp_url = "udp://127.0.0.1:9001"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Explicacion.
        intro = QLabel(
            f"Detectamos <b>{len(secuencias)} escenas</b> en tu Biblioteca. "
            "Con el nuevo modelo unificado todas las rotaciones se hacen "
            "por canal multi-salida (filtro Source Record → UDP). "
            "Podemos crear un canal con estas escenas como items para "
            "que empieces a usar el nuevo flujo sin perder tu contenido."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"background: {COLORS['state_warning_bg']}; "
            f"color: {COLORS['state_warning_fg']}; "
            "padding: 10px; border-radius: 6px;"
        )
        layout.addWidget(intro)

        # Nombre del canal.
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Nombre del canal:"))
        self.input_name = QLineEdit(self._canal_name)
        name_row.addWidget(self.input_name, 1)
        layout.addLayout(name_row)

        # URL UDP destino.
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("URL destino UDP:"))
        self.input_url = QLineEdit(self._udp_url)
        self.input_url.setToolTip(
            "URL donde se emitira el canal (udp://ip:puerto). "
            "Puedes editarlo luego desde Producción."
        )
        url_row.addWidget(self.input_url, 1)
        layout.addLayout(url_row)

        # Lista de secuencias con checkboxes.
        header = QLabel("Selecciona las escenas a incluir en el canal:")
        header.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-weight: bold;"
        )
        layout.addWidget(header)

        self.list_secuencias = QListWidget()
        self.list_secuencias.setAlternatingRowColors(True)
        for s in secuencias:
            item = QListWidgetItem()
            name = s.get("name") or "(sin nombre)"
            tipo = s.get("tipo") or "?"
            dur = s.get("duration") or 0
            item.setText(f"  {name}  —  {tipo}  —  {dur}s")
            item.setData(Qt.ItemDataRole.UserRole, int(s["id"]))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_secuencias.addItem(item)
        layout.addWidget(self.list_secuencias, 1)

        # Shortcut selectores.
        sel_row = QHBoxLayout()
        self.btn_all = QPushButton("Seleccionar todas")
        self.btn_none = QPushButton("Deseleccionar todas")
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(self.btn_all)
        sel_row.addWidget(self.btn_none)
        sel_row.addStretch(1)
        layout.addLayout(sel_row)

        # Botones de accion.
        btns = QHBoxLayout()
        self.btn_never = QPushButton("No volver a preguntar")
        self.btn_never.setToolTip(
            "Marca el flag para que este dialog no vuelva a aparecer. "
            "No crea canal — el user mantiene el estado actual."
        )
        self.btn_skip = QPushButton("Omitir por ahora")
        self.btn_skip.setToolTip(
            "Cierra sin crear canal. Se vuelve a preguntar en el proximo "
            "launch."
        )
        self.btn_convert = QPushButton("Convertir")
        self.btn_convert.setDefault(True)
        try:
            self.btn_convert.setProperty("role", "success")
            self.btn_skip.setProperty("role", "muted")
            self.btn_never.setProperty("role", "danger")
        except Exception:
            pass
        btns.addWidget(self.btn_never)
        btns.addStretch(1)
        btns.addWidget(self.btn_skip)
        btns.addWidget(self.btn_convert)
        layout.addLayout(btns)

        self.btn_convert.clicked.connect(self._on_convert)
        self.btn_skip.clicked.connect(self._on_skip)
        self.btn_never.clicked.connect(self._on_never)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_secuencias.count()):
            self.list_secuencias.item(i).setCheckState(state)

    def _collect_selected_ids(self) -> list[int]:
        ids: list[int] = []
        for i in range(self.list_secuencias.count()):
            item = self.list_secuencias.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                sid = item.data(Qt.ItemDataRole.UserRole)
                if sid is not None:
                    ids.append(int(sid))
        return ids

    def _on_convert(self) -> None:
        selected = self._collect_selected_ids()
        name = self.input_name.text().strip()
        url = self.input_url.text().strip()
        if not selected:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Convertir",
                "Selecciona al menos una escena para incluir en el canal."
            )
            return
        if not name:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Convertir", "El nombre del canal no puede estar vacio."
            )
            return
        if not url:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Convertir", "La URL UDP no puede estar vacia."
            )
            return
        self._decision = self.DO_CONVERT
        self._selected_ids = selected
        self._canal_name = name
        self._udp_url = url
        self.accept()

    def _on_skip(self) -> None:
        self._decision = self.DO_SKIP
        self.reject()

    def _on_never(self) -> None:
        self._decision = self.DO_NEVER
        self.accept()

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------

    @property
    def decision(self) -> str:
        return self._decision

    @property
    def selected_ids(self) -> list[int]:
        return list(self._selected_ids)

    @property
    def canal_name(self) -> str:
        return self._canal_name

    @property
    def udp_url(self) -> str:
        return self._udp_url
