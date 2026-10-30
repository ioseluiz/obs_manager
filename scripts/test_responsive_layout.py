"""Responsive layout regressions; use QT_QPA_PLATFORM=offscreen."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication, QPushButton, QScrollArea, QVBoxLayout, QWidget
from views.home_view import HomeView
from views.main_window import MainWindow
from views.settings_view import SettingsDialog
from views.scene_edit_dialog import SceneEditDialog
from views.canal_edit_dialog import CanalEditDialog
from views.countdown_view import CountdownEditDialog
from views.styles import LIGHT_THEME_QSS
from views.widgets.responsive_layout import FlowLayout


class ResponsiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        if not QFontDatabase.families():
            for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguiemj.ttf'):
                QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
        cls.app.setStyleSheet(LIGHT_THEME_QSS)

    def settle(self):
        for _ in range(10):
            self.app.processEvents()

    def window(self):
        window = MainWindow()
        home = HomeView()
        window.add_section(home, 'Inicio', 'inicio')
        home.set_channel_previews([('piso 1', '—', False), ('piso 2', '—', False)], 2)
        window.show()
        self.addCleanup(window.close)
        return window, home

    def test_home_bottom_panels_fill_desktop_and_keep_original_proportion(self):
        window, home = self.window()
        window.resize(1920, 1080)
        self.settle()
        viewport = home._scroll.viewport()
        self.assertLessEqual(abs(home.obs_card.geometry().bottom() - (viewport.height() - 25)), 2)
        self.assertAlmostEqual(home.channels_card.width() / home.obs_card.width(), 2, delta=0.08)
        self.assertEqual(home._scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(home._scroll.horizontalScrollBar().maximum(), 0)

    def test_resize_reflows_existing_cards_and_preserves_data(self):
        window, home = self.window()
        home.set_kpi_canales(2, 2)
        for width, height, columns in [(1920, 1080, 4), (800, 600, 2),
                                       (768, 1024, 2), (640, 480, 1), (1920, 1080, 4)]:
            window.resize(width, height)
            self.settle()
            occupied = {home._kpi_grid.getItemPosition(i)[1] for i in range(4)}
            self.assertEqual(len(occupied), columns)
            self.assertEqual(home.kpi_canales.lbl_value.text(), '2')
            self.assertEqual(home._scroll.horizontalScrollBar().maximum(), 0)
            self.assertEqual(len(home._preview_widgets), 2)

    def test_header_and_navigation_remain_accessible_at_minimum_size(self):
        window, _ = self.window()
        window.resize(640, 480)
        self.settle()
        self.assertEqual(window.width(), 640)
        for button in (window.btn_settings, window.btn_connect, window.btn_export, window.btn_import):
            self.assertTrue(button.isVisible())
            self.assertGreaterEqual(button.width(), button.minimumSizeHint().width())
            self.assertTrue(window.header.rect().contains(button.mapTo(window.header, button.rect().bottomRight())))
        self.assertTrue(window.sidebar._compact)
        self.assertEqual(window.sidebar._items[0].toolTip(), 'Inicio')

    def test_flow_wraps_whole_buttons_without_overlaps(self):
        host = QWidget()
        layout = FlowLayout(host)
        buttons = [QPushButton(text) for text in ['Agregar nueva escena', 'Editar seleccionada', 'Eliminar seleccionada']]
        for button in buttons:
            layout.addWidget(button)
        host.resize(260, 160)
        host.show()
        self.addCleanup(host.close)
        self.settle()
        for index, button in enumerate(buttons):
            self.assertGreaterEqual(button.width(), button.minimumSizeHint().width())
            self.assertTrue(host.rect().contains(button.geometry()))
            for other in buttons[index + 1:]:
                self.assertFalse(button.geometry().intersects(other.geometry()))

    def test_settings_keep_values_and_save_button_in_small_dialog(self):
        dialog = SettingsDialog({'host': '192.0.2.10', 'port': 4455, 'password': 'test'})
        before = dialog.get_inputs()
        dialog.resize(400, 360)
        dialog.show()
        self.addCleanup(dialog.close)
        self.settle()
        self.assertEqual(dialog.get_inputs(), before)
        self.assertTrue(dialog.rect().contains(dialog.btn_save.geometry()))
        self.assertGreater(dialog.findChild(QScrollArea).verticalScrollBar().maximum(), 0)

    def test_common_dialogs_can_shrink_without_losing_fields(self):
        for dialog, getter in [
            (SceneEditDialog(is_new=True), 'get_values'),
            (CanalEditDialog(), 'get_data'),
            (CountdownEditDialog({}, [], []), 'get_data'),
        ]:
            before = getattr(dialog, getter)()
            dialog.show()
            self.settle()
            dialog.resize(400, 360)
            self.settle()
            self.assertEqual((dialog.width(), dialog.height()), (400, 360))
            self.assertTrue(dialog.findChildren(QScrollArea))
            self.assertEqual(getattr(dialog, getter)(), before)
            dialog.close()


if __name__ == '__main__':
    unittest.main()
