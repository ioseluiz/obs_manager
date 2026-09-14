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
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.output_adapter import OutputAdapter, FILTER_NAME

log = logging.getLogger(__name__)


@dataclass
class _RotatorState:
    """Estado en memoria del rotador interno de un canal."""
    canal_id: int
    scene_name: str
    # canal_item_id -> obs sceneItemId (para SetSceneItemEnabled)
    item_to_scene_item: dict[int, int] = field(default_factory=dict)
    # Orden efectivo: lista de (canal_item_id, duration_seg)
    playlist: list[tuple[int, int]] = field(default_factory=list)
    active_index: int = -1
    timer: QTimer | None = None
    # Pausa/resume: cuando is_paused=True, remaining_ms guarda el tiempo
    # que le quedaba al timer al pausarse. Al resumir, arranca un nuevo
    # timer con ese remaining. Ver pause_rotator/resume_rotator.
    is_paused: bool = False
    remaining_ms: int = 0


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

        Devuelve [{canal_item_id, secuencia_nombre, duration_seg}, ...]. Items
        que referencian secuencias inexistentes se saltan con warning.
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
                               ) -> dict[int, int]:
        """Wipe-and-rebuild: elimina scene items existentes y los recrea desde
        `effective_items` (en orden). Devuelve mapping canal_item_id → sceneItemId.

        Los items se crean deshabilitados. El rotador después activa uno a la vez.
        """
        client = self._raw_client()

        # 1. Wipe existentes (item_ids son locales a la scene)
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

        # 2. Recrear en orden, deshabilitados
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
        return mapping

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
            mapping = self._reconcile_scene_items(canal["nombre"], effective_items)

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
                (e["canal_item_id"], e["duration_seg"]) for e in effective_items
            ]
            state.active_index = -1
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
        """Arranca el ciclo del rotador de este canal si tiene items."""
        state = self._rotators.get(canal_id)
        if not state:
            log.warning("start_rotator sin estado para canal %d; ¿faltó apply?",
                        canal_id)
            return
        if not state.playlist:
            log.info("start_rotator canal %d sin items — nada que rotar.",
                     canal_id)
            return
        # Reinicio limpio si ya había timer corriendo
        if state.timer is not None:
            state.timer.stop()
        # Arranca en el primer item
        state.active_index = -1
        self._advance(state)

    def stop_rotator(self, canal_id: int) -> None:
        """Detiene el timer y oculta todos los items del canal."""
        state = self._rotators.get(canal_id)
        if not state:
            return
        if state.timer is not None:
            state.timer.stop()
            state.timer = None
        state.is_paused = False
        state.remaining_ms = 0
        if not self._connected:
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
        state.active_index = -1

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
        """Oculta el item activo, muestra el siguiente, agenda el próximo tick."""
        if not state.playlist:
            return

        # Ocultar activo (si había uno)
        if 0 <= state.active_index < len(state.playlist):
            prev_item_id = state.playlist[state.active_index][0]
            prev_scene_item = state.item_to_scene_item.get(prev_item_id)
            if prev_scene_item is not None and self._connected:
                with self._lock():
                    try:
                        self._raw_client().set_scene_item_enabled(
                            state.scene_name, prev_scene_item, False,
                        )
                    except Exception as e:
                        log.debug("hide previous item falló: %s", e)

        # Avanzar
        state.active_index = (state.active_index + 1) % len(state.playlist)
        next_item_id, duration_seg = state.playlist[state.active_index]
        next_scene_item = state.item_to_scene_item.get(next_item_id)
        if next_scene_item is None:
            log.warning("Item %d no tiene sceneItemId; se salta.", next_item_id)
            return

        if self._connected:
            with self._lock():
                try:
                    self._raw_client().set_scene_item_enabled(
                        state.scene_name, next_scene_item, True,
                    )
                except Exception as e:
                    log.warning("show next item falló: %s", e)

        # Agendar siguiente tick
        if state.timer is None:
            state.timer = QTimer(self)
            state.timer.setSingleShot(True)
            state.timer.timeout.connect(lambda s=state: self._advance(s))
        state.timer.start(max(1, int(duration_seg)) * 1000)

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
            active = state.playlist[state.active_index][0]
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
        }

    # Método interno expuesto para tests headless: fuerza un tick del rotador.
    # No usar en runtime — el QTimer maneja las transiciones.
    def _test_tick(self, canal_id: int) -> None:
        state = self._rotators.get(canal_id)
        if state:
            self._advance(state)
