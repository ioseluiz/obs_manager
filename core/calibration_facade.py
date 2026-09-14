"""Facade real que implementa ObsFacade contra el OBSClient de la app (Fase 2c).

Traduce las 5 operaciones que necesita `CalibrationEngine` al vocabulario
de obs-websocket v5, usando el cliente ya autenticado de la app. Aisla
al motor de calibration_engine.py del detalle de obsws-python.

Diseño:
- Usa `obs_client._raw_client()` para bypass del `_GuardedClient` — igual
  patrón que `CanalController` para operaciones estructurales (crear/borrar
  escenas y filtros).
- Reusa `core.output_adapter.build_settings` para armar los settings del
  filtro Source Record — así los canales de calibración usan la MISMA
  config que los productivos (mismos keyframe_sec, profile, tune, preset).
- Idempotente: si la escena/filtro ya existe, no rompe.
"""
from __future__ import annotations

import logging
from typing import Any

from core.output_adapter import build_settings, FILTER_KIND

log = logging.getLogger(__name__)


class RealObsFacade:
    """Implementa `ObsFacade` para el motor de calibración."""

    def __init__(self, obs_client):
        """
        obs_client: instancia de `models.obs_client.OBSClient` YA conectada.
            El facade usará su `_raw_client()` para las operaciones.
        """
        self._obs = obs_client

    def _client(self):
        """Devuelve el ReqClient crudo — igual patrón que CanalController."""
        if hasattr(self._obs, "_raw_client"):
            return self._obs._raw_client()
        return self._obs.client

    # ------------------------------------------------------------------
    # Baseline scene (color source neutro 1920x1080)
    # ------------------------------------------------------------------

    def ensure_baseline_scene(self, scene_name: str, input_name: str) -> None:
        """Crea la escena baseline con un color source dentro si no existe."""
        c = self._client()
        # 1. Escena
        try:
            c.create_scene(scene_name)
            log.info("Baseline scene '%s' creada", scene_name)
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg or "600" in msg:
                log.debug("Baseline scene '%s' ya existía", scene_name)
            else:
                raise
        # 2. Color source dentro de la escena (gris medio, 1920x1080).
        # color en formato AARRGGBB (v3 usa BGRA como int32): 0xFF808080 = gris
        try:
            c.create_input(
                scene_name, input_name, "color_source_v3",
                {"color": 0xFF808080, "width": 1920, "height": 1080}, True,
            )
            log.info("Baseline input '%s' creado en '%s'", input_name, scene_name)
        except Exception as e:
            msg = str(e).lower()
            if "already exists" in msg or "600" in msg:
                # Ya existía el input; asegurarse que exista un scene item en la
                # escena baseline. Si no existe, crear.
                try:
                    c.get_scene_item_id(scene_name, input_name)
                except Exception:
                    try:
                        c.create_scene_item(scene_name, input_name, enabled=True)
                    except Exception as e2:
                        log.warning("No pude asegurar scene item baseline: %s", e2)
            else:
                raise

    def remove_baseline_scene(self, scene_name: str, input_name: str) -> None:
        """Elimina la escena baseline + su color source."""
        c = self._client()
        # Remover el input primero. Si estaba compartido con otras escenas
        # (no debería, pero por si acaso), obs-websocket puede rechazar.
        try:
            c.remove_input(input_name)
        except Exception as e:
            log.debug("remove_input('%s') falló (ok si no existía): %s",
                      input_name, e)
        try:
            c.remove_scene(scene_name)
        except Exception as e:
            log.debug("remove_scene('%s') falló (ok si no existía): %s",
                      scene_name, e)

    # ------------------------------------------------------------------
    # Filtros de calibración (Source Record con nombre distinto por N)
    # ------------------------------------------------------------------

    def apply_calibration_filter(
        self, scene_name: str, filter_name: str, encoder: str,
        server_url: str, bitrate_kbps: int,
    ) -> None:
        """Crea un filtro Source Record en la escena, apuntando al URL.

        Idempotente: si el filtro ya existía, lo elimina primero para
        aplicar settings frescos.
        """
        c = self._client()
        # Reusar build_settings para consistencia con canales productivos
        fake_canal = {
            "url_destino": server_url,
            "encoder": encoder,
            "bitrate_kbps": bitrate_kbps,
            "habilitado": True,
        }
        settings = build_settings(fake_canal)

        # Idempotente: remove if exists
        try:
            c.remove_source_filter(scene_name, filter_name)
        except Exception:
            pass  # no existía

        c.create_source_filter(
            source_name=scene_name,
            filter_name=filter_name,
            filter_kind=FILTER_KIND,
            filter_settings=settings,
        )

    def remove_calibration_filter(self, scene_name: str, filter_name: str) -> None:
        """Elimina el filtro. Silencioso si no existía."""
        c = self._client()
        try:
            c.remove_source_filter(scene_name, filter_name)
        except Exception as e:
            log.debug("remove_source_filter('%s'/'%s') falló: %s",
                      scene_name, filter_name, e)

    # ------------------------------------------------------------------
    # Stats: skipped y total frames del output global
    # ------------------------------------------------------------------

    def get_output_frame_stats(self) -> tuple[int, int]:
        """Snapshot de `(output_skipped_frames, output_total_frames)`.

        obs-websocket v5 expone estos contadores en GetStats. En obsws-python
        vienen snake_case como atributos del response.
        """
        c = self._client()
        stats = c.get_stats()
        # Nombres en obsws-python 1.8.0: output_skipped_frames, output_total_frames
        skipped = int(getattr(stats, "output_skipped_frames", 0))
        total = int(getattr(stats, "output_total_frames", 0))
        return skipped, total
