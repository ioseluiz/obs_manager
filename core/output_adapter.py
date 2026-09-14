"""Adapter para la salida UDP de un canal multi-salida vía Source Record.

Objetivo: aislar el conocimiento del plugin (nombres de campos, valores
mágicos, reglas descubiertas en Fases 0 y 1) detrás de una interfaz simple
que consume `canal` dicts (del `CanalModel`) y opera sobre OBS.

Contrato firme (derivado de la Fase 1 discovery):
- El destino UDP se configura con **stream_mode = 1** ("Always").
  NUNCA usar `record_mode: 1` con `path` = URL — crashea el plugin.
- Cada canal tiene su propia **escena contenedora** en OBS cuyo nombre =
  `canal["nombre"]`. El adapter asume que la escena YA existe (no la crea;
  eso es responsabilidad de CanalController en 1c).
- Un solo filtro por escena, con nombre fijo `udp_out`. No se soportan
  múltiples salidas por canal — cada canal es una salida.

El adapter recibe un cliente WebSocket ya conectado (típicamente
`obs_client.client` de `models.obs_client.OBSClient`) y llama a la API v5.
Es puramente de infraestructura: sin PyQt, sin threading, sin persistencia.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


FILTER_NAME = "udp_out"
FILTER_KIND = "source_record_filter"

# Encoders conocidos por el plugin (short-form, no los IDs de OBS).
# Extraídos de la locale del plugin y confirmados con Fase 1.
_KNOWN_ENCODERS = ("x264", "qsv", "nvenc", "amf", "apple")


def build_settings(canal: dict[str, Any]) -> dict[str, Any]:
    """Traduce un dict de canal (del CanalModel) al dict de settings del filtro.

    Nunca incluye keys que puedan crashear el plugin (documentado en la
    memoria de multi-salida).
    """
    encoder = canal.get("encoder") or "x264"
    if encoder not in _KNOWN_ENCODERS:
        log.warning(
            "Encoder '%s' fuera de la lista conocida %s. Pasando tal cual; "
            "Fase 2 (calibración) validará capacidad.",
            encoder, _KNOWN_ENCODERS,
        )

    # Preset explícito por canal (Opción B, Fase 2). Si el canal no lo trae
    # (DBs viejas antes de la migración de output_*), asume 1080p30 estándar.
    width = int(canal.get("output_width") or 1920)
    height = int(canal.get("output_height") or 1080)
    fps = int(canal.get("output_fps") or 30)

    settings: dict[str, Any] = {
        # Regla firme: streaming va SIEMPRE por stream_mode. Ver Fase 1 memory.
        "stream_mode": 1,
        "server": canal["url_destino"],
        "key": "",
        "encoder": encoder,
        "bitrate": int(canal.get("bitrate_kbps", 2500)),
        "rate_control": "CBR",
        "scale_type": 3,
        # Resolución y fps explícitos — antes de esto el plugin heredaba
        # del canvas de OBS y los canales quedaban atados a 1920x1080. Con
        # estos settings cada canal puede tener su propio preset.
        "output_width": width,
        "output_height": height,
        "output_fps_num": fps,
        "output_fps_den": 1,
        # Streaming UDP requiere keyframes frecuentes: un reproductor
        # recién conectado necesita un keyframe para arrancar el decode.
        # Con el default de x264 (~250 frames), a 60fps son ~4s y VLC
        # muestra cuadro negro durante ese tiempo. 2s balancea decode
        # rápido y bitrate razonable.
        "keyint_sec": 2,
        # Perfil H.264 estable: "high" es el default de OBS streaming y
        # lo decodifica cualquier reproductor. Sin este setting, la UI
        # del plugin muestra "profile: none" y el encoder puede negociar
        # un perfil que no matchee lo que espera el reproductor.
        "profile": "high",
        # zerolatency reduce el buffer del encoder para que los frames
        # salgan de inmediato. Sin esto, x264 puede acumular frames en
        # su lookahead antes de emitirlos, empeorando el "arranque
        # negro" en el reproductor.
        "tune": "zerolatency",
        # preset veryfast: default de streaming en OBS. Equilibrio
        # CPU/calidad razonable para bitrate 2500 kbps a 1080p.
        "preset": "veryfast",
    }

    # Audio independiente por canal si el user lo pidió.
    audio_track = int(canal.get("audio_track") or 0)
    if audio_track > 0:
        settings["different_audio"] = True
        settings["audio_track"] = audio_track

    return settings


class OutputAdapter:
    """Wraps el filtro source_record_filter de una escena contenedora.

    Todas las operaciones son idempotentes y reportan (ok, msg) para que el
    caller decida cómo escalar errores. No lanza excepciones excepto por
    bugs de programación (contrato roto del cliente pasado).
    """

    def __init__(self, req_client):
        """req_client: instancia con la API v5 de obsws-python (o compatible).

        Típicamente `models.obs_client.OBSClient().client` — el wrapper
        `_GuardedClient` sirve porque delega a métodos por nombre.
        """
        self._c = req_client

    # ------------------------------------------------------------------
    # Operaciones
    # ------------------------------------------------------------------

    def apply(self, canal: dict[str, Any]) -> tuple[bool, str]:
        """Crea o actualiza el filtro `udp_out` sobre la escena del canal.

        Si el filtro no existe, lo crea. Si existe, actualiza sus settings.
        Requiere que la escena `canal["nombre"]` ya exista en OBS.
        """
        scene = canal["nombre"]
        settings = build_settings(canal)
        # Estrategia idempotente: intentamos remove + create. Si el filter
        # no existía, remove tira 600 (esperado, se ignora); create siempre
        # deja el filter en un estado limpio con los settings frescos.
        self._silent_remove(scene)
        try:
            self._c.create_source_filter(
                source_name=scene,
                filter_name=FILTER_NAME,
                filter_kind=FILTER_KIND,
                filter_settings=settings,
            )
        except Exception as e:
            return False, f"create_source_filter falló para escena '{scene}': {e}"
        # El filter se crea habilitado por default. Respetar el flag del canal:
        if not canal.get("habilitado", True):
            self.disable(scene)
        return True, "Filtro aplicado."

    def enable(self, scene: str) -> tuple[bool, str]:
        try:
            self._c.set_source_filter_enabled(scene, FILTER_NAME, True)
            return True, "Filtro habilitado."
        except Exception as e:
            return False, f"set_source_filter_enabled(True) falló: {e}"

    def disable(self, scene: str) -> tuple[bool, str]:
        try:
            self._c.set_source_filter_enabled(scene, FILTER_NAME, False)
            return True, "Filtro deshabilitado."
        except Exception as e:
            return False, f"set_source_filter_enabled(False) falló: {e}"

    def remove(self, scene: str) -> tuple[bool, str]:
        """Elimina el filtro. Idempotente: si no existe, retorna (True, ...)."""
        try:
            self._quiet(self._c.remove_source_filter, scene, FILTER_NAME)
            return True, "Filtro eliminado."
        except Exception as e:
            msg = str(e)
            if "600" in msg or "No filter" in msg:
                return True, "Filtro ya no existía."
            return False, f"remove_source_filter falló: {e}"

    # ------------------------------------------------------------------
    # Introspección
    # ------------------------------------------------------------------

    def is_present(self, scene: str) -> bool:
        """True si el filtro existe en la escena."""
        try:
            self._quiet(self._c.get_source_filter, scene, FILTER_NAME)
            return True
        except Exception:
            return False

    def is_enabled(self, scene: str) -> bool | None:
        """True/False si el filtro existe; None si no existe."""
        try:
            resp = self._quiet(self._c.get_source_filter, scene, FILTER_NAME)
            return bool(resp.filter_enabled)
        except Exception:
            return None

    def get_effective_settings(self, scene: str) -> dict | None:
        """Devuelve los settings que OBS reporta para el filtro, o None."""
        try:
            resp = self._quiet(self._c.get_source_filter, scene, FILTER_NAME)
            return dict(resp.filter_settings)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _quiet(fn, *args, **kwargs):
        """Ejecuta fn silenciando obsws_python.reqs.

        Los códigos 600 ("no filter found") son esperados en calls de probe
        (is_present, is_enabled, remove-idempotente) — el cliente los loguea
        como traceback en stderr aunque el caller los maneje. Este helper
        baja el nivel del logger durante la llamada para no contaminar la
        salida.
        """
        obsws_log = logging.getLogger("obsws_python.reqs")
        prev = obsws_log.level
        obsws_log.setLevel(logging.CRITICAL)
        try:
            return fn(*args, **kwargs)
        finally:
            obsws_log.setLevel(prev)

    def _silent_remove(self, scene: str) -> None:
        """Elimina el filtro sin ruido si no existe. Interno de apply()."""
        try:
            self._quiet(self._c.remove_source_filter, scene, FILTER_NAME)
        except Exception:
            pass
