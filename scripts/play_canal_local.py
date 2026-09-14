"""Recibe UDP en el puerto del canal y lo reproduce localmente vía ffplay.

El truco: Python bindea el socket UDP (Python.exe ya está autorizado por
el firewall de Windows), lee los packets, y los pipea por stdin a ffplay.
ffplay lee stdin — nunca bindea el puerto UDP, así que el firewall no lo
bloquea.

Requiere ffplay en el PATH (instalar con `winget install Gyan.FFmpeg` y
reiniciar la terminal para que agarre el PATH).

Uso::

    venv\\Scripts\\python.exe scripts\\play_canal_local.py 9001

Con la app transmitiendo el canal en udp://127.0.0.1:9001. Cerrar con Ctrl+C.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/play_canal_local.py <puerto>")
    port = int(sys.argv[1])

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
    print(f"Cerrar con Ctrl+C.\n")

    proc = subprocess.Popen(
        [
            "ffplay",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-analyzeduration", "1000000",
            "-probesize", "1000000",
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
