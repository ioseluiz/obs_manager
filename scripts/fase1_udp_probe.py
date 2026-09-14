"""Fase 1 discovery — ¿Source Record puede emitir a UDP?

La Fase 0 verificó que el filtro produce frames a un archivo MP4. Este probe
extiende a la pregunta operativa de Fase 1: ¿puede el mismo filtro emitir a
un endpoint `udp://<host>:<puerto>` que un consumidor externo pueda recibir?

Estrategia:
1. Abre un socket UDP en 127.0.0.1:<puerto> (default 9999) y cuenta bytes
   recibidos en un thread daemon.
2. Crea una escena `Fase1_UDP` con un color source como estímulo.
3. Configura un filtro Source Record en modo **stream** (no record) apuntando
   a `udp://127.0.0.1:<puerto>`.
4. Enciende el filtro N segundos.
5. Reporta bytes recibidos por el socket.

Si el filtro no expone `stream_mode`/`server` como campos directos, el probe
prueba variantes de settings (record_mode con paths tipo `udp://...`, distintos
rec_format, etc.) hasta encontrar la que hace fluir bytes por el socket.

Uso mínimo::

    python scripts/fase1_udp_probe.py --password <pwd>

Con puerto específico::

    python scripts/fase1_udp_probe.py --password <pwd> --udp-port 7777

Exit code: 0 si algún variant emitió bytes (≥ 100 KB en la ventana);
1 si ningún variant produjo salida al socket.
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

try:
    import obsws_python as obs
except ImportError:
    sys.exit("Falta obsws-python. Ejecute: pip install obsws-python")

LOG = logging.getLogger("fase1udp")

SCENE = "Fase1_UDP"
INPUT = "Fase1_UDP_color"
FILTER_NAME = "fase1_udp_filter"

# Base común de settings de Source Record (verificado en Fase 0)
BASE_SETTINGS = {
    "encoder": "x264",
    "bitrate": 2500,
    "rate_control": "CBR",
    "scale_type": 3,
}


# ---------------------------------------------------------------------------
# UDP listener en thread daemon
# ---------------------------------------------------------------------------

class UDPListener:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.bytes_received = 0
        self.packets = 0
        self._running = False
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Buffer grande para no perder ráfagas
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        except OSError:
            pass
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.5)
        self._running = True
        self.bytes_received = 0
        self.packets = 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        LOG.info("Listener UDP escuchando en %s:%d", self.host, self.port)

    def _loop(self):
        while self._running:
            try:
                data, _addr = self._sock.recvfrom(65535)
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


# ---------------------------------------------------------------------------
# OBS setup / cleanup
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


def _quiet(client, meth, *args):
    """Llama a un método de obsws-python silenciando el logger. Ignora errores."""
    obsws_log = logging.getLogger("obsws_python.reqs")
    prev = obsws_log.level
    obsws_log.setLevel(logging.CRITICAL)
    try:
        try:
            return meth(*args)
        except Exception:
            return None
    finally:
        obsws_log.setLevel(prev)


def _cleanup(client):
    _quiet(client, client.remove_source_filter, SCENE, FILTER_NAME)
    _quiet(client, client.remove_input, INPUT)
    _quiet(client, client.remove_scene, SCENE)


def _pick_color_kind(client):
    resp = client.get_input_kind_list(False)
    kinds = getattr(resp, "input_kinds", None) or getattr(resp, "inputKinds", [])
    for c in ("color_source_v3", "color_source_v2", "color_source"):
        if c in kinds:
            return c
    raise RuntimeError(f"No hay color_source disponible. Kinds: {sorted(kinds)}")


def _setup_scene(client):
    kind = _pick_color_kind(client)
    _quiet(client, client.create_scene, SCENE)
    _quiet(client, client.create_input, SCENE, INPUT, kind,
           {"color": 0xFFFF0000, "width": 1920, "height": 1080}, True)
    client.set_current_program_scene(SCENE)
    time.sleep(1.0)


# ---------------------------------------------------------------------------
# Variantes de settings a probar
# ---------------------------------------------------------------------------

def _build_variants(url: str) -> list[dict]:
    """Devuelve variantes de settings ordenadas de más probable a menos.

    Basado en la locale del plugin (RecordMode / StreamMode / Server / Key)
    y en experimentación con record_mode.

    ⚠️ Algunas variantes de "record a udp://" pueden crashear OBS (visto
    en 2026-09-14 con V3 del setup original). El probe se detiene en la
    primera variante que produzca bytes; si querés ejecutar todas las
    variantes (para caracterizar el plugin), pasar --exhaustive.
    """
    v: list[dict] = []
    # V1 (GANADORA verificada 2026-09-14):
    # stream_mode = 1 (Always) + server con URL udp:// + key vacío.
    # Produjo 2.4 MB / 2046 paquetes en 8s con x264 @ 2500 kbps.
    v.append({
        **BASE_SETTINGS,
        "stream_mode": 1,
        "server": url,
        "key": "",
    })
    # V2: stream_mode = 2 (probablemente "Streaming" — sólo cuando OBS streamea).
    # Verificado que no produce bytes 2026-09-14.
    v.append({
        **BASE_SETTINGS,
        "stream_mode": 2,
        "server": url,
        "key": "",
    })
    # V3-V5: record_mode con URL como path. PELIGRO: puede crashear el plugin.
    # Solo se ejecutan con --exhaustive.
    v.append({
        **BASE_SETTINGS,
        "record_mode": 1,
        "path": url,
        "filename_formatting": "",
        "rec_format": "mpegts",
        "_dangerous": True,  # marcador — se filtra sin --exhaustive
    })
    v.append({
        **BASE_SETTINGS,
        "record_mode": 1,
        "path": url,
        "filename_formatting": "",
        "rec_format": "custom_ffmpeg",
        "muxer_settings": "",
        "_dangerous": True,
    })
    v.append({
        **BASE_SETTINGS,
        "record_mode": 1,
        "path": url,
        "filename_formatting": "",
        "rec_format": "flv",
        "_dangerous": True,
    })
    return v


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def _run_variant(client, listener: UDPListener, variant: dict, duration: int,
                 label: str) -> dict:
    LOG.info("=" * 60)
    LOG.info("Variante '%s': %s", label, variant)

    _quiet(client, client.remove_source_filter, SCENE, FILTER_NAME)
    client.create_source_filter(
        source_name=SCENE,
        filter_name=FILTER_NAME,
        filter_kind="source_record_filter",
        filter_settings=variant,
    )

    baseline_bytes = listener.bytes_received
    baseline_pkts = listener.packets

    client.set_source_filter_enabled(SCENE, FILTER_NAME, True)
    LOG.info("Filtro on. Midiendo %ds...", duration)
    time.sleep(duration)
    client.set_source_filter_enabled(SCENE, FILTER_NAME, False)
    time.sleep(1)

    delta_bytes = listener.bytes_received - baseline_bytes
    delta_pkts = listener.packets - baseline_pkts
    LOG.info("  → %d bytes en %d paquetes UDP", delta_bytes, delta_pkts)

    _quiet(client, client.remove_source_filter, SCENE, FILTER_NAME)

    return {
        "label": label,
        "variant": variant,
        "bytes": delta_bytes,
        "packets": delta_pkts,
        "produced": delta_bytes >= 100_000,  # ≥100 KB en ventana = flujo real
    }


def main():
    _load_env_from_appdata()

    ap = argparse.ArgumentParser(description="Fase 1 discovery — UDP output")
    ap.add_argument("--host", default=os.getenv("OBS_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.getenv("OBS_PORT", "4455")))
    ap.add_argument("--password", default=os.getenv("OBS_PASSWORD", ""))
    ap.add_argument("--udp-host", default="127.0.0.1",
                    help="Host donde escucha el listener (default: 127.0.0.1).")
    ap.add_argument("--udp-port", type=int, default=9999,
                    help="Puerto UDP a probar (default: 9999).")
    ap.add_argument("--duration", type=int, default=8,
                    help="Segundos por variante (default: 8).")
    ap.add_argument("--exhaustive", action="store_true",
                    help="Correr TODAS las variantes incluso después de encontrar "
                         "una ganadora, y también las marcadas peligrosas (algunas "
                         "pueden crashear el plugin de OBS).")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    url = f"udp://{args.udp_host}:{args.udp_port}"

    LOG.info("Conectando a OBS %s:%s ...", args.host, args.port)
    try:
        client = obs.ReqClient(host=args.host, port=args.port,
                               password=args.password, timeout=5)
    except Exception as e:
        sys.exit(f"No se pudo conectar a OBS: {e}")

    listener = UDPListener(args.udp_host, args.udp_port)
    listener.start()

    results = []
    try:
        _cleanup(client)
        _setup_scene(client)
        for i, v in enumerate(_build_variants(url), start=1):
            label = f"V{i}"
            is_dangerous = v.pop("_dangerous", False)
            if is_dangerous and not args.exhaustive:
                LOG.info("Saltando %s (variante peligrosa; usar --exhaustive "
                         "para forzarla).", label)
                continue
            result = _run_variant(client, listener, v, args.duration, label)
            results.append(result)
            if result["produced"] and not args.exhaustive:
                LOG.info("%s produjo salida UDP — detengo aquí "
                         "(usar --exhaustive para seguir probando).", label)
                break
    finally:
        _cleanup(client)
        client.disconnect()
        listener.stop()

    # -----------------------------------------------------------------------
    print()
    print("=" * 78)
    print("RESULTADOS UDP (URL destino: %s)" % url)
    print("=" * 78)
    print(f"{'Variante':<10} {'Bytes':<14} {'Paquetes':<12} {'¿Fluyó?':<10} Keys claves")
    for r in results:
        keys = ",".join(k for k in r["variant"].keys()
                        if k in ("stream_mode", "record_mode", "rec_format", "server", "path"))
        print(f"{r['label']:<10} {r['bytes']:<14,d} {r['packets']:<12,d} "
              f"{str(r['produced']):<10} {keys}")

    winners = [r for r in results if r["produced"]]
    print()
    if winners:
        w = winners[0]
        print("VEREDICTO: UDP FUNCIONA con Source Record.")
        print(f"  Variante ganadora: {w['label']}")
        print("  Settings:")
        for k, val in w["variant"].items():
            print(f"    {k}: {val!r}")
        sys.exit(0)
    print("VEREDICTO: Ninguna variante emitió UDP.")
    print("  Próximo paso: configurar un filtro Source Record via UI de OBS")
    print("  apuntando a un URL UDP y correr scripts/fase1_udp_inspect.py")
    print("  (aún no existe) para leer el schema real via WebSocket.")
    sys.exit(1)


if __name__ == "__main__":
    main()
