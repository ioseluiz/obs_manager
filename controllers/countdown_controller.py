from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QDialog
import datetime
import logging

from views.countdown_view import (MissingSourcesDialog, CountdownEditDialog,
                                   CountdownLayoutDialog)

log = logging.getLogger(__name__)

SOURCE_KEYS = ("source_dias", "source_horas", "source_minutos", "source_segundos")


class CountdownController:
    def __init__(self, view, model, obs_client):
        self.view = view
        self.model = model
        self.obs_client = obs_client

        self.countdowns = []
        self.is_syncing = False
        # Se marca a True si process_countdowns detecta OBS caído mientras
        # sincronizaba, para reanudar automáticamente al reconectar.
        self._was_syncing_before_disconnect = False

        self.timer = QTimer()
        self.timer.timeout.connect(self.process_countdowns)

        self._connect_signals()
        self.refresh_table()
        self.refresh_from_obs()

    def _connect_signals(self):
        self.view.btn_add.clicked.connect(self.add_countdown)
        self.view.btn_edit.clicked.connect(self.edit_countdown)
        self.view.btn_position.clicked.connect(self.adjust_layout)
        self.view.btn_delete.clicked.connect(self.delete_countdown)
        self.view.btn_toggle_sync.clicked.connect(self.toggle_sync)
        self.view.btn_refresh_sources.clicked.connect(self.refresh_from_obs)
        self.view.table.itemDoubleClicked.connect(lambda _item: self.edit_countdown())

    def refresh_table(self):
        self.countdowns = self.model.get_all_countdowns()
        self.view.populate_table(self.countdowns)

    def refresh_from_obs(self):
        """Puebla combos con lo que OBS reporta, refresca valores en OBS y
        reanuda la sincronización si estaba activa antes de una desconexión.
        """
        if not self.obs_client.client:
            self.view.set_source_choices([])
            self.view.set_scene_choices([])
            return
        self.view.set_source_choices(self.obs_client.list_text_input_names() or [])
        self.view.set_scene_choices(self.obs_client.list_scene_names() or [])

        # Refrescar el valor mostrado en OBS con el tiempo restante actual —
        # evita que queden números viejos entre sesiones o entre stop/start.
        if self.countdowns:
            self.process_countdowns()

        # Auto-reanudar si estábamos sincronizando y OBS se cayó
        if self._was_syncing_before_disconnect and not self.is_syncing:
            self._was_syncing_before_disconnect = False
            log.info("Auto-reanudando sincronización de contadores tras reconexión.")
            self.timer.start(1000)
            self._set_sync_ui(True)

    def add_countdown(self):
        data = {
            "nombre": self.view.in_nombre.text().strip(),
            # ISO format para guardarlo seguro en SQLite
            "fecha_objetivo": self.view.in_fecha.dateTime().toPyDateTime().isoformat(),
            "source_dias": self.view.in_src_dias.currentText().strip(),
            "source_horas": self.view.in_src_horas.currentText().strip(),
            "source_minutos": self.view.in_src_mins.currentText().strip(),
            "source_segundos": self.view.in_src_secs.currentText().strip(),
            "repetir_anual": self.view.in_rep_anual.isChecked(),
            "escena": self.view.in_escena.currentText().strip(),
        }

        if not data["nombre"]:
            QMessageBox.warning(self.view, "Error", "El nombre es requerido.")
            return

        self.model.add_countdown(data)
        self.view.in_nombre.clear()
        self.refresh_table()

    def edit_countdown(self):
        selected_items = self.view.table.selectedItems()
        if not selected_items:
            QMessageBox.information(
                self.view, "Editar", "Selecciona un contador para editar."
            )
            return
        row = selected_items[0].row()
        c_id = int(self.view.table.item(row, 0).text())
        countdown = next((c for c in self.countdowns if c["id"] == c_id), None)
        if not countdown:
            return

        if self.obs_client.client:
            scenes = self.obs_client.list_scene_names() or []
            sources = self.obs_client.list_text_input_names() or set()
        else:
            scenes, sources = [], set()

        dialog = CountdownEditDialog(countdown, scenes, sources, self.view)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        if not data["nombre"]:
            QMessageBox.warning(self.view, "Error", "El nombre es requerido.")
            return

        self.model.update_countdown(c_id, data)
        self.refresh_table()

    def adjust_layout(self):
        selected_items = self.view.table.selectedItems()
        if not selected_items:
            QMessageBox.information(
                self.view, "Ajustar posición",
                "Selecciona un contador."
            )
            return
        row = selected_items[0].row()
        c_id = int(self.view.table.item(row, 0).text())
        countdown = next((c for c in self.countdowns if c["id"] == c_id), None)
        if not countdown:
            return
        if not (countdown.get("escena") or "").strip():
            QMessageBox.warning(
                self.view, "Sin escena",
                "Este contador no tiene una escena asignada. Edítalo primero."
            )
            return
        if not self.obs_client.client:
            QMessageBox.warning(
                self.view, "Sin OBS",
                "Conecta a OBS antes de ajustar la posición."
            )
            return

        dialog = CountdownLayoutDialog(countdown, self.obs_client, self.view)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            vals = dialog.get_values()
            self.model.update_layout(c_id, **vals)
            self.refresh_table()

    def delete_countdown(self):
        selected_items = self.view.table.selectedItems()
        if not selected_items:
            return
        row = selected_items[0].row()
        c_id = int(self.view.table.item(row, 0).text())
        countdown = next((c for c in self.countdowns if c["id"] == c_id), None)
        if not countdown:
            return

        # Fuentes del contador vs. fuentes referenciadas por los demás
        counter_srcs = {(countdown.get(k) or "").strip() for k in SOURCE_KEYS}
        counter_srcs.discard("")

        other_srcs = set()
        for c in self.countdowns:
            if c["id"] == c_id:
                continue
            for k in SOURCE_KEYS:
                v = (c.get(k) or "").strip()
                if v:
                    other_srcs.add(v)
        orphan_srcs = counter_srcs - other_srcs
        shared_srcs = counter_srcs & other_srcs

        msg = f"¿Eliminar el contador '{countdown['nombre']}'?"
        can_delete_in_obs = bool(self.obs_client.client) and orphan_srcs
        if can_delete_in_obs:
            msg += ("\n\nSe eliminarán también estas fuentes de OBS:\n  • "
                    + "\n  • ".join(sorted(orphan_srcs)))
        if shared_srcs:
            msg += ("\n\nEstas fuentes son compartidas con otro contador y se "
                    "mantienen:\n  • " + "\n  • ".join(sorted(shared_srcs)))
        if orphan_srcs and not self.obs_client.client:
            msg += ("\n\nNota: OBS no está conectado, sus fuentes no se "
                    "eliminarán de OBS (sólo del contador).")

        reply = QMessageBox.question(
            self.view, "Confirmar eliminación", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.model.delete_countdown(c_id)

        if can_delete_in_obs:
            for name in orphan_srcs:
                ok, err = self.obs_client.remove_input(name)
                if not ok:
                    log.warning("No se pudo eliminar input '%s': %s", name, err)

        self.refresh_table()
        self.refresh_from_obs()

    def _set_sync_ui(self, syncing):
        self.is_syncing = syncing
        if syncing:
            self.view.btn_toggle_sync.setText("⏹ Detener Sincronización")
            self.view.btn_toggle_sync.setStyleSheet("background-color: #DC3545;")
        else:
            self.view.btn_toggle_sync.setText("▶ Iniciar Sincronización")
            self.view.btn_toggle_sync.setStyleSheet("background-color: #198754;")

    def _stop_sync(self):
        self.timer.stop()
        self._set_sync_ui(False)

    def _required_source_names(self):
        """Nombres únicos y no vacíos de todos los text sources referenciados."""
        names = set()
        for c in self.countdowns:
            for key in SOURCE_KEYS:
                n = (c.get(key) or "").strip()
                if n:
                    names.add(n)
        return names

    def _default_scene_for_sources(self, source_names):
        """Devuelve dict {source_name: escena_sugerida} usando la escena del
        primer contador que referencie cada fuente. Vacío si el contador no
        tiene escena configurada.
        """
        default = {s: "" for s in source_names}
        for c in self.countdowns:
            escena = (c.get("escena") or "").strip()
            if not escena:
                continue
            for key in SOURCE_KEYS:
                src = (c.get(key) or "").strip()
                if src in default and not default[src]:
                    default[src] = escena
        return default

    def _create_missing_sources(self, missing_names):
        """Abre diálogo con asignación source→escena y estilo. Crea en OBS.

        Devuelve True si todas se crearon OK, False si cancelan o alguna falla.
        """
        scene_names = self.obs_client.list_scene_names() or []
        if not scene_names:
            QMessageBox.warning(
                self.view, "Fuentes faltantes en OBS",
                "Las siguientes fuentes no existen en OBS y no se detectaron "
                "escenas donde crearlas:\n\n  • " + "\n  • ".join(missing_names)
                + "\n\nCrea al menos una escena en OBS y reintenta."
            )
            return False

        source_scene_map = self._default_scene_for_sources(missing_names)
        dialog = MissingSourcesDialog(source_scene_map, scene_names, self.view)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False

        assignments = dialog.get_assignments()
        unassigned = [s for s, sc in assignments.items() if not sc]
        if unassigned:
            QMessageBox.warning(
                self.view, "Escena no seleccionada",
                "Falta elegir escena para:\n\n  • " + "\n  • ".join(unassigned)
            )
            return False

        style = dialog.get_style()
        failed = []
        created = set()
        for src, scene in assignments.items():
            ok, msg = self.obs_client.create_text_input(scene, src, style=style)
            if not ok:
                failed.append(f"{src}: {msg}")
            else:
                created.add(src)

        if failed:
            QMessageBox.critical(
                self.view, "Error creando fuentes",
                "No se pudieron crear las siguientes fuentes en OBS:\n\n  • "
                + "\n  • ".join(failed)
            )
            return False

        # Auto-posicionar la fila completa (D H M s) de cada contador afectado
        self._layout_counters_with_created_sources(created)

        self.refresh_from_obs()
        return True

    def _layout_counters_with_created_sources(self, created_source_names):
        """Distribuye en fila las 4 fuentes de cada contador que tenga escena
        definida y al menos una de sus fuentes recién creada, usando el layout
        persistido de ese contador (o defaults si nunca se ajustó).
        """
        if not created_source_names:
            return
        for c in self.countdowns:
            scene = (c.get("escena") or "").strip()
            if not scene:
                continue
            ordered = [(c.get(k) or "").strip() for k in SOURCE_KEYS]
            if not any(s and s in created_source_names for s in ordered):
                continue
            self.obs_client.position_countdown_sources(
                scene, ordered,
                x_pct=int(c.get("pos_x_pct") or 50),
                y_pct=int(c.get("pos_y_pct") or 50),
                spread_pct=int(c.get("spread_pct") or 100),
                scale_pct=int(c.get("scale_pct") or 100),
            )

    def _preflight_check(self):
        """Verifica que existan todos los text sources; ofrece crearlos si no."""
        required = self._required_source_names()
        if not required:
            QMessageBox.warning(
                self.view, "Nada que sincronizar",
                "Ningún contador tiene fuentes OBS configuradas."
            )
            return False

        existing = self.obs_client.list_input_names()
        if existing is None:
            log.warning("Preflight: no se pudo enumerar inputs de OBS; se continúa sin validar.")
            return True

        missing = sorted(required - existing)
        if not missing:
            return True

        if not self._create_missing_sources(missing):
            return False

        existing = self.obs_client.list_input_names()
        if existing is None:
            return True
        still_missing = sorted(required - existing)
        if still_missing:
            QMessageBox.warning(
                self.view, "Fuentes faltantes en OBS",
                "Aún faltan estas fuentes tras el intento de creación:\n\n  • "
                + "\n  • ".join(still_missing)
            )
            return False
        return True

    def toggle_sync(self):
        if self.is_syncing:
            self._stop_sync()
            return

        if not self.obs_client.client:
            QMessageBox.warning(self.view, "Error", "Conecta OBS primero.")
            return

        if not self._preflight_check():
            return

        self.timer.start(1000)
        self._set_sync_ui(True)
        # Escribir el valor actual inmediatamente para no esperar 1 s al tick
        self.process_countdowns()

    def process_countdowns(self):
        if not self.obs_client.client:
            if self.is_syncing:
                log.warning("Sincronización de contadores detenida: OBS no está conectado.")
                self._was_syncing_before_disconnect = True
            self._stop_sync()
            return

        now = datetime.datetime.now()

        for c in self.countdowns:
            try:
                target = datetime.datetime.fromisoformat(c["fecha_objetivo"])

                # Lógica de repetición anual (Como el script Lua original)
                if now > target:
                    if c["repetir_anual"]:
                        # Le sumamos un año a la fecha objetivo temporalmente para el cálculo
                        target = target.replace(year=now.year)
                        if now > target:
                            target = target.replace(year=now.year + 1)
                        diff = target - now
                    else:
                        diff = datetime.timedelta(0) # Se queda en cero
                else:
                    diff = target - now

                # Extracción de tiempo
                dias = diff.days
                horas, remainder = divmod(diff.seconds, 3600)
                minutos, segundos = divmod(remainder, 60)

                # Enviar por WebSocket a OBS con sufijo de unidad (05D, 12H, 34M, 56s)
                if c["source_dias"]: self.obs_client.set_text_source_text(c["source_dias"], f"{dias:02d}D")
                if c["source_horas"]: self.obs_client.set_text_source_text(c["source_horas"], f"{horas:02d}H")
                if c["source_minutos"]: self.obs_client.set_text_source_text(c["source_minutos"], f"{minutos:02d}M")
                if c["source_segundos"]: self.obs_client.set_text_source_text(c["source_segundos"], f"{segundos:02d}s")
            except Exception as e:
                log.error("Fallo procesando contador '%s': %s", c.get("nombre", "?"), e)
