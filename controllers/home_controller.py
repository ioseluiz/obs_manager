"""Controller de la pestana Inicio.

Alimenta la HomeView con datos reales de los modelos:

- Canales Activos: CanalModel.get_all_canales() + flag `habilitado`.
- Escenas Programadas: SceneModel.get_all_scenes() filtradas por
  `active_days` != 127 o ventanas horarias definidas.
- Dashboards: scenes con `tipo == "url"`.
- Estado Conexion: OBSClient.client is not None + version/host del
  settings_model.

Refresco: cada 5 segundos. Fuentes son todas locales (SQLite + un
flag en el OBSClient wrapper) — no hace WebSocket calls, es barato.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QTimer

log = logging.getLogger(__name__)

REFRESH_INTERVAL_MS = 5000


class HomeController(QObject):
    def __init__(self, view, canal_model, scene_model, obs_client,
                 settings_model, canal_controller, parent=None):
        super().__init__(parent)
        self._view = view
        self._canal_model = canal_model
        self._scene_model = scene_model
        self._obs_client = obs_client
        self._settings_model = settings_model
        self._canal_controller = canal_controller

        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        # Un refresco inicial para que la pestana no arranque con ceros.
        self.refresh()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        try:
            self._refresh_kpis()
            self._refresh_obs_card()
            self._refresh_channel_previews()
        except Exception as e:
            log.debug("HomeController.refresh fallo: %s", e)

    def _refresh_kpis(self) -> None:
        canales = self._canal_model.get_all_canales() or []
        activos = sum(1 for c in canales if c.get("habilitado"))
        self._view.set_kpi_canales(activos, len(canales))

        scenes = self._scene_model.get_all_scenes() or []
        # Escena "programada" = tiene ventana horaria o dias restringidos.
        def _is_scheduled(s: dict) -> bool:
            if s.get("active_time_start") or s.get("active_time_end"):
                return True
            days = s.get("active_days")
            # 127 = todos los dias (bitmask completo). 0 u otros valores
            # distintos cuentan como programacion restringida.
            if days is None:
                return False
            try:
                days_int = int(days)
            except (TypeError, ValueError):
                return False
            return days_int not in (0, 127)
        programadas = sum(1 for s in scenes if _is_scheduled(s))
        self._view.set_kpi_escenas(programadas)

        dashboards = sum(1 for s in scenes if (s.get("tipo") or "") == "url")
        self._view.set_kpi_dashboards(dashboards)

        connected = bool(getattr(self._obs_client, "client", None))
        self._view.set_kpi_conexion(connected, "Conectado" if connected else "")

    def _refresh_obs_card(self) -> None:
        connected = bool(getattr(self._obs_client, "client", None))
        settings = {}
        try:
            settings = self._settings_model.get_settings() or {}
        except Exception:
            pass
        host = str(settings.get("host") or "")
        try:
            port = int(settings.get("port") or 0)
        except (TypeError, ValueError):
            port = 0

        scene_count = 0
        if connected:
            try:
                scene_count = len(self._obs_client.list_scene_names() or [])
            except Exception:
                scene_count = 0

        self._view.set_obs_card(
            connected=connected, version="",
            host=host, port=port, scene_count=scene_count,
        )

    def _refresh_channel_previews(self) -> None:
        canales = self._canal_model.get_all_canales() or []
        habilitados = [c for c in canales if c.get("habilitado")]
        items: list[tuple[str, str, bool]] = []
        for c in habilitados[:3]:
            cid = c.get("id")
            name = c.get("nombre") or ""
            scene_actual = "—"
            is_live = False
            try:
                status = self._canal_controller.get_status(int(cid)) if cid is not None else {}
            except Exception:
                status = {}
            if status and status.get("applied"):
                is_live = bool(status.get("rotator_running"))
                # active_item_id es el canal_item_id del rotador. No se
                # resuelve a nombre de escena aqui para no sobrecargar
                # — en Fase 5c/7 el preview_worker puede inyectar la
                # miniatura real + nombre resuelto. Por ahora mostramos
                # el nombre del canal como fallback.
                scene_actual = name
            items.append((name, scene_actual, is_live))
        self._view.set_channel_previews(items, total=len(habilitados))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._timer.stop()
