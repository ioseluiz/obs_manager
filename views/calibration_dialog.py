"""Diálogo modal de calibración auto (Fase 2c).

Corre `CalibrationEngine.calibrate()` en un `QThread` y traduce sus
eventos a la UI:
- Barra por encoder (0..max_n).
- Log lineal de eventos (QTextEdit read-only).
- Estado global: idle / running / done / error / cancelled.
- Botón Cancelar (mientras running).
- Botón Cerrar (al terminar).

Al finalizar exitosamente, guarda el `CapacityEntry` en el `CapacityRepo`
recibido en el constructor. Si el user cancela, guarda de todas formas
la entry parcial con `notes: 'cancelled by user'` — así el user puede
ver "última calibración: cancelada" en Settings (2e).

No importa `calibration_engine` en el main thread — todo el trabajo
pasa dentro del worker QThread.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout, QFrame, QMessageBox,
)

log = logging.getLogger(__name__)


class _CalibrationWorker(QThread):
    """QThread que corre CalibrationEngine.calibrate.

    Emite signals para cada evento del motor. Recibe un `threading.Event`
    como flag de cancelación que la UI setea al presionar Cancelar.
    """

    event = pyqtSignal(dict)      # cada evento del motor (progress_cb)
    finished_ok = pyqtSignal(object)  # CapacityEntry al terminar OK
    finished_error = pyqtSignal(str)  # excepción string al fallar

    def __init__(self, engine, encoders, fingerprint, cancel_event,
                 parent=None):
        super().__init__(parent)
        self._engine = engine
        self._encoders = list(encoders)
        self._fingerprint = fingerprint
        self._cancel_event = cancel_event

    def run(self):
        try:
            entry = self._engine.calibrate(
                encoders=self._encoders,
                fingerprint=self._fingerprint,
                progress_cb=lambda ev: self.event.emit(ev),
                cancelled=lambda: self._cancel_event.is_set(),
            )
            self.finished_ok.emit(entry)
        except Exception as e:
            log.exception("Calibración falló")
            self.finished_error.emit(str(e))


class CalibrationDialog(QDialog):
    """Diálogo modal que ejecuta y muestra progreso de la calibración."""

    def __init__(
        self, engine, encoders: Iterable[str], fingerprint,
        capacity_repo, parent=None,
    ):
        """
        engine: CalibrationEngine ya construido (con facade real).
        encoders: iterable de shortnames a calibrar.
        fingerprint: Fingerprint del equipo actual.
        capacity_repo: CapacityRepo para persistir el resultado.
        """
        super().__init__(parent)
        self._engine = engine
        self._encoders = list(encoders)
        self._fingerprint = fingerprint
        self._repo = capacity_repo
        self._cancel_event = threading.Event()
        self._worker: _CalibrationWorker | None = None
        self._result_entry = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        self.setWindowTitle("Calibración automática de encoders")
        self.setModal(True)
        self.resize(650, 520)

        root = QVBoxLayout(self)

        # Encabezado explicativo
        header = QLabel(
            "La app va a medir cuántos canales UDP simultáneos aguanta "
            "cada encoder en este equipo. Toma <b>~60 segundos por encoder</b>. "
            "Durante la calibración no se puede transmitir contenido productivo — "
            "usa una escena baseline gris."
        )
        header.setWordWrap(True)
        root.addWidget(header)

        # Info: qué se va a calibrar
        info = QLabel(
            f"Encoders a probar: <b>{', '.join(self._encoders)}</b>  ·  "
            f"Equipo: <b>{self._fingerprint.hostname}</b> "
            f"(OBS {self._fingerprint.obs_major}, "
            f"{self._fingerprint.cpu_threads} threads, "
            f"GPU: {self._fingerprint.gpu[:40]})"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #495057;")
        root.addWidget(info)

        root.addSpacing(8)

        # Estado global
        self.lbl_status = QLabel("Listo para comenzar.")
        f = QFont(); f.setBold(True)
        self.lbl_status.setFont(f)
        root.addWidget(self.lbl_status)

        # Barra global (progreso encoders)
        self.pb_global = QProgressBar()
        self.pb_global.setRange(0, len(self._encoders))
        self.pb_global.setValue(0)
        self.pb_global.setFormat("Encoder %v / %m")
        root.addWidget(self.pb_global)

        # Barra del encoder actual (progreso pasos)
        row = QHBoxLayout()
        self.lbl_current_encoder = QLabel("")
        self.lbl_current_encoder.setMinimumWidth(120)
        row.addWidget(self.lbl_current_encoder)
        self.pb_encoder = QProgressBar()
        self.pb_encoder.setRange(0, self._engine._max_n)
        self.pb_encoder.setValue(0)
        self.pb_encoder.setFormat("Paso %v / %m")
        row.addWidget(self.pb_encoder, 1)
        root.addLayout(row)

        # Log de eventos
        log_frame = QFrame()
        log_frame.setFrameShape(QFrame.Shape.StyledPanel)
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(6, 6, 6, 6)
        log_layout.addWidget(QLabel("Detalles:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFontFamily("Consolas")
        log_layout.addWidget(self.log, 1)
        root.addWidget(log_frame, 1)

        # Botones
        bb = QDialogButtonBox()
        self.btn_start = bb.addButton("▶ Comenzar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_cancel = bb.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_close = bb.addButton("Cerrar", QDialogButtonBox.ButtonRole.DestructiveRole)
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_close.clicked.connect(self._on_close)
        root.addWidget(bb)

    # ------------------------------------------------------------------
    # Slots del ciclo de vida
    # ------------------------------------------------------------------

    def _on_start(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self.btn_start.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.lbl_status.setText("Calibrando…")
        self._cancel_event.clear()

        self._worker = _CalibrationWorker(
            self._engine, self._encoders, self._fingerprint,
            self._cancel_event, parent=self,
        )
        self._worker.event.connect(self._on_event)
        self._worker.finished_ok.connect(self._on_worker_ok)
        self._worker.finished_error.connect(self._on_worker_error)
        self._worker.start()

    def _on_cancel(self):
        if self._worker is None or not self._worker.isRunning():
            return
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText("Cancelando…")
        self._cancel_event.set()

    def _on_close(self):
        # Si el worker sigue corriendo, cancelarlo antes de cerrar.
        if self._worker is not None and self._worker.isRunning():
            self._cancel_event.set()
            self._worker.wait(3000)
        self.accept()

    # ------------------------------------------------------------------
    # Recepción de eventos del motor (via signal)
    # ------------------------------------------------------------------

    def _on_event(self, ev: dict):
        t = ev.get("type")
        if t == "started":
            self._append(f"[start] encoders: {ev.get('encoders')}")
        elif t == "encoder_start":
            enc = ev.get("encoder", "?")
            self.lbl_current_encoder.setText(f"Encoder: {enc}")
            self.pb_encoder.setValue(0)
            self._append(f"[{enc}] iniciando…")
        elif t == "step_start":
            enc = ev.get("encoder", "?")
            n = ev.get("current_n", 0)
            port = ev.get("port", "?")
            self.pb_encoder.setValue(n)
            self._append(f"[{enc}]   paso N={n} en puerto {port}")
        elif t == "step_result":
            enc = ev.get("encoder", "?")
            n = ev.get("current_n", 0)
            lag = ev.get("lag_pct", 0.0)
            ds = ev.get("delta_skipped", 0)
            dt = ev.get("delta_total", 0)
            self._append(
                f"[{enc}]     N={n} → skipped={ds}/{dt} ({lag:.2f}% lag)"
            )
        elif t == "encoder_done":
            enc = ev.get("encoder", "?")
            nmax = ev.get("nmax", 0)
            sat = ev.get("saturated_at_n")
            err = ev.get("error")
            if err:
                self._append(f"[{enc}] ✗ falló: {err}  (nmax=0)")
            elif sat is not None:
                self._append(f"[{enc}] ✓ nmax={nmax}  (saturó en N={sat})")
            else:
                self._append(f"[{enc}] ✓ nmax={nmax}  (no saturó en max_n)")
            self.pb_global.setValue(self.pb_global.value() + 1)
        elif t == "cancelled":
            self._append("[cancelado por el usuario]")
        elif t == "error":
            self._append(f"[error] {ev.get('message')}")
        elif t == "finished":
            self._append("[finalizado]")

    def _on_worker_ok(self, entry):
        self._result_entry = entry
        # Persistir en el repo. Aún si fue cancelación, la entry viene con notes.
        try:
            self._repo.upsert(entry)
            self._append(f"[repo] Guardado en: {self._repo.path}")
        except Exception as e:
            self._append(f"[repo] Error al guardar: {e}")

        cancelled = "cancelled" in (entry.notes or "")
        if cancelled:
            self.lbl_status.setText("Calibración cancelada — resultado parcial guardado.")
        else:
            summary = ", ".join(f"{k}={v}" for k, v in entry.encoders.items())
            self.lbl_status.setText(f"✓ Calibración completa. Resultados: {summary}")

        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)

    def _on_worker_error(self, err_msg: str):
        self._append(f"[FATAL] {err_msg}")
        self.lbl_status.setText("✗ Calibración falló — ver detalles.")
        self.btn_cancel.setEnabled(False)
        self.btn_close.setEnabled(True)
        QMessageBox.warning(
            self, "Calibración falló",
            f"La calibración falló:\n\n{err_msg}\n\n"
            f"Revise la conexión con OBS y que la escena "
            f"'Calibration_Baseline' se pueda crear.",
        )

    # ------------------------------------------------------------------
    # API pública para el caller
    # ------------------------------------------------------------------

    def result_entry(self):
        """Devuelve el CapacityEntry final tras exec(), o None si canceló/erró."""
        return self._result_entry

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append(self, msg: str) -> None:
        self.log.append(msg)
        # Auto-scroll al final
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())
