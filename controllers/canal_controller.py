"""Orquesta la aplicación de canales multi-salida sobre OBS.

Toma canales del `CanalModel` (persistencia) y los materializa en OBS:
- Crea la escena contenedora (nombre = `canal["nombre"]`).
- Adjunta el filtro de output UDP vía `OutputAdapter`.
- Reconcilia los `canal_items` como scene items anidados (cada item
  referencia una escena de `secuencias` — no se duplica contenido).
- Enciende/apaga la salida y opera el rotador interno que alterna
  visibilidad de scene items via `SetSceneItemEnabled` — nunca
  `change_scene`, porque la escena contenedora vive fuera de programa
  (Fase 0 verificó que el filter produce ahí).

Diseño de threading:
- Los métodos públicos deben llamarse desde el hilo principal (UI).
- El rotador usa `QTimer` que dispara en el hilo principal.
- Adquiere `obs_client._client_lock` para las operaciones que puedan
  concurrir con el watchdog o con el rotador legacy (change_scene).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.output_adapter import OutputAdapter, FILTER_NAME
from views.schedule_widget import is_scene_active_now

log = logging.getLogger(__name__)

# Cuando ningún item del canal está en su ventana horaria, el rotador
# muestra un placeholder y agenda el próximo chequeo en este intervalo.
_RETRY_MS_WHEN_NO_ACTIVE = 60_000  # 60s — matches the legacy rotator behavior

# Nombre del input color-source-black que sirve de placeholder en cada
# canal container. Se crea al aplicar el canal si no existe.
_PLACEHOLDER_SUFFIX = "__placeholder"


@dataclass
class _PlaylistEntry:
    """Un item del canal + info de schedule inlineada para no re-consultar
    scene_model en cada tick del rotador."""
    item_id: int  # canal_items.id
    duration_seg: int
    active_days: int  # bitmask (bit 0 = Lunes)
    time_start: str | None  # "HH:MM" o None
    time_end: str | None

    def as_scene_dict(self) -> dict[str, Any]:
        """Envelope que espera is_scene_active_now."""
        return {
            "active_days": self.active_days,
            "active_time_start": self.time_start,
            "active_time_end": self.time_end,
        }


@dataclass
class _RotatorState:
    """Estado en memoria del rotador interno de un canal."""
    canal_id: int
    scene_name: str
    # canal_item_id -> obs sceneItemId (para SetSceneItemEnabled)
    item_to_scene_item: dict[int, int] = field(default_factory=dict)
    playlist: list[_PlaylistEntry] = field(default_factory=list)
    active_index: int = -1
    timer: QTimer | None = None
    # Pausa/resume: cuando is_paused=True, remaining_ms guarda el tiempo
    # que le quedaba al timer al pausarse. Al resumir, arranca un nuevo
    # timer con ese remaining. Ver pause_rotator/resume_rotator.
    is_paused: bool = False
    remaining_ms: int = 0
    # Scene item id del placeholder (color source negro) dentro del
    # container. Se muestra cuando ningún item está en ventana horaria.
    placeholder_scene_item_id: int | None = None
    # True si el placeholder es lo que está visible ahora mismo.
    placeholder_visible: bool = False


class CanalController(QObject):
    """Controlador de canales multi-salida.

    Se instancia una vez y se le pasan los modelos + un `OBSClient` ya
    inicializado (aunque puede no estar conectado todavía; las operaciones
    verifican al momento del uso).
    """

    # Señales para la futura UI (1d). Ninguna se emite todavía en 1c más allá
    # de que la infraestructura queda declarada para no romper 1d.
    canal_applied = pyqtSignal(int, bool, str)      # canal_id, ok, msg
    canal_removed = pyqtSignal(int, bool, str)
    canal_status_changed = pyqtSignal(int, dict)    # canal_id, status dict

    def __init__(self, canal_model, scene_model, obs_client, parent=None):
        super().__init__(parent)
        self.canal_model = canal_model
        self.scene_model = scene_model
        self.obs_client = obs_client
        self._rotators: dict[int, _RotatorState] = {}
        # Override para tests: función que devuelve el "now" que consulta
        # el rotador al filtrar por schedule. En runtime = datetime.now.
        self._time_provider: Callable[[], datetime] | None = None

    def _now(self) -> datetime:
        return self._time_provider() if self._time_provider else datetime.now()

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    @property
    def _connected(self) -> bool:
        return self.obs_client is not None and self.obs_client.client is not None

    def _adapter(self) -> OutputAdapter | None:
        """Adapter fresco cada llamada — el underlying client puede rotarse
        por el watchdog. No cachearlo evita usar un client obsoleto.

        Usa el raw client (ver `_raw_client`) porque el adapter mismo se
        beneficia de la sincronía directa; el guarded solo detecta
        timeouts, y todas las operaciones del adapter son cortas."""
        if not self._connected:
            return None
        return OutputAdapter(self._raw_client())

    def _lock(self):
        """Devuelve el RLock del OBSClient para serializar acceso al socket."""
        return self.obs_client._client_lock

    def _get_effective_items(self, canal_id: int) -> list[dict[str, Any]]:
        """Join en Python entre canal_items y secuencias.

        Devuelve una lista con, por item:
            canal_item_id, secuencia_nombre, duration_seg,
            active_days, active_time_start, active_time_end
        Items que referencian secuencias inexistentes se saltan con warning.
        """
        items = self.canal_model.get_items(canal_id)
        result = []
        for it in items:
            seq = self.scene_model.get_scene(it["secuencia_id"])
            if seq is None:
                log.warning(
                    "canal_item %d referencia secuencia %d inexistente; se salta",
                    it["id"], it["secuencia_id"],
                )
                continue
            duration = it["duracion_override_seg"] or seq["duration"]
            result.append({
                "canal_item_id": it["id"],
                "secuencia_nombre": seq["name"],
                "duration_seg": int(duration),
                # Schedule heredado de la secuencia — el canal_item lo respeta
                # sin poder overridearlo (R-2).
                "active_days": int(seq.get("active_days") or 127),
                "active_time_start": seq.get("active_time_start"),
                "active_time_end": seq.get("active_time_end"),
            })
        return result

    def _raw_client(self):
        """Devuelve el ReqClient crudo, saltando el _GuardedClient si está.

        El _GuardedClient de OBSClient se envenena en secuencias largas de
        requests (visto en tests de canal_controller: remove_scene tras una
        cadena de set_scene_item_enabled devuelve exito sin efecto). El
        contrato del guarded (invalidar sesión ante timeouts) no se pierde
        para las operaciones de rotador — solo evitamos el proxy para
        operaciones estructurales de scene/filter donde vimos flakiness.
        """
        c = self.obs_client.client
        return getattr(c, "_inner", c)

    def _ensure_scene(self, scene_name: str) -> tuple[bool, str]:
        """Crea la escena contenedora si no existe. Idempotente."""
        client = self._raw_client()
        try:
            existing = {s["sceneName"] for s in client.get_scene_list().scenes}
        except Exception as e:
            return False, f"get_scene_list falló: {e}"
        if scene_name in existing:
            return True, "Escena ya existía."
        try:
            client.create_scene(scene_name)
            return True, "Escena creada."
        except Exception as e:
            return False, f"create_scene falló: {e}"

    def _reconcile_scene_items(self, scene_name: str, effective_items: list[dict]
                               ) -> tuple[dict[int, int], int | None]:
        """Wipe-and-rebuild: elimina scene items existentes y los recrea desde
        `effective_items` (en orden), más un scene item placeholder al final.

        Devuelve (mapping canal_item_id → sceneItemId, placeholder_scene_item_id).
        Todos los items se crean deshabilitados. El rotador después activa uno
        a la vez (o el placeholder si nada está en ventana).
        """
        client = self._raw_client()

        # 1. Wipe existentes
        try:
            current = client.get_scene_item_list(scene_name).scene_items
        except Exception as e:
            log.warning("get_scene_item_list falló en %s: %s", scene_name, e)
            current = []
        for si in current:
            try:
                client.remove_scene_item(scene_name, si["sceneItemId"])
            except Exception as e:
                log.warning("remove_scene_item %d falló: %s", si["sceneItemId"], e)

        # 2. Recrear items en orden, deshabilitados
        mapping: dict[int, int] = {}
        for eff in effective_items:
            try:
                resp = client.create_scene_item(
                    scene_name, eff["secuencia_nombre"], enabled=False,
                )
                mapping[eff["canal_item_id"]] = int(resp.scene_item_id)
            except Exception as e:
                log.warning(
                    "create_scene_item(%s, %s) falló: %s",
                    scene_name, eff["secuencia_nombre"], e,
                )

        # 3. Placeholder (color source negro) — se muestra cuando nada está
        # en su ventana horaria. Se crea el input si no existe (idempotente
        # mediante try/except).
        placeholder_input = f"{scene_name}{_PLACEHOLDER_SUFFIX}"
        try:
            client.create_input(
                scene_name, placeholder_input, "color_source_v3",
                {"color": 0xFF000000, "width": 1920, "height": 1080}, False,
            )
            # create_input ya crea la scene item; obtener su id via get_scene_item_id
            try:
                placeholder_sid = int(
                    client.get_scene_item_id(scene_name, placeholder_input).scene_item_id
                )
            except Exception:
                placeholder_sid = None
        except Exception as e:
            # Ya existía: crear scene item que referencia el input existente
            msg = str(e).lower()
            if "already exists" in msg or "600" in msg:
                try:
                    resp = client.create_scene_item(
                        scene_name, placeholder_input, enabled=False,
                    )
                    placeholder_sid = int(resp.scene_item_id)
                except Exception as e2:
                    log.warning("No se pudo crear scene item de placeholder: %s", e2)
                    placeholder_sid = None
            else:
                log.warning("create_input placeholder falló: %s", e)
                placeholder_sid = None

        return mapping, placeholder_sid

    # ------------------------------------------------------------------
    # API pública — orquestación
    # ------------------------------------------------------------------

    def apply_canal(self, canal_id: int) -> tuple[bool, str]:
        """Sincroniza un canal del modelo con OBS (crea/actualiza)."""
        canal = self.canal_model.get_canal(canal_id)
        if not canal:
            return False, f"Canal {canal_id} no existe en el modelo."
        if not self._connected:
            return False, "OBS no está conectado."

        with self._lock():
            ok, msg = self._ensure_scene(canal["nombre"])
            if not ok:
                return False, msg

            effective_items = self._get_effective_items(canal_id)
            mapping, placeholder_sid = self._reconcile_scene_items(
                canal["nombre"], effective_items,
            )

            adapter = self._adapter()
            ok, msg = adapter.apply(canal)
            if not ok:
                return False, f"Filtro no se pudo aplicar: {msg}"

            # Preparar / actualizar estado del rotador (aunque no arranque aún)
            state = self._rotators.get(canal_id) or _RotatorState(
                canal_id=canal_id, scene_name=canal["nombre"],
            )
            state.scene_name = canal["nombre"]
            state.item_to_scene_item = mapping
            state.playlist = [
                _PlaylistEntry(
                    item_id=e["canal_item_id"],
                    duration_seg=e["duration_seg"],
                    active_days=e["active_days"],
                    time_start=e["active_time_start"],
                    time_end=e["active_time_end"],
                )
                for e in effective_items
            ]
            state.active_index = -1
            state.placeholder_scene_item_id = placeholder_sid
            state.placeholder_visible = False
            self._rotators[canal_id] = state

        # Si el canal está habilitado, arranca la rotación
        if canal["habilitado"]:
            self.start_rotator(canal_id)
        else:
            self.stop_rotator(canal_id)

        result = "Canal aplicado en OBS."
        self.canal_applied.emit(canal_id, True, result)
        return True, result

    def remove_canal_from_obs(self, canal_id: int) -> tuple[bool, str]:
        """Quita la escena contenedora + filtro de OBS. No borra la DB."""
        canal = self.canal_model.get_canal(canal_id)
        if not canal:
            return False, f"Canal {canal_id} no existe en el modelo."
        if not self._connected:
            return False, "OBS no está conectado."

        self.stop_rotator(canal_id)
        with self._lock():
            adapter = self._adapter()
            adapter.remove(canal["nombre"])
            try:
                # Usar raw client: ver comentario en _raw_client().
                self._raw_client().remove_scene(canal["nombre"])
                msg = "Canal removido de OBS."
            except Exception as e:
                msg = f"remove_scene falló ({e}); filtro sí se quitó."
                self.canal_removed.emit(canal_id, False, msg)
                return False, msg

        self._rotators.pop(canal_id, None)
        self.canal_removed.emit(canal_id, True, msg)
        return True, msg

    def set_habilitado(self, canal_id: int, habilitado: bool) -> tuple[bool, str]:
        """Toggle rápido: enciende/apaga filtro + arranca/para rotador.
        Persiste al modelo. NO reconstruye scene items."""
        canal = self.canal_model.get_canal(canal_id)
        if not canal:
            return False, f"Canal {canal_id} no existe."
        self.canal_model.set_habilitado(canal_id, habilitado)

        if not self._connected:
            return True, "Persistido en modelo; OBS no conectado."

        with self._lock():
            adapter = self._adapter()
            if habilitado:
                adapter.enable(canal["nombre"])
            else:
                adapter.disable(canal["nombre"])

        if habilitado:
            self.start_rotator(canal_id)
        else:
            self.stop_rotator(canal_id)
        return True, "OK"

    # ------------------------------------------------------------------
    # Rotador interno (por canal)
    # ------------------------------------------------------------------

    def start_rotator(self, canal_id: int) -> None:
        """Arranca el ciclo del rotador de este canal.

        Si la playlist está vacía o todos los items están fuera de ventana
        horaria, _advance mostrará el placeholder y agendará re-check.
        """
        state = self._rotators.get(canal_id)
        if not state:
            log.warning("start_rotator sin estado para canal %d; ¿faltó apply?",
                        canal_id)
            return
        # Reinicio limpio si ya había timer corriendo
        if state.timer is not None:
            state.timer.stop()
        # _advance resuelve empty playlist / all-out-of-schedule mostrando
        # el placeholder — no cortar acá.
        state.active_index = -1
        self._advance(state)

    def stop_rotator(self, canal_id: int) -> None:
        """Detiene el timer y oculta todos los items del canal (incluye placeholder)."""
        state = self._rotators.get(canal_id)
        if not state:
            return
        if state.timer is not None:
            state.timer.stop()
            state.timer = None
        state.is_paused = False
        state.remaining_ms = 0
        if not self._connected:
            state.active_index = -1
            state.placeholder_visible = False
            return
        with self._lock():
            client = self._raw_client()
            for si_id in state.item_to_scene_item.values():
                try:
                    client.set_scene_item_enabled(
                        state.scene_name, si_id, False,
                    )
                except Exception as e:
                    log.debug("hide scene item %d falló: %s", si_id, e)
            # También ocultar placeholder
            if state.placeholder_scene_item_id is not None:
                try:
                    client.set_scene_item_enabled(
                        state.scene_name, state.placeholder_scene_item_id, False,
                    )
                except Exception as e:
                    log.debug("hide placeholder falló: %s", e)
        state.active_index = -1
        state.placeholder_visible = False

    def pause_rotator(self, canal_id: int) -> bool:
        """Congela la rotación en el item actual sin ocultarlo.

        Retorna True si pausó, False si el rotador no estaba corriendo o
        ya estaba pausado.
        """
        state = self._rotators.get(canal_id)
        if not state or state.timer is None or state.is_paused:
            return False
        # Guardar tiempo restante antes de parar el timer
        remaining = state.timer.remainingTime()
        state.remaining_ms = max(0, int(remaining)) if remaining > 0 else 0
        state.timer.stop()
        state.is_paused = True
        return True

    def resume_rotator(self, canal_id: int) -> bool:
        """Reanuda un rotador pausado con el tiempo que le quedaba.

        Retorna True si reanudó, False si el rotador no estaba pausado.
        """
        state = self._rotators.get(canal_id)
        if not state or not state.is_paused:
            return False
        if state.timer is None:
            # El timer fue destruido; recreamos avanzando desde el item actual
            state.is_paused = False
            state.remaining_ms = 0
            # Retroceder 1 para que _advance vuelva a mostrar el mismo item
            n = len(state.playlist)
            if n > 0 and 0 <= state.active_index < n:
                state.active_index = (state.active_index - 1) % n
            self._advance(state)
            return True
        # Restart con el remaining guardado (mínimo 100ms para no fire inmediato)
        wait_ms = max(100, state.remaining_ms) if state.remaining_ms > 0 else 1000
        state.timer.start(wait_ms)
        state.is_paused = False
        state.remaining_ms = 0
        return True

    def next_item(self, canal_id: int) -> bool:
        """Salta al siguiente item, cortando el tiempo restante actual."""
        state = self._rotators.get(canal_id)
        if not state or not state.playlist:
            return False
        if state.timer is not None:
            state.timer.stop()
        state.is_paused = False
        state.remaining_ms = 0
        # _advance ya avanza el índice y muestra el item + agenda timer
        self._advance(state)
        return True

    def prev_item(self, canal_id: int) -> bool:
        """Retrocede al item anterior (wraps al último si estamos en el primero)."""
        state = self._rotators.get(canal_id)
        if not state or not state.playlist:
            return False
        if state.timer is not None:
            state.timer.stop()
        state.is_paused = False
        state.remaining_ms = 0
        n = len(state.playlist)
        # Truco: seteamos active_index tal que _advance nos deje en actual-1.
        # _advance hace (active_index + 1) % n al mostrar el nuevo, así que
        # queremos que ese cómputo dé (actual - 1) mod n.
        if state.active_index < 0:
            # Rotator no arrancó — prev antes de start deja en el último.
            state.active_index = n - 2
        else:
            state.active_index = (state.active_index - 2) % n
        self._advance(state)
        return True

    def _advance(self, state: _RotatorState) -> None:
        """Muestra el siguiente item en su ventana horaria, o el placeholder
        si nada está activo. Agenda el próximo tick."""
        if not state.playlist:
            # Sin items → placeholder si existe, sin reintentar.
            self._hide_all_items(state)
            self._show_placeholder(state)
            self._ensure_timer(state)
            return

        now = self._now()

        # Buscar el siguiente item que esté en su ventana horaria,
        # empezando por (active_index + 1) y dando la vuelta.
        n = len(state.playlist)
        start = state.active_index if state.active_index >= 0 else -1
        found: int | None = None
        for offset in range(1, n + 1):
            candidate = (start + offset) % n
            entry = state.playlist[candidate]
            if is_scene_active_now(entry.as_scene_dict(), now):
                found = candidate
                break

        # Ocultar activo previo (item o placeholder)
        self._hide_current(state)

        if found is None:
            # Ningún item en ventana → placeholder + retry en 60s
            self._show_placeholder(state)
            state.active_index = -1
            self._ensure_timer(state)
            state.timer.start(_RETRY_MS_WHEN_NO_ACTIVE)
            return

        # Mostrar el item encontrado
        state.active_index = found
        entry = state.playlist[found]
        self._show_item(state, entry.item_id)
        state.placeholder_visible = False
        self._ensure_timer(state)
        state.timer.start(max(1, int(entry.duration_seg)) * 1000)

    def _ensure_timer(self, state: _RotatorState) -> None:
        if state.timer is None:
            state.timer = QTimer(self)
            state.timer.setSingleShot(True)
            state.timer.timeout.connect(lambda s=state: self._advance(s))

    def _hide_current(self, state: _RotatorState) -> None:
        """Oculta el item activo (si había uno) o el placeholder."""
        if state.placeholder_visible and state.placeholder_scene_item_id is not None:
            self._set_scene_item(state, state.placeholder_scene_item_id, False)
            state.placeholder_visible = False
            return
        if 0 <= state.active_index < len(state.playlist):
            item_id = state.playlist[state.active_index].item_id
            scene_item = state.item_to_scene_item.get(item_id)
            if scene_item is not None:
                self._set_scene_item(state, scene_item, False)

    def _hide_all_items(self, state: _RotatorState) -> None:
        """Oculta todos los scene items del canal (no el placeholder)."""
        for si_id in state.item_to_scene_item.values():
            self._set_scene_item(state, si_id, False)

    def _show_item(self, state: _RotatorState, item_id: int) -> None:
        scene_item = state.item_to_scene_item.get(item_id)
        if scene_item is None:
            log.warning("Item %d no tiene sceneItemId; se salta.", item_id)
            return
        log.info("Canal '%s' → item_id=%d visible (sceneItemId=%d)",
                 state.scene_name, item_id, scene_item)
        self._set_scene_item(state, scene_item, True)

    def _show_placeholder(self, state: _RotatorState) -> None:
        if state.placeholder_scene_item_id is None:
            log.warning("Canal '%s': placeholder solicitado pero no existe "
                        "(sceneItemId None) — VLC verá stream sin nada",
                        state.scene_name)
            state.placeholder_visible = False
            return
        log.info("Canal '%s' → placeholder visible (negro) — nada en ventana "
                 "horaria o playlist vacía", state.scene_name)
        self._set_scene_item(state, state.placeholder_scene_item_id, True)
        state.placeholder_visible = True

    def _set_scene_item(self, state: _RotatorState, scene_item_id: int,
                         enabled: bool) -> None:
        if not self._connected:
            return
        with self._lock():
            try:
                self._raw_client().set_scene_item_enabled(
                    state.scene_name, scene_item_id, enabled,
                )
            except Exception as e:
                log.debug("set_scene_item_enabled(%s, %s) falló: %s",
                          scene_item_id, enabled, e)

    # ------------------------------------------------------------------
    # Consulta / debug
    # ------------------------------------------------------------------

    def get_status(self, canal_id: int) -> dict[str, Any]:
        """Estado en memoria del canal — para UI o tests."""
        state = self._rotators.get(canal_id)
        if not state:
            return {"canal_id": canal_id, "applied": False}
        active = None
        if 0 <= state.active_index < len(state.playlist):
            active = state.playlist[state.active_index].item_id
        # Segundos restantes hasta el próximo _advance:
        # - Si el rotador está pausado, `state.remaining_ms` guarda lo que
        #   quedaba al pausar (ver pause_rotator).
        # - Si está corriendo, se lee del propio QTimer singleShot.
        if state.is_paused:
            remaining_ms = int(state.remaining_ms)
        elif state.timer is not None and state.timer.isActive():
            r = state.timer.remainingTime()
            remaining_ms = int(r) if r > 0 else 0
        else:
            remaining_ms = 0
        return {
            "canal_id": canal_id,
            "applied": True,
            "scene_name": state.scene_name,
            "item_count": len(state.playlist),
            "active_index": state.active_index,
            "active_item_id": active,
            "rotator_running": (
                state.timer is not None and state.timer.isActive()
                and not state.is_paused
            ),
            "is_paused": state.is_paused,
            "placeholder_visible": state.placeholder_visible,
            "remaining_ms": remaining_ms,
        }

    # Método interno expuesto para tests headless: fuerza un tick del rotador.
    # No usar en runtime — el QTimer maneja las transiciones.
    def _test_tick(self, canal_id: int) -> None:
        state = self._rotators.get(canal_id)
        if state:
            self._advance(state)

    # ------------------------------------------------------------------
    # Ciclo de vida (Fase 1e)
    # ------------------------------------------------------------------

    def apply_all_habilitados(self) -> list[dict[str, Any]]:
        """Aplica en OBS todos los canales del modelo con habilitado=True.

        Idempotente — llamable en cada conexión / reconexión con OBS. Los
        canales apagados se ignoran (no se materializan en OBS hasta que el
        user los habilite explícitamente).

        Retorna una lista de dicts por canal procesado:
            [{"canal_id": int, "nombre": str, "ok": bool, "msg": str}, ...]
        """
        results: list[dict[str, Any]] = []
        for canal in self.canal_model.get_all_canales():
            if not canal["habilitado"]:
                continue
            ok, msg = self.apply_canal(int(canal["id"]))
            results.append({
                "canal_id": int(canal["id"]),
                "nombre": canal["nombre"],
                "ok": ok,
                "msg": msg,
            })
            if ok:
                log.info("Canal '%s' auto-aplicado a OBS.", canal["nombre"])
            else:
                log.warning(
                    "Canal '%s' no se pudo auto-aplicar: %s",
                    canal["nombre"], msg,
                )
        return results

    def shutdown_keeping_filters(self) -> None:
        """Detiene rotadores en memoria sin tocar el estado en OBS.

        Regla firme (memoria del proyecto): al cerrar la app, los filtros
        de canal quedan habilitados para que las pantallas remotas sigan
        recibiendo el último frame. No se llama a set_source_filter_enabled,
        no se ocultan scene items, no se remueve la escena contenedora.

        Solo se paran los QTimers del rotador para permitir que la app
        cierre limpia (sin que un tick disparado durante el cierre intente
        hablar con OBS).
        """
        for state in self._rotators.values():
            if state.timer is not None:
                try:
                    state.timer.stop()
                except Exception:
                    pass
                state.timer = None
        log.info(
            "CanalController shutdown limpio; %d rotador(es) detenidos, "
            "filtros de OBS preservados.",
            len(self._rotators),
        )
