"""Guardia de rueda del mouse para controles de valor.

Problema: un QSpinBox / QComboBox / QSlider SIN foco bajo el cursor consume
la rueda del mouse y cambia su valor en vez de dejar que la pagina (el
QScrollArea que lo contiene) se desplace. En vistas como Calendario, donde
los spinboxes aplican el cambio en vivo a OBS y lo persisten en .env, un
tick accidental mientras se hace scroll modifica la calibracion sin que el
operador lo note.

Solucion:
- `focusPolicy = StrongFocus`: la rueda ya no otorga foco (el default de
  QSpinBox/QComboBox es WheelFocus).
- Un event filter compartido que, si el control NO tiene foco, ignora la
  rueda en el control y la entrega directamente al viewport del
  QAbstractScrollArea ancestro mas cercano. Asi la pagina sigue
  desplazandose. (No se reenvia al padre: en Qt 6 los eventos de rueda
  no espontaneos no se propagan hacia arriba.) Con foco (clic previo) la
  rueda funciona como siempre.

Uso:
    from views.widgets import guard_wheel, guard_wheel_in
    guard_wheel_in(self)        # al final del __init__ de una vista/dialogo
    guard_wheel(spin)           # para un widget creado despues
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import (
    QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QApplication,
    QComboBox, QScrollBar, QWidget,
)

GUARDED_TYPES = (QAbstractSpinBox, QComboBox, QAbstractSlider)
GUARDED_PROPERTY = "wheel_guarded"

# QScrollBar hereda de QAbstractSlider pero es justamente el destino final
# de la rueda que reenviamos al viewport: protegerlo provoca recursion
# infinita (viewport -> scrollbar -> filtro -> viewport -> ...).
_EXCLUDED_TYPES = (QScrollBar,)

_guard_instance: "_WheelGuard | None" = None


def _has_focus(widget: QWidget) -> bool:
    """True si el widget o alguno de sus hijos tiene el foco.

    Los QComboBox editables tienen el foco en su QLineEdit interno, por eso
    no basta con `widget.hasFocus()`.
    """
    if widget.hasFocus():
        return True
    focused = QApplication.focusWidget()
    return focused is not None and widget.isAncestorOf(focused)


def _enclosing_scroll_area(widget: QWidget) -> "QAbstractScrollArea | None":
    """QScrollArea (o cualquier QAbstractScrollArea) ancestro mas cercano."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return parent
        parent = parent.parentWidget()
    return None


class _WheelGuard(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._forwarding = False

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.Wheel
                and not self._forwarding
                and isinstance(obj, QWidget)
                and not _has_focus(obj)):
            # No dejamos que el control procese la rueda. La entregamos al
            # viewport del scroll area contenedor para que la pagina se
            # desplace igual que si la rueda hubiera caido fuera del control.
            # `_forwarding` evita re-interceptar la misma rueda si en el
            # camino aparece otro widget protegido.
            area = _enclosing_scroll_area(obj)
            if area is not None:
                self._forwarding = True
                try:
                    QApplication.sendEvent(area.viewport(), event)
                finally:
                    self._forwarding = False
            return True
        return super().eventFilter(obj, event)


def _guard() -> _WheelGuard:
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = _WheelGuard(QApplication.instance())
    return _guard_instance


def guard_wheel(widget: QWidget) -> QWidget:
    """Protege un widget. Idempotente: llamar dos veces no duplica el filtro.

    Las barras de scroll se ignoran (ver `_EXCLUDED_TYPES`).
    """
    if widget.property(GUARDED_PROPERTY) or isinstance(widget, _EXCLUDED_TYPES):
        return widget
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.installEventFilter(_guard())
    widget.setProperty(GUARDED_PROPERTY, True)
    return widget


def guard_wheel_in(root: QWidget) -> int:
    """Protege todos los spinboxes, combos y sliders descendientes de `root`.

    Devuelve cuantos widgets se protegieron en esta llamada (los ya
    protegidos no se cuentan).
    """
    count = 0
    for cls in GUARDED_TYPES:
        for widget in root.findChildren(cls):
            if isinstance(widget, _EXCLUDED_TYPES) or widget.property(GUARDED_PROPERTY):
                continue
            guard_wheel(widget)
            count += 1
    return count
