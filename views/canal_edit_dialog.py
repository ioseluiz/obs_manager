"""Diálogo para crear o editar un canal multi-salida."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSpinBox, QVBoxLayout,
)

from PyQt6.QtGui import QValidator

from core.udp_url_params import compose_url, extract_multicast_params


class _OptionalSpinBox(QSpinBox):
    """QSpinBox donde dejar el campo VACIO equivale al minimo (0 = "sin setear").

    Un QSpinBox normal trata el texto vacio como estado intermedio y al
    perder el foco revierte al ultimo valor valido -- borrar "32" dejaba
    "2" y no habia forma de volver a "(sin setear)" salvo teclear 0 o
    bajar con la flecha. Con esta subclase, vacio == minimum().
    """

    def validate(self, text: str, pos: int):
        if text.strip() == "":
            return (QValidator.State.Acceptable, text, pos)
        return super().validate(text, pos)

    def valueFromText(self, text: str) -> int:
        if text.strip() == "":
            return self.minimum()
        return super().valueFromText(text)


ENCODERS = ("x264", "qsv", "nvenc", "amf")

# Presets de resolución soportados: (label mostrado, width, height).
# El label lo ve el user; el ancho/alto se guarda en la DB.
RESOLUTION_PRESETS = (
    ("720p (1280×720)",  1280,  720),
    ("1080p (1920×1080)", 1920, 1080),
    ("1440p (2560×1440)", 2560, 1440),
    ("4K (3840×2160)",    3840, 2160),
)
# Presets de fps
FPS_PRESETS = (30, 60)

# Default para canal nuevo: 1080p30 (baseline de calibración).
_DEFAULT_WIDTH = 1920
_DEFAULT_HEIGHT = 1080
_DEFAULT_FPS = 30


class CanalEditDialog(QDialog):
    """Modal para crear/editar un `canal`.

    Uso::

        # Crear:
        dlg = CanalEditDialog(parent=..., existing_names={"OtroCanal"})
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()   # dict listo para CanalModel.add_canal

        # Editar:
        dlg = CanalEditDialog(parent=..., canal=canal_dict,
                              existing_names={n for n in ... if n != canal["nombre"]})
        ...

    `existing_names` es el conjunto de nombres ocupados (excepto el propio
    canal si se está editando) para validar unicidad antes de aceptar.
    """

    def __init__(self, parent=None, canal: dict | None = None,
                 existing_names: set[str] | None = None):
        super().__init__(parent)
        self._existing_names = existing_names or set()
        self._is_edit = canal is not None
        self.setWindowTitle("Editar Canal" if self._is_edit else "Nuevo Canal")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setContentsMargins(10, 10, 10, 10)

        self.ed_nombre = QLineEdit()
        self.ed_nombre.setPlaceholderText("Ej.: Piso3-Lobby")
        form.addRow("Nombre / escena OBS:", self.ed_nombre)

        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText("udp://192.168.1.100:9998")
        form.addRow("URL de destino:", self.ed_url)

        # Params multicast opcionales. Se persisten como query params
        # dentro de url_destino -- zero cambios de schema. Valor 0 = no
        # agregar a la URL (SpecialValueText los muestra como "(sin setear)").
        lbl_multicast = QLabel("<b>Parametros multicast (opcional)</b>")
        lbl_multicast.setStyleSheet("color: #495057; margin-top: 4px;")
        form.addRow("", lbl_multicast)

        self.spin_ttl = _OptionalSpinBox()
        self.spin_ttl.setRange(0, 255)
        self.spin_ttl.setSpecialValueText("(sin setear)")
        self.spin_ttl.setValue(0)
        self.spin_ttl.setToolTip(
            "TTL (Time To Live) del paquete UDP. Tipico 32 para cross-subnet "
            "en multicast. Deja el campo vacio o en 0 para no agregarlo a la URL."
        )
        form.addRow("TTL:", self.spin_ttl)

        self.spin_pkt_size = _OptionalSpinBox()
        self.spin_pkt_size.setRange(0, 9000)
        self.spin_pkt_size.setSingleStep(4)
        self.spin_pkt_size.setSpecialValueText("(sin setear)")
        self.spin_pkt_size.setValue(0)
        self.spin_pkt_size.setToolTip(
            "Tamano de paquete UDP en bytes. Tipico 1316 para MPEG-TS "
            "(7 paquetes TS de 188 bytes). Deja el campo vacio o en 0 para "
            "no agregarlo a la URL."
        )
        form.addRow("pkt_size:", self.spin_pkt_size)

        self.cmb_encoder = QComboBox()
        for e in ENCODERS:
            self.cmb_encoder.addItem(e)
        form.addRow("Encoder:", self.cmb_encoder)

        self.spin_bitrate = QSpinBox()
        self.spin_bitrate.setRange(500, 50000)
        self.spin_bitrate.setSingleStep(500)
        self.spin_bitrate.setSuffix(" kbps")
        self.spin_bitrate.setValue(2500)
        form.addRow("Bitrate:", self.spin_bitrate)

        # Resolución y FPS explícitos por canal (Fase 2 Opción B completa).
        # Los valores se guardan en output_width/output_height/output_fps y
        # se propagan al filtro Source Record en OBS + al validador de
        # capacidad (720p30 cuesta 0.5, 1080p60 cuesta 2, etc.).
        self.cmb_resolution = QComboBox()
        for label, w, h in RESOLUTION_PRESETS:
            self.cmb_resolution.addItem(label, (w, h))
        form.addRow("Resolución:", self.cmb_resolution)

        self.cmb_fps = QComboBox()
        for fps in FPS_PRESETS:
            self.cmb_fps.addItem(f"{fps} fps", fps)
        form.addRow("FPS:", self.cmb_fps)

        self.lbl_cost_hint = QLabel("")
        self.lbl_cost_hint.setStyleSheet("color: #495057; font-style: italic;")
        self.lbl_cost_hint.setWordWrap(True)
        form.addRow("", self.lbl_cost_hint)
        # Reactivo: al cambiar resolución/fps, actualizar el hint de costo
        self.cmb_resolution.currentIndexChanged.connect(self._refresh_cost_hint)
        self.cmb_fps.currentIndexChanged.connect(self._refresh_cost_hint)

        self.chk_habilitado = QCheckBox("Habilitado (arranca la transmisión al aplicar)")
        self.chk_habilitado.setChecked(True)
        form.addRow("", self.chk_habilitado)

        self.ed_descripcion = QLineEdit()
        self.ed_descripcion.setPlaceholderText("Opcional")
        form.addRow("Descripción:", self.ed_descripcion)

        layout.addLayout(form)

        # Hint sobre unicidad
        hint = QLabel(
            "El nombre debe ser único — se usa como nombre de la escena "
            "contenedora en OBS."
        )
        hint.setStyleSheet("color: #6C757D; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Botones
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Prefill si es edición
        if canal:
            self.ed_nombre.setText(canal.get("nombre", ""))
            # La URL en BD puede traer `?ttl=...&pkt_size=...` embebido.
            # La separamos para mostrar la URL base en ed_url y los params
            # en sus propios spinners. Al guardar, se recomponen.
            base_url, ttl_str, pkt_str = extract_multicast_params(
                canal.get("url_destino", "")
            )
            self.ed_url.setText(base_url)
            try:
                self.spin_ttl.setValue(int(ttl_str) if ttl_str else 0)
            except (ValueError, TypeError):
                self.spin_ttl.setValue(0)
            try:
                self.spin_pkt_size.setValue(int(pkt_str) if pkt_str else 0)
            except (ValueError, TypeError):
                self.spin_pkt_size.setValue(0)
            enc = canal.get("encoder", "x264")
            if enc in ENCODERS:
                self.cmb_encoder.setCurrentText(enc)
            self.spin_bitrate.setValue(int(canal.get("bitrate_kbps", 2500)))
            self.chk_habilitado.setChecked(bool(canal.get("habilitado", True)))
            self.ed_descripcion.setText(canal.get("descripcion") or "")
            self._select_resolution(
                int(canal.get("output_width") or _DEFAULT_WIDTH),
                int(canal.get("output_height") or _DEFAULT_HEIGHT),
            )
            self._select_fps(int(canal.get("output_fps") or _DEFAULT_FPS))
        else:
            self._select_resolution(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
            self._select_fps(_DEFAULT_FPS)
        # Poblar el hint inicial
        self._refresh_cost_hint()

    def _select_resolution(self, width: int, height: int) -> None:
        """Selecciona la resolución en el combo. Si no coincide con presets,
        usa 1080p como fallback."""
        for i in range(self.cmb_resolution.count()):
            w, h = self.cmb_resolution.itemData(i)
            if w == width and h == height:
                self.cmb_resolution.setCurrentIndex(i)
                return
        # Fallback: buscar el más cercano por alto
        for i in range(self.cmb_resolution.count()):
            _w, h = self.cmb_resolution.itemData(i)
            if h == _DEFAULT_HEIGHT:
                self.cmb_resolution.setCurrentIndex(i)
                return

    def _select_fps(self, fps: int) -> None:
        for i in range(self.cmb_fps.count()):
            if self.cmb_fps.itemData(i) == fps:
                self.cmb_fps.setCurrentIndex(i)
                return
        # Fallback a 30
        self.cmb_fps.setCurrentIndex(0)

    def _refresh_cost_hint(self) -> None:
        """Actualiza el hint 'este canal cuesta X unidades de calibración'."""
        from core.capacity_validator import _derive_preset
        from core.calibration_engine import budget_cost
        w, h = self.cmb_resolution.currentData()
        fps = self.cmb_fps.currentData()
        preset = _derive_preset({"output_height": h, "output_fps": fps})
        cost = budget_cost(preset)
        if cost == 1.0:
            self.lbl_cost_hint.setText(
                f"Costo de este canal: {cost:g} unidad "
                f"(baseline — capacidad nmax del encoder)."
            )
        else:
            self.lbl_cost_hint.setText(
                f"Costo de este canal: {cost:g} unidades "
                f"({'más liviano' if cost < 1 else 'más pesado'} que 1080p30)."
            )

    def _on_accept(self):
        nombre = self.ed_nombre.text().strip()
        url = self.ed_url.text().strip()

        if not nombre:
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio.")
            return
        if not url:
            QMessageBox.warning(self, "Validación", "La URL de destino es obligatoria.")
            return
        if not url.startswith(("udp://", "rtmp://", "rtmps://", "srt://")):
            QMessageBox.warning(
                self, "Validación",
                "La URL debe empezar con udp://, rtmp://, rtmps:// o srt://.",
            )
            return
        if nombre in self._existing_names:
            QMessageBox.warning(
                self, "Validación",
                f"Ya existe un canal con el nombre '{nombre}'.",
            )
            return
        self.accept()

    def get_data(self) -> dict:
        width, height = self.cmb_resolution.currentData()
        # Componer url_destino: URL base + ttl/pkt_size si estan setados.
        # Valores 0 = no agregar query param (SpecialValueText "(sin setear)").
        base_url = self.ed_url.text().strip()
        ttl_val = self.spin_ttl.value()
        pkt_val = self.spin_pkt_size.value()
        url_destino = compose_url(
            base_url,
            ttl=str(ttl_val) if ttl_val > 0 else "",
            pkt_size=str(pkt_val) if pkt_val > 0 else "",
        )
        return {
            "nombre": self.ed_nombre.text().strip(),
            "url_destino": url_destino,
            "encoder": self.cmb_encoder.currentText(),
            "bitrate_kbps": int(self.spin_bitrate.value()),
            "habilitado": self.chk_habilitado.isChecked(),
            "descripcion": self.ed_descripcion.text().strip() or None,
            "output_width": int(width),
            "output_height": int(height),
            "output_fps": int(self.cmb_fps.currentData()),
        }
