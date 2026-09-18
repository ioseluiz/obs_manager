"""Cliente Python del script Autopilot que corre dentro de OBS.

Se comunica con `obs_scripts/autopilot.lua` a través de dos text sources
ocultos en OBS que actúan como buzones:

- `__autopilot_config__`: la app escribe JSON con la playlist + heartbeat.
- `__autopilot_state__`: el script publica JSON con su estado actual.

Ver `obs_scripts/PROTOCOL.md` para el contrato completo del JSON.

Este cliente NO cambia el comportamiento normal de la app cuando está
conectada. Solo:
1. Mantiene un heartbeat que le dice al script "estoy viva".
2. Publica la playlist actualizada cuando el user edita escenas.
3. Al cerrar la app, publica un handoff explícito para que el script
   retome exactamente desde donde estaba.
4. Al reconectar, lee el estado del script para sincronizarse.

No requiere OBS conectado en el constructor — cada método detecta si
la conexión está viva y falla suavemente si no.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)


# Nombres de los text sources del buzón. Deben coincidir EXACTAMENTE con
# obs_scripts/autopilot.lua (CONFIG_SOURCE / STATE_SOURCE).
CONFIG_SOURCE = "__autopilot_config__"
STATE_SOURCE = "__autopilot_state__"


class AutopilotNotInstalled(RuntimeError):
    """El script Autopilot no está instalado en el OBS remoto."""


class AutopilotClient:
    """Cliente para el Autopilot Lua del OBS remoto."""

    def __init__(self, obs_client):
        """
        obs_client: instancia de `models.obs_client.OBSClient`. No exige que
                    esté conectada en construcción — se chequea por operación.
        """
        self._obs = obs_client
        self._version = 0  # monotónico local; se incrementa en cada publish

    # ------------------------------------------------------------------
    # Detección
    # ------------------------------------------------------------------

    def is_installed(self) -> bool:
        """True si ambos text sources del buzón existen en OBS.

        Sin ellos, el script Lua no está corriendo (o falló al crearlos).
        Silencia excepciones — devuelve False si no hay OBS conectado, si
        los sources no existen, o si hay cualquier error de comunicación.
        """
        try:
            self._get_source_text(CONFIG_SOURCE)
            self._get_source_text(STATE_SOURCE)
            return True
        except Exception:
            return False

    def script_version(self) -> Optional[str]:
        """Devuelve la versión del script instalado, o None si no hay estado."""
        state = self.read_state()
        if state is None:
            return None
        return state.get("script_version")

    # ------------------------------------------------------------------
    # Publicación de config
    # ------------------------------------------------------------------

    def publish_config(
        self,
        playlist: list[dict[str, Any]],
        handoff: Optional[dict[str, Any]] = None,
        bump_version: bool = True,
    ) -> int:
        """Escribe la playlist como config al buzón. Devuelve la version usada.

        Args:
            playlist: lista de dicts con las escenas + duración + programación
                horaria. Cada item debe tener al menos `name` (string) y
                `duration_seg` (int). Opcional: `active_days`,
                `active_time_start`, `active_time_end`.
            handoff: opcional. `{active_scene: str, seconds_remaining: int}`.
                Cuando la app se cierra o transfiere control, se manda un
                handoff para que el script retome desde ese punto exacto.
            bump_version: True (default) incrementa la version. False mantiene
                la anterior — útil para heartbeats que no cambian la playlist.

        Raises:
            AutopilotNotInstalled: si los text sources del buzón no existen.
        """
        if not self._obs_connected():
            raise AutopilotNotInstalled("OBS no está conectado")

        if bump_version:
            self._version += 1

        payload: dict[str, Any] = {
            "version": self._version,
            "generated_at": _now_iso(),
            "app_heartbeat_at": _now_iso(),
            "playlist": [self._normalize_item(x) for x in playlist],
        }
        if handoff is not None:
            payload["handoff"] = {
                "active_scene": str(handoff.get("active_scene") or ""),
                "seconds_remaining": int(handoff.get("seconds_remaining") or 0),
                "at": _now_iso(),
            }

        text = json.dumps(payload, ensure_ascii=False)
        try:
            self._set_source_text(CONFIG_SOURCE, text)
        except Exception as e:
            raise AutopilotNotInstalled(
                f"No se pudo escribir a '{CONFIG_SOURCE}': {e}"
            ) from e

        log.info(
            "Autopilot config v%d publicada (%d escenas%s)",
            self._version, len(playlist),
            ", con handoff" if handoff else "",
        )
        return self._version

    def send_heartbeat(self) -> bool:
        """Actualiza `app_heartbeat_at` sin cambiar la playlist.

        Se llama periódicamente (ej. cada 5s) para mantener al script en
        modo `standby`. Sin heartbeat por >30s el script asume que la
        app se cayó y toma control.

        Devuelve True si se pudo actualizar, False si falló (silencioso).
        """
        try:
            current = self._get_source_text(CONFIG_SOURCE)
        except Exception:
            return False

        if not current:
            # Nunca se publicó config — un heartbeat vacío es inútil.
            return False

        try:
            data = json.loads(current)
        except json.JSONDecodeError:
            log.debug("Config actual no es JSON válido; no se puede heartbeat")
            return False

        data["app_heartbeat_at"] = _now_iso()
        try:
            self._set_source_text(CONFIG_SOURCE, json.dumps(data, ensure_ascii=False))
            return True
        except Exception as e:
            log.debug("Heartbeat falló: %s", e)
            return False

    # ------------------------------------------------------------------
    # Lectura de estado
    # ------------------------------------------------------------------

    def read_state(self) -> Optional[dict[str, Any]]:
        """Lee y parsea el JSON de `__autopilot_state__`.

        Devuelve un dict con las claves documentadas en PROTOCOL.md
        (`script_version`, `mode`, `active_scene`, `seconds_remaining`,
        `last_rotation_at`, `last_config_version`, `playlist_size`,
        `updated_at`), o None si el source no existe o el contenido no
        es JSON válido.
        """
        try:
            text = self._get_source_text(STATE_SOURCE)
        except Exception:
            return None
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _obs_connected(self) -> bool:
        return getattr(self._obs, "client", None) is not None

    def _client(self):
        """Devuelve el ReqClient de obsws-python. Lanza si no hay conexión."""
        c = getattr(self._obs, "client", None)
        if c is None:
            raise AutopilotNotInstalled("OBS no está conectado")
        return c

    def _get_source_text(self, source_name: str) -> str:
        """GetInputSettings + extraer el campo 'text'. Lanza si no existe."""
        c = self._client()
        resp = c.get_input_settings(source_name)
        settings = getattr(resp, "input_settings", None) or {}
        return settings.get("text", "") or ""

    def _set_source_text(self, source_name: str, text: str) -> None:
        """SetInputSettings con overlay=True para no pisar otros settings."""
        c = self._client()
        c.set_input_settings(source_name, {"text": text}, True)

    @staticmethod
    def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
        """Filtra un item de playlist a los campos del protocolo.

        Ignora campos que la app tenga y el script no espera. Asigna
        defaults sensatos si faltan campos opcionales.
        """
        return {
            "name": str(item.get("name") or item.get("nombre_escena") or ""),
            "duration_seg": int(
                item.get("duration_seg")
                or item.get("duracion_segundos")
                or item.get("duration")
                or 20
            ),
            "active_days": int(item.get("active_days") or 127),
            "active_time_start": item.get("active_time_start") or "",
            "active_time_end": item.get("active_time_end") or "",
        }


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def _now_iso() -> str:
    """ISO 8601 UTC hasta segundos, con sufijo Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
