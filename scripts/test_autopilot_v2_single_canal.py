"""Prueba end-to-end de Fase B del port de Autopilot v2.

Verifica que `obs_scripts/autopilot_v2.lua` instalado en OBS puede
mantener la rotacion de UN canal multi-salida (modo scene_items)
cuando la app cliente deja de enviar heartbeats.

Pre-requisitos:
  - OBS corriendo con WebSocket habilitado.
  - Plugin Source Record (Exeldro) instalado en OBS.
  - Script `autopilot_v2.lua` registrado en OBS
    (Tools -> Scripts -> + -> autopilot_v2.lua).
  - Firewall local permite UDP inbound a 127.0.0.1 (loopback suele estar ok).

Flujo:
  1) Conecta a OBS.
  2) Verifica que el script Lua v2 esta instalado.
  3) Crea escena contenedora `__ap_v2_test__` con 2 color sources como
     scene items.
  4) Adjunta filtro Source Record `udp_out` apuntando a
     udp://127.0.0.1:<puerto>.
  5) Levanta listener UDP local en el mismo puerto.
  6) Publica config v2 con 1 canal (duration_seg=5s).
  7) Envia heartbeats durante ~15s → verifica mode=standby.
  8) Deja de enviar heartbeats por ~40s → el Lua debe entrar en active y
     empezar a rotar.
  9) En active, verifica que:
     - El filtro udp_out quedo habilitado.
     - Bytes UDP recibidos aumentan sostenidamente (>100 KB en 10s).
     - active_scene_item_id del state publicado por el Lua cambia entre
       los dos scene items (al menos una rotacion observada).
  10) Cleanup: oculta ambos items, remueve filtro, remueve escena.

Uso minimo::

    python scripts/test_autopilot_v2_single_canal.py --password <pwd>

Con puerto UDP especifico (default 7801)::

    python scripts/test_autopilot_v2_single_canal.py --password <pwd> --udp-port 7801

Exit code 0 si todas las verificaciones pasan; 1 en la primera falla.
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.autopilot_client import AutopilotClientV2  # noqa: E402

LOG = logging.getLogger("autopilot_v2_test")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

SCENE = "__ap_v2_test__"
ITEM_RED = "__ap_v2_test_red__"
ITEM_BLUE = "__ap_v2_test_blue__"
FILTER_NAME = "udp_out"
FILTER_KIND = "source_record_filter"
CANAL_ID_TEST = 999
DURATION_PER_ITEM = 5  # segundos
HEARTBEAT_PHASE_SEC = 15
NO_HEARTBEAT_PHASE_SEC = 40
UDP_CHECK_WINDOW_SEC = 10


# ---------------------------------------------------------------------------
# Infra: cargar .env, listener UDP, helpers
# ---------------------------------------------------------------------------

def _load_env_from_appdata():
    localappdata = os.getenv("LOCALAPPDATA")
    if not localappdata:
        return
    env_path = Path(localappdata) / "OBS_Automation_Manager" / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path)


class UdpByteCounter:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.bytes_received = 0
        self.packets = 0
        self._sock = None
        self._thread = None
        self._running = False

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        LOG.info("UDP listener en %s:%d", self.host, self.port)

    def _loop(self):
        while self._running:
            try:
                data, _ = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self.bytes_received += len(data)
            self.packets += 1

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=2)


def _quiet(fn, *args):
    """Llama a un metodo de obsws-python silenciando el logger. Ignora errores."""
    logger = logging.getLogger("obsws_python.reqs")
    prev = logger.level
    logger.setLevel(logging.CRITICAL)
    try:
        try:
            return fn(*args)
        except Exception as e:
            LOG.debug("quiet call %s fallo: %s", fn.__name__, e)
            return None
    finally:
        logger.setLevel(prev)


# ---------------------------------------------------------------------------
# OBS setup / cleanup
# ---------------------------------------------------------------------------

def _pick_color_kind(client):
    resp = client.get_input_kind_list(False)
    kinds = getattr(resp, "input_kinds", None) or getattr(resp, "inputKinds", [])
    for c in ("color_source_v3", "color_source_v2", "color_source"):
        if c in kinds:
            return c
    raise RuntimeError(f"No hay color_source disponible. Kinds: {sorted(kinds)}")


def _setup_scene_and_items(client, udp_port: int):
    """Crea escena contenedora con 2 color items + filtro Source Record.

    Devuelve (scene_item_id_red, scene_item_id_blue).
    """
    _cleanup(client)  # idempotente

    color_kind = _pick_color_kind(client)
    client.create_scene(SCENE)

    # Red
    client.create_input(SCENE, ITEM_RED, color_kind,
                        {"color": 0xFF0000FF, "width": 640, "height": 360}, True)
    resp_red = client.get_scene_item_id(SCENE, ITEM_RED, 0)
    red_id = int(getattr(resp_red, "scene_item_id", 0))

    # Blue
    client.create_input(SCENE, ITEM_BLUE, color_kind,
                        {"color": 0xFFFF0000, "width": 640, "height": 360}, True)
    resp_blue = client.get_scene_item_id(SCENE, ITEM_BLUE, 0)
    blue_id = int(getattr(resp_blue, "scene_item_id", 0))

    # Hide blue inicialmente para arrancar en red.
    client.set_scene_item_enabled(SCENE, red_id, True)
    client.set_scene_item_enabled(SCENE, blue_id, False)

    # Filtro Source Record udp_out
    filter_settings = {
        "stream_mode": 1,
        "server": f"udp://127.0.0.1:{udp_port}",
        "key": "",
        "encoder": "x264",
        "bitrate": 1500,
        "rate_control": "CBR",
        "scale_type": 3,
        "keyint_sec": 2,
        "profile": "high",
        "tune": "zerolatency",
        "preset": "veryfast",
    }
    client.create_source_filter(SCENE, FILTER_NAME, FILTER_KIND, filter_settings)
    # El filter viene habilitado por default. Explicito para claridad:
    client.set_source_filter_enabled(SCENE, FILTER_NAME, True)

    LOG.info("Escena '%s' lista: red_id=%d, blue_id=%d, filtro '%s' → %s",
             SCENE, red_id, blue_id, FILTER_NAME,
             filter_settings["server"])
    return red_id, blue_id


def _cleanup(client):
    _quiet(lambda: client.remove_source_filter(SCENE, FILTER_NAME))
    _quiet(lambda: client.remove_input(ITEM_RED))
    _quiet(lambda: client.remove_input(ITEM_BLUE))
    _quiet(lambda: client.remove_scene(SCENE))


# ---------------------------------------------------------------------------
# Verificaciones
# ---------------------------------------------------------------------------

def _check(cond: bool, msg: str) -> None:
    if cond:
        LOG.info("  ok - %s", msg)
    else:
        LOG.error("FAIL: %s", msg)
        raise AssertionError(msg)


def _assert_filter_enabled(client):
    resp = client.get_source_filter(SCENE, FILTER_NAME)
    enabled = bool(getattr(resp, "filter_enabled",
                           getattr(resp, "filterEnabled", False)))
    _check(enabled, "filtro udp_out habilitado")


def _assert_state_canal(ap: AutopilotClientV2, expected_mode: str,
                        canal_id: int, label: str):
    state = ap.read_state()
    _check(state is not None, f"{label}: read_state no es None")
    _check(state.get("mode") == expected_mode,
           f"{label}: mode = '{expected_mode}' (got '{state.get('mode')}')")
    canal_entry = None
    for c in state.get("canales", []):
        if int(c.get("canal_id", -1)) == canal_id:
            canal_entry = c
            break
    _check(canal_entry is not None,
           f"{label}: canal {canal_id} presente en state")
    return canal_entry


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def run(args):
    try:
        from obsws_python import ReqClient
    except ImportError:
        LOG.error("obsws-python no instalado. pip install obsws-python")
        return 2

    LOG.info("=== Fase B smoke test: Autopilot v2 con 1 canal scene_items ===")
    LOG.info("Conectando a OBS %s:%d ...", args.host, args.port)
    client = ReqClient(host=args.host, port=args.port,
                       password=args.password, timeout=5.0)

    # Stub minimo compatible con AutopilotClientV2 (espera .client).
    class _ObsStub:
        pass
    obs_stub = _ObsStub()
    obs_stub.client = client

    ap = AutopilotClientV2(obs_stub)

    LOG.info("Verificando que autopilot_v2.lua esta instalado ...")
    if not ap.is_installed():
        LOG.error("Buzones v2 no encontrados en OBS. ¿Esta cargado "
                  "autopilot_v2.lua en Tools -> Scripts?")
        return 2
    LOG.info("  ok - script v2 instalado (version=%s)", ap.script_version())

    listener = UdpByteCounter(args.udp_host, args.udp_port)
    try:
        listener.start()
        red_id, blue_id = _setup_scene_and_items(client, args.udp_port)

        canales = [{
            "canal_id": CANAL_ID_TEST,
            "modo_rotacion": "scene_items",
            "scene_name": SCENE,
            "filter_name": FILTER_NAME,
            "playlist": [
                {"name": ITEM_RED, "scene_item_id": red_id,
                 "duration_seg": DURATION_PER_ITEM},
                {"name": ITEM_BLUE, "scene_item_id": blue_id,
                 "duration_seg": DURATION_PER_ITEM},
            ],
        }]
        version = ap.publish_config(canales)
        LOG.info("Config v%d publicada (1 canal, 2 items de %ds)",
                 version, DURATION_PER_ITEM)

        # ---------- Fase 1: heartbeats activos ----------
        LOG.info("Fase 1: heartbeats por %ds (esperado mode=standby)",
                 HEARTBEAT_PHASE_SEC)
        hb_end = time.monotonic() + HEARTBEAT_PHASE_SEC
        while time.monotonic() < hb_end:
            ap.send_heartbeat()
            time.sleep(5)
        _assert_state_canal(ap, "standby", CANAL_ID_TEST,
                            "despues de 15s con heartbeat")
        _assert_filter_enabled(client)

        bytes_t0 = listener.bytes_received
        LOG.info("Bytes UDP recibidos tras Fase 1: %d (standby, filtro vivo)",
                 bytes_t0)
        _check(bytes_t0 > 100 * 1024,
               "stream UDP emite durante standby (>100 KB)")

        # ---------- Fase 2: dejar de mandar heartbeats ----------
        LOG.info("Fase 2: deteniendo heartbeats por %ds (esperado "
                 "mode→active)", NO_HEARTBEAT_PHASE_SEC)
        time.sleep(NO_HEARTBEAT_PHASE_SEC)

        canal_entry = _assert_state_canal(
            ap, "active", CANAL_ID_TEST, "despues de 40s sin heartbeat")
        active_idx_at_switch = int(canal_entry.get("active_index", 0))
        active_item_at_switch = int(canal_entry.get("active_scene_item_id", 0))
        LOG.info("Al cambiar a active: active_index=%d, active_scene_item_id=%d",
                 active_idx_at_switch, active_item_at_switch)
        _check(active_item_at_switch in (red_id, blue_id),
               "active_scene_item_id es uno de los dos items validos")

        # ---------- Fase 3: observar rotacion sostenida ----------
        LOG.info("Fase 3: observando rotacion durante %ds",
                 UDP_CHECK_WINDOW_SEC + DURATION_PER_ITEM)
        bytes_before = listener.bytes_received
        changed = False
        poll_end = time.monotonic() + UDP_CHECK_WINDOW_SEC + DURATION_PER_ITEM
        while time.monotonic() < poll_end:
            time.sleep(1)
            entry = _assert_state_canal(ap, "active", CANAL_ID_TEST,
                                        "polling en active")
            current_item = int(entry.get("active_scene_item_id", 0))
            if current_item != active_item_at_switch and current_item != 0:
                changed = True
        _check(changed,
               "active_scene_item_id cambio durante la ventana (rotacion activa)")
        bytes_after = listener.bytes_received
        delta = bytes_after - bytes_before
        LOG.info("Bytes UDP en ventana de %ds durante active: %d",
                 UDP_CHECK_WINDOW_SEC + DURATION_PER_ITEM, delta)
        _check(delta > 100 * 1024,
               "stream UDP sigue emitiendo durante active (>100 KB)")
        _assert_filter_enabled(client)

        LOG.info("=== TODO OK ===")
        return 0

    finally:
        LOG.info("Cleanup ...")
        listener.stop()
        _cleanup(client)


def main():
    _load_env_from_appdata()

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=os.getenv("OBS_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.getenv("OBS_PORT", "4455")))
    p.add_argument("--password", default=os.getenv("OBS_PASSWORD", ""))
    p.add_argument("--udp-host", default="127.0.0.1")
    p.add_argument("--udp-port", type=int, default=7801)
    args = p.parse_args()

    try:
        return run(args)
    except AssertionError:
        return 1
    except Exception:
        LOG.exception("Error inesperado")
        return 1


if __name__ == "__main__":
    sys.exit(main())
