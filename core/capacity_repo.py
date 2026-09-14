"""Repositorio de calibraciones de capacidad por equipo (Fase 2a).

Persiste el resultado de la calibración automática de encoders (cuántos
canales aguanta cada encoder a 1080p30 en este equipo específico) en un
JSON bajo `%LOCALAPPDATA%\\OBS_Automation_Manager\\calibrations.json`.

El archivo está *keyed por fingerprint del equipo* — si el equipo cambia
(hostname distinto, CPU threads distintos, GPU distinta, OBS major bump)
la entry se invalida automáticamente y hay que re-calibrar.

Este módulo es puro: no toca OBS, no depende de PyQt, sólo stdlib. El
`calibration_engine` (2b) lo llamará para guardar los resultados; los
consumers (validador de conexión en 2d, settings en 2e) lo llamarán
para leer.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Fingerprint del equipo
# -----------------------------------------------------------------------

@dataclass(frozen=True)
class Fingerprint:
    """Identifica un equipo de forma estable para calibración.

    Se compara por igualdad completa: cualquier cambio invalida la entry.
    - hostname: cambio típico al mover disco a otra máquina.
    - cpu_threads: cambio típico al upgrade de CPU.
    - gpu: string reportado por wmic o similar; cambio al agregar/cambiar GPU.
    - obs_major: bump de mayor de OBS puede cambiar encoders disponibles.
    """
    hostname: str
    cpu_threads: int
    gpu: str
    obs_major: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Fingerprint":
        return cls(
            hostname=str(d["hostname"]),
            cpu_threads=int(d["cpu_threads"]),
            gpu=str(d["gpu"]),
            obs_major=int(d["obs_major"]),
        )


def detect_fingerprint(obs_major: int, gpu_override: str | None = None) -> Fingerprint:
    """Snapshot del equipo actual.

    `obs_major` lo debe pasar el caller (leído de obs_client.get_version).
    `gpu_override` sirve para tests headless que no quieren tocar wmic.
    """
    hostname = socket.gethostname()
    cpu_threads = os.cpu_count() or 0
    if gpu_override is not None:
        gpu = gpu_override
    else:
        gpu = _detect_gpu()
    return Fingerprint(
        hostname=hostname,
        cpu_threads=int(cpu_threads),
        gpu=gpu,
        obs_major=int(obs_major),
    )


def _detect_gpu() -> str:
    """Devuelve un string identificador de la GPU principal.

    Windows: wmic. Otros SO: fallback a `platform.processor()` como
    señuelo estable — la app en producción corre en Windows, pero
    quiero que los tests headless funcionen en cualquier plataforma.
    """
    if sys.platform != "win32":
        return f"non-windows:{platform.processor() or 'unknown'}"
    try:
        import subprocess
        # Preferir PowerShell por CIM (wmic está deprecado y sale en Win11).
        out = subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object -First 1 -ExpandProperty Name"
            ],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8", errors="replace").strip()
        if out:
            return out
    except Exception as e:
        log.warning("Detección de GPU falló, se usa 'unknown': %s", e)
    return "unknown"


# -----------------------------------------------------------------------
# Entry de calibración
# -----------------------------------------------------------------------

@dataclass(frozen=True)
class CapacityEntry:
    """Resultado persistido de una calibración para un equipo.

    - fingerprint: el equipo al que aplica esta calibración.
    - encoders: mapping `{encoder_shortname: nmax_1080p30}`.
      Los encoders que fallaron en calibración no aparecen (o aparecen
      con 0). Los que no se probaron tampoco aparecen.
    - calibrated_at: timestamp ISO 8601 UTC — para mostrar "última
      calibración: hace 3 días" en la UI de Settings.
    - notes: string libre — la app puede escribir observaciones (por
      ej. "canceled by user, using conservative fallback").
    """
    fingerprint: Fingerprint
    encoders: dict[str, int] = field(default_factory=dict)
    calibrated_at: str = ""
    notes: str = ""

    def with_encoder(self, encoder: str, nmax: int) -> "CapacityEntry":
        new_map = dict(self.encoders)
        new_map[encoder] = int(nmax)
        return CapacityEntry(
            fingerprint=self.fingerprint,
            encoders=new_map,
            calibrated_at=self.calibrated_at,
            notes=self.notes,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint.as_dict(),
            "encoders": dict(self.encoders),
            "calibrated_at": self.calibrated_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CapacityEntry":
        return cls(
            fingerprint=Fingerprint.from_dict(d["fingerprint"]),
            encoders={str(k): int(v) for k, v in (d.get("encoders") or {}).items()},
            calibrated_at=str(d.get("calibrated_at") or ""),
            notes=str(d.get("notes") or ""),
        )

    @classmethod
    def new(cls, fp: Fingerprint, notes: str = "") -> "CapacityEntry":
        """Crea una entry vacía con timestamp UTC actual."""
        return cls(
            fingerprint=fp,
            encoders={},
            calibrated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            notes=notes,
        )


# -----------------------------------------------------------------------
# Repositorio: load / save / lookup por fingerprint
# -----------------------------------------------------------------------

def default_repo_path() -> Path:
    """Path por default: `%LOCALAPPDATA%\\OBS_Automation_Manager\\calibrations.json`.

    En sistemas no-Windows cae a `~/.local/share/OBS_Automation_Manager/`.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
    else:
        base = str(Path.home() / ".local" / "share")
    return Path(base) / "OBS_Automation_Manager" / "calibrations.json"


