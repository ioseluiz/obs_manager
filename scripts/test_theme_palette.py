"""El tema claro no depende del modo oscuro del SO; usar QT_QPA_PLATFORM=offscreen.

Simula un equipo con Windows en modo oscuro (esquema Dark + paleta oscura
en la QApplication) y verifica que, tras apply_light_theme(), una lista de
canales y la playlist de un canal se pintan con fondo claro y la fila
seleccionada con texto blanco sobre azul — lo que los operadores veian
negro / ilegible en la v2.1.0 y el rc.1.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication, QListWidget, QTableWidget, QTableWidgetItem, QWidget, QVBoxLayout,
)
from views.theme import COLORS, LIGHT_THEME_QSS, apply_light_theme, build_light_palette


def dark_palette() -> QPalette:
    p = QPalette()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button,
                 QPalette.ColorRole.AlternateBase, QPalette.ColorRole.ToolTipBase):
        p.setColor(role, QColor("#1E1E1E"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText, QPalette.ColorRole.ToolTipText):
        p.setColor(role, QColor("#F0F0F0"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#0D3B66"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#202020"))
    return p


class ThemePaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def settle(self):
        for _ in range(10):
            self.app.processEvents()

    def simulate_dark_os(self):
        hints = self.app.styleHints()
        if hasattr(hints, "setColorScheme"):
            hints.setColorScheme(Qt.ColorScheme.Dark)
        self.app.setStyle("Fusion")
        self.app.setPalette(dark_palette())
        self.app.setStyleSheet("")

    def test_palette_roles_are_light_after_apply(self):
        self.simulate_dark_os()
        self.assertLess(self.app.palette().color(QPalette.ColorRole.Base).lightness(), 80)
        apply_light_theme(self.app)
        pal = self.app.palette()
        self.assertGreater(pal.color(QPalette.ColorRole.Base).lightness(), 240)
        self.assertGreater(pal.color(QPalette.ColorRole.Window).lightness(), 240)
        self.assertLess(pal.color(QPalette.ColorRole.Text).lightness(), 80)
        self.assertEqual(pal.color(QPalette.ColorRole.Highlight).name().upper(), COLORS["accent_primary"].upper())
        self.assertEqual(pal.color(QPalette.ColorRole.HighlightedText).name().upper(), "#FFFFFF")
        hints = self.app.styleHints()
        if hasattr(hints, "colorScheme"):
            # La plataforma offscreen no gestiona esquema y reporta Unknown;
            # lo unico que no puede quedar es Dark.
            self.assertIn(hints.colorScheme(), (Qt.ColorScheme.Light, Qt.ColorScheme.Unknown))
        self.assertEqual(build_light_palette().color(QPalette.ColorRole.Base).name().upper(), COLORS["bg_input"].upper())

    def test_qss_styles_item_views_explicitly(self):
        for needle in ("QListWidget", "::item:selected", "selection-background-color",
                       "selection-color", "QHeaderView::section", "QMenu", "QToolTip"):
            self.assertIn(needle, LIGHT_THEME_QSS)

    def _grab(self, widget):
        widget.resize(360, 160)
        widget.show()
        self.settle()
        return widget.grab().toImage()

    def test_channel_list_and_playlist_render_light_with_readable_selection(self):
        self.simulate_dark_os()
        apply_light_theme(self.app)

        host = QWidget()
        layout = QVBoxLayout(host)
        lst = QListWidget()
        lst.setAlternatingRowColors(True)
        lst.addItems(["🟢  piso 1", "🟢  piso 2", "⚪  piso 3"])
        layout.addWidget(lst)
        self.addCleanup(host.close)
        lst.setCurrentRow(1)
        img = self._grab(host)
        # Fondo de la lista (zona vacia abajo): claro, no negro.
        empty = img.pixelColor(img.width() // 2, img.height() - 8)
        self.assertGreater(empty.lightness(), 230, f"fondo de lista oscuro: {empty.name()}")
        # Fila seleccionada: azul accent, y hay pixeles de texto claro dentro.
        row = lst.visualItemRect(lst.item(1))
        center = lst.viewport().mapTo(host, row.center())
        sel = img.pixelColor(row.right() - 6 + (center.x() - row.center().x()), center.y())
        self.assertEqual(sel.name().upper(), COLORS["accent_primary"].upper(), f"seleccion: {sel.name()}")
        light_pixels = sum(
            1 for x in range(row.left() + 2, row.right() - 2)
            for y in range(row.top() + 2, row.bottom() - 2)
            if img.pixelColor(x + (center.x() - row.center().x()), y + (center.y() - row.center().y())).lightness() > 220
        )
        self.assertGreater(light_pixels, 20, "no hay texto claro sobre la fila seleccionada")

        tbl = QTableWidget(3, 2)
        tbl.setHorizontalHeaderLabels(["Escena", "Duración"])
        for r in range(3):
            tbl.setItem(r, 0, QTableWidgetItem(f"imagen {r + 3}"))
            tbl.setItem(r, 1, QTableWidgetItem("20 s"))
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        host2 = QWidget()
        QVBoxLayout(host2).addWidget(tbl)
        self.addCleanup(host2.close)
        tbl.selectRow(1)
        img2 = self._grab(host2)
        cell = tbl.visualItemRect(tbl.item(1, 1))
        pt = tbl.viewport().mapTo(host2, cell.center())
        sel2 = img2.pixelColor(pt.x() + cell.width() // 3, pt.y())
        self.assertEqual(sel2.name().upper(), COLORS["accent_primary"].upper(), f"fila tabla: {sel2.name()}")
        hdr = tbl.horizontalHeader()
        hp = hdr.mapTo(host2, hdr.rect().center())
        header = img2.pixelColor(hp.x() + 30, hp.y())
        self.assertGreater(header.lightness(), 200, f"cabecera oscura: {header.name()}")


if __name__ == "__main__":
    unittest.main()
