"""Cliente Python del script Autopilot v2 que corre dentro de OBS.

Comunica con `obs_scripts/autopilot_v2.lua` a traves de dos text sources
ocultos en OBS que actuan como buzones:

- `__autopilot_config_v2__`: la app escribe JSON con canales[] + heartbeat.
- `__autopilot_state_v2__`:  el script publica JSON con estado por canal.

Ver `obs_scripts/PROTOCOL_v2.md` para el contrato completo del JSON.

La version v2 extiende la mecanica del Autopilot v1 (vive en la rama
release/v1.8.x-autopilot) para soportar N canales independientes
simultaneos — cada uno con su propia playlist, modo de rotacion
(`program_global` para Canal Principal legacy, `scene_items` para
canales multi-salida con filtro Source Record) y handoff.

Este cliente NO cambia el comportamiento normal de la app cuando esta
conectada. Solo:
1. Mantiene un heartbeat que le dice al script "estoy viva".
2. Publica el array de canales cuando el user edita escenas/canales.
3. Al cerrar la app, publica un handoff por canal para que el script
   retome exactamente desde donde estaba cada uno.
4. Al reconectar, lee el estado del script para sincronizar los
   `_RotatorState` locales + el Canal Principal.

No requiere OBS conectado en el constructor — cada metodo detecta si
la conexion esta viva y falla suavemente si no.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)


PROTOCOL_VERSION = 2

# Nombres de los text sources del buzon. Deben coincidir EXACTAMENTE con
# obs_scripts/autopilot_v2.lua (CONFIG_SOURCE_V2 / STATE_SOURCE_V2).
CONFIG_SOURCE_V2 = "__autopilot_config_v2__"
STATE_SOURCE_V2 = "__autopilot_state_v2__"

# Modos de rotacion soportados por el Lua v2.
MODE_PROGRAM_GLOBAL = "program_global"
MODE_SCENE_ITEMS = "scene_items"
_VALID_MODES = (MODE_PROGRAM_GLOBAL, MODE_SCENE_ITEMS)


class AutopilotV2NotInstalled(RuntimeError):
    """El script Autopilot v2 no esta instalado en el OBS remoto."""


class AutopilotClientV2:
    """Cliente para el Autopilot v2 Lua del OBS remoto (multi-canal)."""

    def __init__(self, obs_client):
        """
        obs_client: instancia de `models.obs_client.OBSClient`. No exige
                    que este conectada en construccion — se chequea por
                    operacion.
        """
        self._obs = obs_client
        self._version = 0  # monotonico local; se incrementa en cada publish

    # ------------------------------------------------------------------
    # Deteccion
    # ------------------------------------------------------------------

    def is_installed(self) -> bool:
        """True si ambos text sources del buzon v2 existen en OBS.

        Sin ellos, el script Lua v2 no esta corriendo (o fallo al
        crearlos). Silencia excepciones — devuelve False si no hay OBS
        conectado, si los sources no existen, o si hay cualquier error.
        """
        try:
            self._get_source_text(CONFIG_SOURCE_V2)
            self._get_source_text(STATE_SOURCE_V2)
            return True
        except Exception:
            return False

    def script_version(self) -> Optional[str]:
        """Devuelve la version del script instalado, o None si no hay state."""
        state = self.read_state()
        if state is None:
            return None
        return state.get("script_version")

    # ------------------------------------------------------------------
    # Publicacion de config
    # ------------------------------------------------------------------

    def publish_config(
        self,
        canales: list[dict[str, Any]],
        bump_version: bool = True,
    ) -> int:
        """Escribe el array de canales como config al buzon v2.

        Args:
            canales: lista de dicts con la estructura por canal
                documentada en PROTOCOL_v2.md. Cada dict debe tener al
                menos `canal_id` (int) y `modo_rotacion` (uno de
                `program_global` / `scene_items`). Opcional: `playlist`,
                `scene_name`, `filter_name`, `handoff`.
            bump_version: True (default) incrementa la version
                monotonica. False mantiene la anterior — util para
                heartbeats que no cambian la config.

        Returns:
            La `version` usada en la publicacion.

        Raises:
            AutopilotV2NotInstalled: si no hay OBS conectado o el buzon
                v2 no existe.
            ValueError: si `canales` no es una lista o algun entry
                tiene campos invalidos.
        """
        if not self._obs_connected():
            raise AutopilotV2NotInstalled("OBS no esta conectado")

        if not isinstance(canales, list):
            raise ValueError("canales debe ser una lista de dicts")

        normalized = [self._normalize_canal(c) for c in canales]

        if bump_version:
            self._version += 1

        payload: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "version": self._version,
            "generated_at": _now_iso(),
            "app_heartbeat_at": _now_iso(),
            "canales": normalized,
        }

        text = json.dumps(payload, ensure_ascii=False)
        try:
            self._set_source_text(CONFIG_SOURCE_V2, text)
        except Exception as e:
            raise AutopilotV2NotInstalled(
                f"No se pudo escribir a '{CONFIG_SOURCE_V2}': {e}"
            ) from e

        with_handoff = sum(1 for c in normalized if c.get("handoff"))
        log.info(
            "Autopilot v2 config v%d publicada (%d canales, %d con handoff)",
            self._version, len(normalized), with_handoff,
        )
        return self._version

    def send_heartbeat(self) -> bool:
        """Actualiza `app_heartbeat_at` sin cambiar el array `canales`.

        Se llama periodicamente (p. ej. cada 5 s) para mantener al script
        en modo `standby`. Sin heartbeat por >30 s el script asume que la
        app se cayo y toma control de todos los canales.

        El timestamp DEBE cambiar entre llamadas sucesivas, aun dentro de
        la misma publicacion. _now_iso() tiene granularidad de segundo,
        asi que si el heartbeat se dispara dentro del mismo segundo del
        anterior, el string sera identico y el Lua lo tratara como
        "mismo heartbeat" — sin problema porque el intervalo real es
        5 s.

        Returns:
            True si se pudo actualizar, False si fallo (silencioso).
        """
        try:
            current = self._get_source_text(CONFIG_SOURCE_V2)
        except Exception:
            return False

        if not current:
            # Nunca se publico config — un heartbeat vacio es inutil.
            return False

        try:
            data = json.loads(current)
        except json.JSONDecodeError:
            log.debug("Config v2 actual no es JSON valido; no se puede heartbeat")
            return False

        data["app_heartbeat_at"] = _now_iso()
        try:
            self._set_source_text(
                CONFIG_SOURCE_V2, json.dumps(data, ensure_ascii=False)
            )
            return True
        except Exception as e:
            log.debug("Heartbeat v2 fallo: %s", e)
            return False

    # ------------------------------------------------------------------
    # Lectura de estado
    # ------------------------------------------------------------------

    def read_state(self) -> Optional[dict[str, Any]]:
        """Lee y parsea el JSON de `__autopilot_state_v2__`.

        Devuelve un dict con las claves documentadas en PROTOCOL_v2.md
        (`script_version`, `protocol_version`, `mode`, `canales`,
        `updated_at`, `last_config_version`), o None si el source no
        existe o el contenido no es JSON valido.
        """
        try:
            text = self._get_source_text(STATE_SOURCE_V2)
        except Exception:
            return None
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def read_canal_state(self, canal_id: int) -> Optional[dict[str, Any]]:
        """Devuelve el entry del canal `canal_id` dentro del state, o None.

        Shortcut comun — la app casi siempre quiere el state de UN canal
        especifico (para sync al reconectar), no la lista completa.
        """
        state = self.read_state()
        if state is None:
            return None
        for c in state.get("canales", []):
            if int(c.get("canal_id", -999999)) == int(canal_id):
                return c
        return None

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _obs_connected(self) -> bool:
        return getattr(self._obs, "client", None) is not None

    def _client(self):
        """Devuelve el ReqClient de obsws-python. Lanza si no hay conexion."""
        c = getattr(self._obs, "client", None)
        if c is None:
            raise AutopilotV2NotInstalled("OBS no esta conectado")
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

    @classmethod
    def _normalize_canal(cls, canal: dict[str, Any]) -> dict[str, Any]:
        """Filtra un canal a los campos del protocolo v2 con validacion.

        Lanza ValueError si faltan campos requeridos o `modo_rotacion`
        es desconocido.
        """
        if not isinstance(canal, dict):
            raise ValueError("Cada canal debe ser un dict")

        if "canal_id" not in canal:
            raise ValueError("canal sin canal_id")
        canal_id = int(canal["canal_id"])

        modo = str(canal.get("modo_rotacion") or "")
        if modo not in _VALID_MODES:
            raise ValueError(
                f"canal {canal_id}: modo_rotacion '{modo}' invalido; "
                f"debe ser uno de {_VALID_MODES}"
            )

        out: dict[str, Any] = {
            "canal_id": canal_id,
            "modo_rotacion": modo,
            "playlist": [
                cls._normalize_item(x, modo)
                for x in (canal.get("playlist") or [])
            ],
        }

        if modo == MODE_SCENE_ITEMS:
            scene_name = str(canal.get("scene_name") or "")
            if not scene_name:
                raise ValueError(
                    f"canal {canal_id}: modo scene_items requiere scene_name"
                )
            out["scene_name"] = scene_name
            # filter_name es opcional pero recomendado; se pasa tal cual.
            if canal.get("filter_name"):
                out["filter_name"] = str(canal["filter_name"])

        handoff = cls._normalize_handoff(canal.get("handoff"), modo)
        if handoff is not None:
            out["handoff"] = handoff

        return out

    @staticmethod
    def _normalize_item(
        item: dict[str, Any], modo: str
    ) -> dict[str, Any]:
        """Filtra un item de playlist a los campos del protocolo v2.

        Ignora campos que la app tenga y el script no espera. Asigna
        defaults sensatos si faltan campos opcionales.
        """
        base: dict[str, Any] = {
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
        if modo == MODE_SCENE_ITEMS:
            # scene_item_id es como el Lua localiza el item en la escena
            # contenedora para hacer `set_scene_item_enabled`. Si falta,
            # el Lua logueara y saltara ese item.
            base["scene_item_id"] = int(
                item.get("scene_item_id")
                or item.get("sceneItemId")
                or 0
            )
        return base

    @staticmethod
    def _normalize_handoff(
        handoff: Any, modo: str
    ) -> Optional[dict[str, Any]]:
        """Normaliza handoff segun modo. None si vacio o seconds_remaining<=0.

        Replica el fix del bug C del Autopilot v1: handoff con
        seconds_remaining<=0 corrompia el cursor del script, asi que se
        omite.
        """
        if not handoff or not isinstance(handoff, dict):
            return None
        seconds = int(handoff.get("seconds_remaining") or 0)
        if seconds <= 0:
            return None
        base: dict[str, Any] = {
            "seconds_remaining": seconds,
            "at": _now_iso(),
        }
        if modo == MODE_PROGRAM_GLOBAL:
            active_scene = str(handoff.get("active_scene") or "")
            if not active_scene:
                return None
            base["active_scene"] = active_scene
        else:  # scene_items
            active_index = int(handoff.get("active_index") or 0)
            if active_index <= 0:
                return None
            base["active_index"] = active_index
        return base


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def _now_iso() -> str:
    """ISO 8601 UTC hasta segundos, con sufijo Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
