"""Recibe UDP en el puerto del canal y lo reproduce localmente vía ffplay.

El truco: Python bindea el socket UDP (Python.exe ya está autorizado por
el firewall de Windows), lee los packets, y los pipea por stdin a ffplay.
ffplay lee stdin — nunca bindea el puerto UDP, así que el firewall no lo
bloquea.

Requiere ffplay en el PATH (instalar con `winget install Gyan.FFmpeg` y
reiniciar la terminal para que agarre el PATH).

Uso::

    venv\\Scripts\\python.exe scripts\\play_canal_local.py <puerto> [nombre_canal]

Con la app transmitiendo el canal en udp://127.0.0.1:<puerto>. La ventana
de ffplay arranca a 640x360 (redimensionable arrastrando bordes) y con
el nombre del canal en el título — así podés abrir varios previews
simultáneamente y distinguirlos.

Cerrar con Ctrl+C en esta terminal, o cerrando la ventana de ffplay.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys


# Tamaño inicial de la ventana de ffplay. Se puede agrandar arrastrando
# los bordes; el aspect ratio del stream se preserva.
_WINDOW_WIDTH = 640
_WINDOW_HEIGHT = 360


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/play_canal_local.py <puerto> [nombre_canal]")
    port = int(sys.argv[1])
    canal_name = sys.argv[2] if len(sys.argv) >= 3 else f"canal :{port}"

    if not shutil.which("ffplay"):
        sys.exit(
            "ffplay no está en el PATH.\n"
            "Instalar: `winget install Gyan.FFmpeg` (como admin)\n"
            "Después REINICIAR la terminal para que agarre el PATH."
        )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
    except OSError:
        pass
    sock.bind(("0.0.0.0", port))

    print(f"Escuchando UDP en 0.0.0.0:{port} y pipeando a ffplay...")
    print(f"Ventana: '{canal_name}' — arrancá con Ctrl+C acá o cerrando la ventana.\n")

    window_title = f"Preview: {canal_name}  (udp :{port})"
    proc = subprocess.Popen(
        [
            "ffplay",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-analyzeduration", "1000000",
            "-probesize", "1000000",
            # Tamaño inicial y título — redimensionable arrastrando bordes.
            # Sin estos, ffplay abre a la resolución nativa del stream
            # (1080p → ocupa casi todo el monitor). Ver README:
            # "Reproducir un canal en una pantalla".
            "-x", str(_WINDOW_WIDTH),
            "-y", str(_WINDOW_HEIGHT),
            "-window_title", window_title,
            "-f", "mpegts",
            "-i", "pipe:0",
        ],
        stdin=subprocess.PIPE,
    )

    try:
        while True:
            data, _ = sock.recvfrom(65535)
            try:
                proc.stdin.write(data)
                proc.stdin.flush()
            except BrokenPipeError:
                break
    except KeyboardInterrupt:
        print("\nInterrumpido por Ctrl+C.")
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait(timeout=2)
        sock.close()


if __name__ == "__main__":
    main()
