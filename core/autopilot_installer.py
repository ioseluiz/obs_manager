"""Actualizacion automatica del script Autopilot v2 en un OBS local.

OBS carga `autopilot_v2.lua` desde la ruta que el operador registro en
Herramientas -> Scripts; esa ruta queda guardada en la coleccion de
escenas (`<config OBS>/basic/scenes/<coleccion>.json`, bajo
`modules["scripts-tool"][i]["path"]`). Este modulo:

1. Encuentra esas rutas (`find_registered_scripts`).
2. Compara la version del script embebido en la app con la que reporta
   el Lua en ejecucion (buzon `script_version`) y con la del archivo en
   disco (`read_script_version`).
3. Sobrescribe el archivo registrado con el embebido, dejando un `.bak`
   (`update_registered_scripts`).

Lo que NO puede hacer: pedirle a OBS que recargue scripts (obs-websocket
no lo expone). Tras actualizar el archivo, OBS usa la version nueva al
reiniciarse o al pulsar Herramientas -> Scripts -> Recargar scripts.

Modulo puro (sin PyQt). Solo tiene sentido con OBS en la misma maquina.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from core.autopilot_paths import LUA_V2_FILENAME, autopilot_v2_lua_path
from core.source_record_installer import LocalObs, parse_version

log = logging.getLogger(__name__)

_VERSION_RE = re.compile(r'^\s*local\s+SCRIPT_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def read_script_version(path: Path | str) -> str | None:
    """Version declarada en un autopilot_v2.lua (`local SCRIPT_VERSION = "x.y.z"`)."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _VERSION_RE.search(text)
    return m.group(1) if m else None


def bundled_script_version() -> str | None:
    return read_script_version(autopilot_v2_lua_path())


def is_newer(candidate: str | None, than: str | None) -> bool:
    """True si `candidate` es estrictamente mas nueva que `than`.
    Versiones no parseables cuentan como 0.0.0."""
    a = parse_version(candidate) or (0, 0, 0)
    b = parse_version(than) or (0, 0, 0)
    return a > b


def obs_config_dir(local: LocalObs) -> Path:
    """Carpeta de configuracion de OBS: portable -> <raiz>/config/obs-studio;
    instalado -> %APPDATA%/obs-studio."""
    if local.portable:
        return local.root / "config" / "obs-studio"
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "obs-studio"


@dataclass
class RegisteredScript:
    path: Path
    collection: str
    exists: bool
    version: str | None

    def describe(self) -> str:
        ver = self.version or ("?" if self.exists else "archivo no existe")
        return f"{self.path} (v{ver}, colección '{self.collection}')"


def find_registered_scripts(config_dir: Path | str,
                            filename: str = LUA_V2_FILENAME) -> list[RegisteredScript]:
    """Rutas de `filename` registradas en Herramientas -> Scripts, leidas de
    todas las colecciones de escenas. Sin duplicados (misma ruta en varias
    colecciones se devuelve una vez)."""
    scenes_dir = Path(config_dir) / "basic" / "scenes"
    found: list[RegisteredScript] = []
    seen: set[str] = set()
    if not scenes_dir.is_dir():
        return found
    for collection_file in sorted(scenes_dir.glob("*.json")):
        try:
            data = json.loads(collection_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.debug("No se pudo leer %s: %s", collection_file, exc)
            continue
        entries = (data.get("modules") or {}).get("scripts-tool") or []
        for entry in entries:
            raw = (entry or {}).get("path") or ""
            if not raw or Path(raw).name.lower() != filename.lower():
                continue
            path = Path(raw.replace("/", os.sep))
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            exists = path.is_file()
            found.append(RegisteredScript(
                path=path, collection=collection_file.stem, exists=exists,
                version=read_script_version(path) if exists else None,
            ))
    return found


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class UpdateResult:
    path: Path
    ok: bool
    changed: bool
    message: str


def update_registered_scripts(targets: list[RegisteredScript],
                              source: Path | None = None) -> list[UpdateResult]:
    """Sobrescribe cada script registrado con el embebido. Deja `<nombre>.bak`
    del anterior. Si el contenido ya es identico, no toca nada."""
    source = Path(source) if source else autopilot_v2_lua_path()
    results: list[UpdateResult] = []
    if not source.is_file():
        for t in targets:
            results.append(UpdateResult(t.path, False, False,
                                        f"Script embebido no encontrado: {source}"))
        return results
    src_hash = _sha256(source)
    for t in targets:
        try:
            if t.path.resolve() == source.resolve():
                results.append(UpdateResult(t.path, True, False,
                                            "Es el propio archivo embebido (desarrollo); nada que copiar."))
                continue
            if t.exists and _sha256(t.path) == src_hash:
                results.append(UpdateResult(t.path, True, False, "Ya estaba actualizado en disco."))
                continue
            t.path.parent.mkdir(parents=True, exist_ok=True)
            if t.exists:
                shutil.copy2(t.path, t.path.with_suffix(t.path.suffix + ".bak"))
            shutil.copy2(source, t.path)
            results.append(UpdateResult(t.path, True, True,
                                        f"Actualizado a v{read_script_version(source) or '?'} (respaldo .bak)."))
            log.info("autopilot_v2.lua actualizado en %s", t.path)
        except OSError as exc:
            results.append(UpdateResult(t.path, False, False, f"No se pudo escribir: {exc}"))
    return results


@dataclass
class UpdatePlan:
    bundled_version: str | None
    running_version: str | None
    registered: list[RegisteredScript] = field(default_factory=list)

    @property
    def running_outdated(self) -> bool:
        return is_newer(self.bundled_version, self.running_version)

    @property
    def outdated_files(self) -> list[RegisteredScript]:
        return [r for r in self.registered
                if r.exists and is_newer(self.bundled_version, r.version)]

    @property
    def files_current_but_not_loaded(self) -> bool:
        """Archivo(s) ya actualizados en disco pero OBS sigue corriendo la
        version vieja: falta recargar scripts / reiniciar OBS."""
        return (self.running_outdated and bool(self.registered)
                and not self.outdated_files
                and any(r.exists for r in self.registered))


def plan_update(local: LocalObs | None, running_version: str | None) -> UpdatePlan:
    plan = UpdatePlan(bundled_version=bundled_script_version(), running_version=running_version)
    if local is not None:
        try:
            plan.registered = find_registered_scripts(obs_config_dir(local))
        except Exception as exc:
            log.debug("find_registered_scripts fallo: %s", exc)
    return plan
