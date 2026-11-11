"""Guardia de rueda del mouse (views/widgets/wheel_guard.py); usar QT_QPA_PLATFORM=offscreen.

Verifica:
- Un spinbox / combo / slider protegido SIN foco no cambia con la rueda y la
  rueda llega al QScrollArea (la pagina se desplaza).
- CON foco, la rueda si cambia el valor (comportamiento normal de Qt).
- Un combo editable con el foco en su QLineEdit interno si responde.
- CalendarView protege sus 23 spinboxes y 2 combos.
- Los dialogos ResponsiveDialog (CanalEditDialog, SceneEditDialog,
  CountdownLayoutDialog) quedan protegidos al mostrarse.

Uso: venv\\Scripts\\python.exe scripts\\test_wheel_guard.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QLabel, QScrollArea, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)
from views.widgets.wheel_guard import GUARDED_PROPERTY, guard_wheel, guard_wheel_in


def wheel(widget, delta_y=-120):
    """Envia un tick de rueda al widget. delta negativo = scroll hacia abajo."""
    pos = QPointF(widget.rect().center())
    event = QWheelEvent(
        pos, widget.mapToGlobal(pos.toPoint()).toPointF(),
        QPoint(0, 0), QPoint(0, delta_y),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(widget, event)
    return event


class WheelGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def settle(self):
        for _ in range(10):
            self.app.processEvents()

    def scroll_host(self):
        """QScrollArea con contenido alto + spin/combo/slider protegidos."""
        host = QScrollArea()
        host.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        spin = QSpinBox(); spin.setRange(0, 1000); spin.setValue(50)
        combo = QComboBox(); combo.addItems(["a", "b", "c"]); combo.setCurrentIndex(1)
        slider = QSlider(Qt.Orientation.Horizontal); slider.setRange(0, 1000); slider.setValue(50)
        for w in (spin, combo, slider):
            layout.addWidget(w)
        for _ in range(60):
            layout.addWidget(QLabel("relleno para que la pagina tenga scroll"))
        host.setWidget(content)
        # Se protege el scroll area completo (como hacen las vistas reales):
        # sus QScrollBar deben quedar excluidos o la rueda reenviada al
        # viewport rebotaria en ellos.
        guard_wheel_in(host)
        self.assertFalse(host.verticalScrollBar().property(GUARDED_PROPERTY),
                         "las barras de scroll no se protegen")
        host.resize(400, 300)
        host.show()
        self.addCleanup(host.close)
        self.settle()
        self.assertGreater(host.verticalScrollBar().maximum(), 0, "el host debe tener scroll")
        return host, spin, combo, slider

    def test_unfocused_controls_ignore_wheel_and_page_scrolls(self):
        host, spin, combo, slider = self.scroll_host()
        for widget, value in ((spin, spin.value), (combo, combo.currentIndex), (slider, slider.value)):
            with self.subTest(widget=type(widget).__name__):
                self.assertEqual(widget.focusPolicy(), Qt.FocusPolicy.StrongFocus)
                # Al mostrar la ventana Qt da el foco al primer widget
                # enfocable; lo retiramos para simular "cursor pasa por
                # encima sin haber hecho clic".
                focused = QApplication.focusWidget()
                if focused is not None:
                    focused.clearFocus()
                self.settle()
                self.assertFalse(widget.hasFocus())
                before_value = value()
                before_scroll = host.verticalScrollBar().value()
                wheel(widget, -120)
                self.settle()
                self.assertEqual(value(), before_value, "el valor no debe cambiar sin foco")
                self.assertGreater(host.verticalScrollBar().value(), before_scroll,
                                   "la rueda debe desplazar la pagina")

    def test_focused_spinbox_still_responds_to_wheel(self):
        host, spin, _combo, _slider = self.scroll_host()
        host.activateWindow()
        spin.setFocus()
        self.settle()
        self.assertTrue(spin.hasFocus(), "offscreen debe permitir dar foco al spin")
        wheel(spin, +120)
        self.settle()
        self.assertEqual(spin.value(), 51, "con foco la rueda incrementa 1 paso")

    def test_editable_combo_focused_in_its_line_edit_responds(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        combo = QComboBox(); combo.setEditable(True); combo.addItems(["uno", "dos", "tres"])
        combo.setCurrentIndex(0)
        layout.addWidget(combo)
        guard_wheel(combo)
        host.show(); host.activateWindow()
        self.addCleanup(host.close)
        combo.lineEdit().setFocus()
        self.settle()
        # El foco real vive en el QLineEdit interno; QComboBox lo usa como
        # focus proxy, asi que combo.hasFocus() tambien es True y la guardia
        # deja pasar la rueda.
        self.assertTrue(combo.lineEdit().hasFocus())
        self.assertTrue(combo.hasFocus())
        wheel(combo, -120)
        self.settle()
        self.assertEqual(combo.currentIndex(), 1, "con foco interno la rueda si cambia el item")

    def test_guard_is_idempotent(self):
        spin = QSpinBox()
        guard_wheel(spin)
        self.assertTrue(spin.property(GUARDED_PROPERTY))
        self.assertEqual(guard_wheel_in(spin), 0, "ya protegido: no se cuenta de nuevo")

    def test_calendar_view_protects_all_spinboxes_and_combos(self):
        from views.calendar_view import CalendarView
        view = CalendarView({})
        view.resize(1200, 800)
        view.show()
        self.addCleanup(view.close)
        self.settle()
        focused = QApplication.focusWidget()
        if focused is not None:
            focused.clearFocus()
        self.settle()
        spins = view.findChildren(QSpinBox)
        combos = view.findChildren(QComboBox)
        self.assertEqual(len(spins), 23)
        self.assertEqual(len(combos), 2)
        for w in spins + combos:
            with self.subTest(widget=w.objectName() or w.toolTip()[:30] or type(w).__name__):
                self.assertTrue(w.property(GUARDED_PROPERTY))
                self.assertEqual(w.focusPolicy(), Qt.FocusPolicy.StrongFocus)
        # Secciones 3/4/5 y combo de la seccion 2: la rueda sin foco no toca nada.
        targets = [view.spin_x_start_4w, view.spin_scale_6w, view.spin_dy_row0_5w]
        before = [t.value() for t in targets] + [view.combo_template_weeks.currentIndex()]
        for t in targets + [view.combo_template_weeks]:
            wheel(t, -120)
        self.settle()
        after = [t.value() for t in targets] + [view.combo_template_weeks.currentIndex()]
        self.assertEqual(after, before)

    def test_responsive_dialogs_are_guarded_when_shown(self):
        from views.canal_edit_dialog import CanalEditDialog
        from views.scene_edit_dialog import SceneEditDialog
        canal = CanalEditDialog()
        canal.show(); self.settle()
        self.addCleanup(canal.close)
        self.assertTrue(canal.spin_bitrate.property(GUARDED_PROPERTY))
        wheel(canal.spin_bitrate, -120); self.settle()
        self.assertEqual(canal.spin_bitrate.value(), 2500)
        wheel(canal.cmb_encoder, -120); self.settle()
        self.assertEqual(canal.cmb_encoder.currentIndex(), 0)

        scene = SceneEditDialog(is_new=True)
        scene.show(); self.settle()
        self.addCleanup(scene.close)
        self.assertTrue(scene.input_zoom.property(GUARDED_PROPERTY))
        before = scene.input_zoom.value()
        wheel(scene.input_zoom, -120); self.settle()
        self.assertEqual(scene.input_zoom.value(), before)


if __name__ == '__main__':
    unittest.main()
