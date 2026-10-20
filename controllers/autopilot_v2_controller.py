"""Controlador que mantiene el buzon Autopilot v2 publicado desde la app.

Pega los eventos del `CanalController` (apply, start/stop, advance,
set_habilitado) con el `AutopilotClientV2` para que el Lua residente en
OBS reciba:

- Un payload con todos los canales habilitados + handoff por canal cada
  vez que cambia el estado del rotador (debounced 300 ms, con
  bump_version=True para que el Lua recargue).
- Un heartbeat ligero cada 5 s mientras la app esta viva (sin tocar el
  array `canales[]`, solo refresca `app_heartbeat_at`).
- Un ultimo payload con los handoffs actuales en el shutdown de la app.

Fase C del port de Autopilot v1.8 a v2.0.0-beta: solo cubre canales
multi-salida (modo `scene_items`). Canal Principal entra en Fase D.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSlot

from core.autopilot_client import (
    MODE_SCENE_ITEMS,
    AutopilotClientV2,
    AutopilotV2NotInstalled,
)

log = logging.getLogger(__name__)

_FILTER_NAME = "udp_out"  # misma constante que core/output_adapter.py
_HEARTBEAT_INTERVAL_MS = 5000
_DEBOUNCE_PUBLISH_MS = 300


def collect_canales_payload(canal_controller) -> list[dict[str, Any]]:
    """Arma el array `canales[]` del protocolo v2 desde el estado actual
    del `CanalController`.

    Solo incluye canales con `_RotatorState` aplicado (hay escena creada
    en OBS) y habilitados en el modelo. Para cada canal:

    - `modo_rotacion = "scene_items"` (Canal Principal sigue en Fase D).
    - `scene_name` = nombre de la escena contenedora.
    - `filter_name = "udp_out"` (constante del output_adapter).
    - `playlist[]` iterando `_RotatorState.playlist`: resuelve
      `scene_item_id` por `item_to_scene_item` y `name` por join con
      la secuencia en `scene_model`.
    - `handoff` con `active_index` (1-based) + `seconds_remaining`
      actuales desde `get_status`. Si `active_index` es 0 o
      `seconds_remaining` <= 0, el cliente lo filtra solo (bug C del v1).

    Es funcion pura: no toca OBS ni la red, solo lee estructuras en
    memoria + BD local. Testeable headless con mocks.
    """
    canales: list[dict[str, Any]] = []
    rotators = getattr(canal_controller, "_rotators", {}) or {}
    canal_model = getattr(canal_controller, "canal_model", None)
    scene_model = getattr(canal_controller, "scene_model", None)
    if canal_model is None or scene_model is None:
        return canales

    for canal_id, state in rotators.items():
        canal_rec = canal_model.get_canal(canal_id)
        if not canal_rec or not canal_rec.get("habilitado"):
            continue
        scene_name = canal_rec.get("nombre") or state.scene_name or ""
        if not scene_name:
            continue

        # Resolver nombres de secuencia para cada canal_item vivo del
        # rotador. canal_item_id → secuencia_nombre via get_items + get_scene.
        try:
            items_rows = canal_model.get_items(canal_id) or []
        except Exception as e:
            log.debug("canal %s: canal_model.get_items fallo: %s", canal_id, e)
            continue
        item_to_name: dict[int, str] = {}
        for row in items_rows:
            seq_id = row.get("secuencia_id")
            if seq_id is None:
                continue
            try:
                seq = scene_model.get_scene(seq_id)
            except Exception:
                seq = None
            if seq is None:
                continue
            item_to_name[int(row["id"])] = seq.get("name", "") or ""

        playlist: list[dict[str, Any]] = []
        for entry in state.playlist:
            scene_item_id = state.item_to_scene_item.get(entry.item_id, 0)
            if not scene_item_id:
                continue
            playlist.append({
                "name": item_to_name.get(entry.item_id, ""),
                "scene_item_id": int(scene_item_id),
                "duration_seg": int(entry.duration_seg),
                "active_days": int(entry.active_days or 127),
                "active_time_start": entry.time_start or "",
                "active_time_end": entry.time_end or "",
            })

        # Handoff: active_index 1-based + seconds_remaining en segundos.
        status = {}
        try:
            status = canal_controller.get_status(canal_id) or {}
        except Exception as e:
            log.debug("canal %s: get_status fallo: %s", canal_id, e)
        active_index_0b = int(status.get("active_index", -1))
        active_index_1b = active_index_0b + 1 if active_index_0b >= 0 else 0
        remaining_ms = int(status.get("remaining_ms", 0) or 0)
        remaining_sec = int(math.ceil(remaining_ms / 1000.0)) if remaining_ms > 0 else 0

        canal_entry: dict[str, Any] = {
            "canal_id": int(canal_id),
            "modo_rotacion": MODE_SCENE_ITEMS,
            "scene_name": scene_name,
            "filter_name": _FILTER_NAME,
            "playlist": playlist,
            "handoff": {
                "active_index": active_index_1b,
                "seconds_remaining": remaining_sec,
            },
        }
        canales.append(canal_entry)

    return canales


class AutopilotV2Controller(QObject):
    """Pega el `CanalController` con el `AutopilotClientV2`.

    Vive mientras la app esta corriendo. Arranca al conectar OBS, se
    detiene al perder conexion, publica un handoff final al shutdown.
    """

    def __init__(self, autopilot_client: AutopilotClientV2,
                 canal_controller, parent=None):
        super().__init__(parent)
        self._ap = autopilot_client
        self._canal_ctrl = canal_controller
        self._enabled = False
        self._script_present: bool | None = None

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(_HEARTBEAT_INTERVAL_MS)
        self._heartbeat_timer.timeout.connect(self._on_heartbeat_tick)

        self._publish_debouncer = QTimer(self)
        self._publish_debouncer.setSingleShot(True)
        self._publish_debouncer.setInterval(_DEBOUNCE_PUBLISH_MS)
        self._publish_debouncer.timeout.connect(self._on_debounced_publish)

        canal_controller.canal_status_changed.connect(self._on_canal_status_changed)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Arranca heartbeats + publish inicial. Idempotente."""
        if self._enabled:
            return
        self._enabled = True
        # Re-detectar al arrancar: el usuario puede haber instalado el
        # script entre un connect y otro.
        self._script_present = None
        self._do_publish(bump_version=True)
        self._heartbeat_timer.start()
        log.info("AutopilotV2Controller arrancado")

    def stop(self, publish_handoff: bool = False) -> None:
        """Detiene timers. Si `publish_handoff`, publica un ultimo
        payload con los handoffs actuales antes de parar."""
        if not self._enabled and not publish_handoff:
            return
        try:
            if publish_handoff:
                self._do_publish(bump_version=True)
        finally:
            self._enabled = False
            self._heartbeat_timer.stop()
            self._publish_debouncer.stop()
            log.info("AutopilotV2Controller detenido (handoff=%s)",
                     "si" if publish_handoff else "no")

    # ------------------------------------------------------------------
    # Senales
    # ------------------------------------------------------------------

    @pyqtSlot(int, dict)
    def _on_canal_status_changed(self, canal_id: int, status: dict) -> None:
        """Cada cambio relevante en un canal reagenda el publish."""
        if not self._enabled:
            return
        # Restart single-shot: colapsa rafagas (apply + start en el mismo
        # tick, o varios advances casi simultaneos tras un apply_all).
        self._publish_debouncer.start()

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _on_heartbeat_tick(self) -> None:
        if not self._enabled:
            return
        if not self._ensure_script_detected():
            return
        try:
            self._ap.send_heartbeat()
        except Exception as e:
            log.debug("heartbeat v2 fallo: %s", e)

    def _on_debounced_publish(self) -> None:
        if not self._enabled:
            return
        self._do_publish(bump_version=True)

    # ------------------------------------------------------------------
    # Nucleo
    # ------------------------------------------------------------------

    def _ensure_script_detected(self) -> bool:
        """Chequea una vez por arranque si el Lua v2 esta instalado.

        Si no esta, no vuelve a intentar en este ciclo de start/stop —
        el proximo `start()` resetea `_script_present` y re-chequea.
        """
        if self._script_present is None:
            self._script_present = self._ap.is_installed()
            if not self._script_present:
                log.info("Autopilot v2 Lua no detectado en OBS; publish/hb inactivos")
        return self._script_present

    def _do_publish(self, bump_version: bool) -> None:
        if not self._ensure_script_detected():
            return
        try:
            canales = collect_canales_payload(self._canal_ctrl)
        except Exception as e:
            log.warning("collect_canales_payload fallo: %s", e)
            return
        try:
            self._ap.publish_config(canales, bump_version=bump_version)
        except AutopilotV2NotInstalled:
            # OBS cayo entre is_installed y publish; marcar para re-check.
            self._script_present = None
        except Exception as e:
            log.warning("publish_config v2 fallo: %s", e)
