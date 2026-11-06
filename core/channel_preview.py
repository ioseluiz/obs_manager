"""UDP preview for both source runs and the frozen Windows application."""
from __future__ import annotations

import ipaddress
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
from urllib.parse import urlsplit

from PyQt6.QtCore import QObject, pyqtSignal


def find_ffplay():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    bundled = root / 'vendor' / 'ffmpeg' / 'bin' / 'ffplay.exe'
    return str(bundled) if bundled.is_file() else shutil.which('ffplay')


def udp_endpoint(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'udp' or not parsed.hostname or not parsed.port:
        raise ValueError('El canal necesita una dirección UDP y un puerto válidos.')
    return parsed.hostname, parsed.port


def can_receive_locally(host):
    try:
        address = ipaddress.ip_address(socket.gethostbyname(host))
        if address.is_multicast or address.is_loopback or address.is_unspecified:
            return True
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((str(address), 9))
            return probe.getsockname()[0] == str(address)
    except OSError:
        return False


class UdpPreview(QObject):
    unavailable = pyqtSignal(str)

    def __init__(self, host, port, title, executable, parent=None):
        super().__init__(parent)
        self.host, self.port = host, port
        self.title, self.executable = title, executable
        self._stop = threading.Event()
        self._socket = None
        self._process = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._socket:
            self._socket.close()
        if self._process and self._process.poll() is None:
            self._process.terminate()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(3)

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                self._socket = sock
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
                sock.bind(('0.0.0.0', self.port))
                address = socket.gethostbyname(self.host)
                if ipaddress.ip_address(address).is_multicast:
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                    socket.inet_aton(address) + socket.inet_aton('0.0.0.0'))
                # Wait before launching the player, so no empty player lingers.
                sock.settimeout(5)
                first, _ = sock.recvfrom(65535)
                if self._stop.is_set():
                    return
                self._process = subprocess.Popen([
                    self.executable, '-loglevel', 'error', '-fflags', 'nobuffer',
                    '-flags', 'low_delay', '-analyzeduration', '1000000',
                    '-probesize', '1000000', '-x', '640', '-y', '360',
                    '-window_title', f'Preview UDP: {self.title}', '-f', 'mpegts',
                    '-i', 'pipe:0'], stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                self._process.stdin.write(first)
                self._process.stdin.flush()
                sock.settimeout(1)
                idle = 0
                while not self._stop.is_set() and self._process.poll() is None:
                    try:
                        packet, _ = sock.recvfrom(65535)
                    except socket.timeout:
                        idle += 1
                        if idle >= 10:
                            raise TimeoutError('El canal dejó de enviar vídeo UDP.')
                        continue
                    idle = 0
                    self._process.stdin.write(packet)
                    self._process.stdin.flush()
        except BrokenPipeError:
            pass  # The user closed the player.
        except (OSError, ValueError) as exc:
            if not self._stop.is_set():
                self.unavailable.emit(str(exc))
        finally:
            proc = self._process
            if proc:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                if proc.stdin:
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass
            self._socket = None