class CapacityRepo:
    """Load/save de calibraciones. Compatible con app cerrando/reabriendo.

    El JSON en disco tiene forma::

        {
          "schema_version": 1,
          "entries": [<CapacityEntry.as_dict()>, ...]
        }

    Se re-escribe entero cada `save` — el archivo es chico (bytes) y
    escrito atómicamente vía tmp + rename para no dejarlo corrupto si
    la app muere a mitad.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: Path | None = None):
        self._path = path or default_repo_path()

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load_all(self) -> list[CapacityEntry]:
        """Devuelve todas las entries persistidas. Vacío si no existe el file."""
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("calibrations.json ilegible (%s); se ignora y reinicia.", e)
            return []
        if not isinstance(data, dict):
            return []
        entries_raw = data.get("entries") or []
        result: list[CapacityEntry] = []
        for raw in entries_raw:
            try:
                result.append(CapacityEntry.from_dict(raw))
            except (KeyError, TypeError, ValueError) as e:
                log.warning("Entry inválida en calibrations.json — se salta: %s", e)
        return result

    def save_all(self, entries: list[CapacityEntry]) -> None:
        """Reescribe el archivo entero. Atómico via tmp + rename."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "entries": [e.as_dict() for e in entries],
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------
    # Lookup / upsert por fingerprint
    # ------------------------------------------------------------------

    def get(self, fp: Fingerprint) -> CapacityEntry | None:
        """Devuelve la entry para este fingerprint o None."""
        for e in self.load_all():
            if e.fingerprint == fp:
                return e
        return None

    def upsert(self, entry: CapacityEntry) -> None:
        """Guarda o actualiza la entry cuyo fingerprint matchee."""
        all_entries = self.load_all()
        found = False
        new_list: list[CapacityEntry] = []
        for e in all_entries:
            if e.fingerprint == entry.fingerprint:
                new_list.append(entry)
                found = True
            else:
                new_list.append(e)
        if not found:
            new_list.append(entry)
        self.save_all(new_list)

    def delete(self, fp: Fingerprint) -> bool:
        """Elimina la entry con este fingerprint. Devuelve True si borró algo."""
        all_entries = self.load_all()
        remaining = [e for e in all_entries if e.fingerprint != fp]
        if len(remaining) == len(all_entries):
            return False
        self.save_all(remaining)
        return True
