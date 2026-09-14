"""Test de OutputAdapter — unit + opcional live contra OBS.

Modo default (unit)
-------------------
Verifica la función pura `build_settings` con distintos canales-input.
No requiere OBS. Corre en <1s.

Modo live (--live)
------------------
Además del unit test:
- Crea una escena efímera en OBS.
- Aplica el filtro via OutputAdapter.apply().
- Verifica presencia + settings via get_effective_settings().
- Enciende + confirma UDP bytes en un listener local.
- Apaga + confirma cese de UDP.
- Elimina el filtro y la escena.

Requiere OBS abierto con WebSocket y Source Record cargado. Uso::

    python scripts/test_output_adapter.py                            # unit
    python scripts/test_output_adapter.py --live --password <pwd>    # + live
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
from pathlib import Path

# Project root en sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok — {msg}")


# ---------------------------------------------------------------------------
# Unit tests (build_settings)
# ---------------------------------------------------------------------------

def run_unit_tests() -> None:
    from core.output_adapter import build_settings

    print("\n[Unit — build_settings defaults]")
    canal = {
        "nombre": "Piso3",
        "url_destino": "udp://10.0.0.5:9999",
        "encoder": "x264",
        "bitrate_kbps": 2500,
        "habilitado": True,
        "audio_track": 0,
    }
    s = build_settings(canal)
    _check(s["stream_mode"] == 1, "stream_mode = 1 (Always)")
    _check(s["server"] == "udp://10.0.0.5:9999", "server = url_destino")
    _check(s["key"] == "", "key vacío")
    _check(s["encoder"] == "x264", "encoder passthrough")
    _check(s["bitrate"] == 2500, "bitrate desde bitrate_kbps")
    _check(s["rate_control"] == "CBR", "rate_control fijo en CBR")
    _check(s["scale_type"] == 3, "scale_type fijo en 3")
    _check(s["keyint_sec"] == 2, "keyint_sec = 2 (streaming UDP requiere keyframes frecuentes)")
    _check(s["profile"] == "high", "profile = high (default OBS streaming)")
    _check(s["tune"] == "zerolatency", "tune = zerolatency (evita lookahead del encoder)")
    _check(s["preset"] == "veryfast", "preset = veryfast (default streaming OBS)")
    # Preset por canal (Opción B, Fase 2 full)
    _check(s["output_width"] == 1920, "output_width default = 1920")
    _check(s["output_height"] == 1080, "output_height default = 1080")
    _check(s["output_fps_num"] == 30, "output_fps_num default = 30")
    _check(s["output_fps_den"] == 1, "output_fps_den fijo = 1")
    _check("record_mode" not in s, "NO incluye record_mode (regla firme Fase 1)")
    _check("path" not in s, "NO incluye path (regla firme Fase 1)")

    print("\n[Unit — canal con preset 720p60]")
    canal_720p60 = dict(canal)
    canal_720p60["output_width"] = 1280
    canal_720p60["output_height"] = 720
    canal_720p60["output_fps"] = 60
    s60 = build_settings(canal_720p60)
    _check(s60["output_width"] == 1280, "720p60 width=1280 propagado")
    _check(s60["output_height"] == 720, "720p60 height=720 propagado")
    _check(s60["output_fps_num"] == 60, "720p60 fps_num=60 propagado")

    print("\n[Unit — build_settings con audio_track > 0]")
    canal["audio_track"] = 2
    s = build_settings(canal)
    _check(s["different_audio"] is True, "different_audio activado con audio_track > 0")
    _check(s["audio_track"] == 2, "audio_track propagado")

    print("\n[Unit — build_settings sin audio (track = 0)]")
    canal["audio_track"] = 0
    s = build_settings(canal)
    _check("different_audio" not in s, "different_audio omitido cuando audio_track = 0")
    _check("audio_track" not in s, "audio_track omitido cuando = 0")

    print("\n[Unit — encoder desconocido pasa con warning]")
    canal["encoder"] = "raro_encoder"
    s = build_settings(canal)
    _check(s["encoder"] == "raro_encoder", "encoder desconocido pasa tal cual")

    print("\n[Unit — bitrate custom]")
    canal["encoder"] = "qsv"
    canal["bitrate_kbps"] = 6000
    s = build_settings(canal)
    _check(s["bitrate"] == 6000, "bitrate custom aplicado")
    _check(s["encoder"] == "qsv", "encoder qsv válido")

    print("\n[Unit — encoder None cae en x264]")
    canal["encoder"] = None
    s = build_settings(canal)
    _check(s["encoder"] == "x264", "encoder None → x264 fallback")

    print("✓ Unit tests pasaron.")


# ---------------------------------------------------------------------------
# Live test (contra OBS real)
# ---------------------------------------------------------------------------

class UDPListener:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.bytes_received = 0
        self._running = False
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        except OSError:
            pass
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            try:
                data, _ = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self.bytes_received += len(data)

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


def run_live_test(host: str, port: int, password: str,
                  udp_port: int, duration: int) -> None:
    import obsws_python as obs
    from core.output_adapter import OutputAdapter, FILTER_NAME

    SCENE = "TestOutputAdapter"
    INPUT = "TestOutputAdapter_color"
    URL = f"udp://127.0.0.1:{udp_port}"

    print("\n[Live — conectando a OBS]")
    client = obs.ReqClient(host=host, port=port, password=password, timeout=5)

    def _quiet(fn, *args):
        import logging as _log
        lg = _log.getLogger("obsws_python.reqs")
        prev = lg.level
        lg.setLevel(_log.CRITICAL)
        try:
            try:
                return fn(*args)
            except Exception:
                return None
        finally:
            lg.setLevel(prev)

    def cleanup():
        _quiet(client.remove_source_filter, SCENE, FILTER_NAME)
        _quiet(client.remove_input, INPUT)
        _quiet(client.remove_scene, SCENE)

    listener = UDPListener("127.0.0.1", udp_port)
    listener.start()

    try:
        cleanup()
        client.create_scene(SCENE)
        client.create_input(SCENE, INPUT, "color_source_v3",
                            {"color": 0xFFFF0000, "width": 1920, "height": 1080}, True)
        client.set_current_program_scene(SCENE)
        time.sleep(1)

        adapter = OutputAdapter(client)
        canal = {
            "nombre": SCENE,
            "url_destino": URL,
            "encoder": "x264",
            "bitrate_kbps": 2500,
            "habilitado": True,
            "audio_track": 0,
        }

        print("\n[Live — apply]")
        ok, msg = adapter.apply(canal)
        _check(ok, f"apply retorna ok ({msg})")
        _check(adapter.is_present(SCENE), "is_present tras apply")
        eff = adapter.get_effective_settings(SCENE)
        _check(eff is not None and eff.get("server") == URL, "settings reflejan la url")

        print("\n[Live — enable + medir UDP]")
        baseline = listener.bytes_received
        ok, _ = adapter.enable(SCENE)
        _check(ok, "enable ok")
        _check(adapter.is_enabled(SCENE) is True, "is_enabled True tras enable")
        time.sleep(duration)
        received = listener.bytes_received - baseline
        _check(received > 100_000,
               f"UDP fluyó ({received:,} bytes en {duration}s)")

        print("\n[Live — disable]")
        ok, _ = adapter.disable(SCENE)
        _check(ok, "disable ok")
        _check(adapter.is_enabled(SCENE) is False, "is_enabled False tras disable")
        baseline2 = listener.bytes_received
        time.sleep(2)
        after_disable = listener.bytes_received - baseline2
        _check(after_disable < 50_000, f"UDP se detuvo ({after_disable:,} bytes en 2s post-disable)")

        print("\n[Live — apply idempotente (re-apply)]")
        ok, _ = adapter.apply(canal)
        _check(ok, "apply idempotente retorna ok")
        _check(adapter.is_present(SCENE), "filter sigue presente tras re-apply")

        print("\n[Live — remove]")
        ok, _ = adapter.remove(SCENE)
        _check(ok, "remove ok")
        _check(not adapter.is_present(SCENE), "filter ausente tras remove")

        print("\n[Live — remove idempotente]")
        ok, _ = adapter.remove(SCENE)
        _check(ok, "remove idempotente (filter ya no existía) retorna True")

        print("\n[Live — apply con habilitado=False respeta el flag]")
        canal["habilitado"] = False
        ok, _ = adapter.apply(canal)
        _check(ok, "apply(habilitado=False) ok")
        _check(adapter.is_enabled(SCENE) is False,
               "filter creado deshabilitado cuando canal.habilitado=False")

        print("✓ Live test pasó.")
    finally:
        cleanup()
        client.disconnect()
        listener.stop()


def main():
    ap = argparse.ArgumentParser(description="Test OutputAdapter (unit + live)")
    ap.add_argument("--live", action="store_true",
                    help="Además del unit test, corre el live test contra OBS real.")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=4455)
    ap.add_argument("--password", default="")
    ap.add_argument("--udp-port", type=int, default=9999)
    ap.add_argument("--duration", type=int, default=6,
                    help="Segundos midiendo UDP en el live test (default: 6).")
    args = ap.parse_args()

    run_unit_tests()

    if args.live:
        run_live_test(args.host, args.port, args.password,
                      args.udp_port, args.duration)

    print("\n✓ TODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
