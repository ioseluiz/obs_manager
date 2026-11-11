"""Instalacion del plugin Source Record (Exeldro, GPL-2.0) en un OBS local
y exportacion de un paquete para un OBS remoto.

Todo el modelo multi-canal depende de este plugin (`source_record_filter`).
La app lo lleva embebido en `vendor/source-record/` (ver
scripts/bundle_source_record.py) en los dos layouts que OBS reconoce:

- `new`    : OBS >= 33  -> <dir>/source-record/source-record.dll + data/
- `legacy` : OBS <= 32  -> <dir>/source-record/bin/64bit/source-record.dll + data/
- `intree` : OBS <= 32 PORTABLE -> <raiz>/obs-plugins/64bit/source-record.dll
             + <raiz>/data/obs-plugins/source-record/  (OBS portable ignora
             ProgramData y solo carga <raiz>/plugins/ a partir de 33)

Donde <dir> es `C:\\ProgramData\\obs-studio\\plugins` para un OBS instalado
(escribible sin admin) o `<raiz>\\plugins` para un OBS portable 33+.

Modulo puro: sin PyQt. Las funciones devuelven (ok, msg) o lanzan solo
por bugs de programacion.
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from core import obs_launcher
from core.autopilot_paths import bundle_root
from core.output_adapter import FILTER_KIND

log = logging.getLogger(__name__)

PLUGIN_NAME = "source-record"
PLUGIN_VERSION = "0.5.0"
PLUGIN_FILTER_KIND = FILTER_KIND  # "source_record_filter"

LAYOUT_NEW = "new"
LAYOUT_LEGACY = "legacy"
LAYOUT_INTREE = "intree"
NEW_LAYOUT_MIN_MAJOR = 33


# ---------------------------------------------------------------------------
# Bundle embebido
# ---------------------------------------------------------------------------

def bundled_root() -> Path:
    return bundle_root() / "vendor" / PLUGIN_NAME


def _bundled_parts(layout: str) -> tuple[Path, Path]:
    """(ruta del dll, carpeta data) dentro del bundle para `layout`."""
    root = bundled_root()
    if layout == LAYOUT_NEW:
        base = root / "new" / PLUGIN_NAME
        return base / f"{PLUGIN_NAME}.dll", base / "data"
    base = root / "legacy" / PLUGIN_NAME
    return base / "bin" / "64bit" / f"{PLUGIN_NAME}.dll", base / "data"


def is_bundled() -> bool:
    try:
        return all(dll.is_file() and data.is_dir()
                   for dll, data in (_bundled_parts(LAYOUT_NEW), _bundled_parts(LAYOUT_LEGACY)))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Deteccion del OBS local
# ---------------------------------------------------------------------------

def exe_file_version(path) -> tuple[int, int, int] | None:
    """Version (major, minor, patch) del recurso VERSIONINFO de un .exe.

    Solo Windows; None si no se puede leer.
    """
    if sys.platform != "win32":
        return None
    try:
        version_dll = ctypes.WinDLL("version.dll")
        path_w = ctypes.c_wchar_p(str(path))
        size = version_dll.GetFileVersionInfoSizeW(path_w, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not version_dll.GetFileVersionInfoW(path_w, 0, size, buf):
            return None
        ptr = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not version_dll.VerQueryValueW(buf, ctypes.c_wchar_p("\\"),
                                          ctypes.byref(ptr), ctypes.byref(length)):
            return None

        class VS_FIXEDFILEINFO(ctypes.Structure):
            _fields_ = [("dwSignature", ctypes.c_uint32), ("dwStrucVersion", ctypes.c_uint32),
                        ("dwFileVersionMS", ctypes.c_uint32), ("dwFileVersionLS", ctypes.c_uint32),
                        ("dwProductVersionMS", ctypes.c_uint32), ("dwProductVersionLS", ctypes.c_uint32)]

        info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
        ms, ls = info.dwProductVersionMS, info.dwProductVersionLS
        return (ms >> 16, ms & 0xFFFF, ls >> 16)
    except Exception as exc:
        log.debug("exe_file_version(%s) fallo: %s", path, exc)
        return None


def parse_version(text) -> tuple[int, int, int] | None:
    """'32.1.2' / '33.0.1-beta2' -> (32, 1, 2). None si no parsea."""
    m = re.match(r"\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(text or ""))
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0))


@dataclass
class LocalObs:
    exe: Path
    root: Path
    portable: bool
    version: tuple[int, int, int] | None

    @property
    def major(self) -> int | None:
        return self.version[0] if self.version else None

    def describe(self) -> str:
        ver = ".".join(str(p) for p in self.version) if self.version else "versión desconocida"
        kind = "portable" if self.portable else "instalado"
        return f"OBS Studio {ver} ({kind}) en {self.root}"


def detect_local_obs(exe_hint: str | None = None) -> LocalObs | None:
    """Localiza el OBS de esta maquina: `exe_hint` (setting OBS_EXE_PATH) o
    registro / rutas comunes via obs_launcher.find_obs_executable()."""
    candidate = (exe_hint or "").strip() or obs_launcher.find_obs_executable()
    if not candidate or not Path(candidate).is_file():
        return None
    exe = Path(candidate).resolve()
    # <raiz>\bin\64bit\obs64.exe -> <raiz>
    root = exe.parents[2] if len(exe.parents) >= 3 else exe.parent
    portable = (root / "portable_mode.txt").exists() or (root / "portable_mode").exists()
    return LocalObs(exe=exe, root=root, portable=portable, version=exe_file_version(exe))


def programdata_plugins_dir() -> Path:
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(base) / "obs-studio" / "plugins"


# ---------------------------------------------------------------------------
# Plan + instalacion
# ---------------------------------------------------------------------------

@dataclass
class InstallPlan:
    layout: str
    target_root: Path
    files: list[tuple[Path, Path]]
    description: str

    @property
    def dll_target(self) -> Path:
        for src, dst in self.files:
            if dst.suffix.lower() == ".dll":
                return dst
        return self.target_root


def _layout_files(layout: str, target_root: Path) -> list[tuple[Path, Path]]:
    source_layout = LAYOUT_NEW if layout == LAYOUT_NEW else LAYOUT_LEGACY
    dll, data = _bundled_parts(source_layout)
    if layout == LAYOUT_NEW:
        plugin_dir = target_root / PLUGIN_NAME
        dll_dst = plugin_dir / dll.name
        data_dst = plugin_dir / "data"
    elif layout == LAYOUT_LEGACY:
        plugin_dir = target_root / PLUGIN_NAME
        dll_dst = plugin_dir / "bin" / "64bit" / dll.name
        data_dst = plugin_dir / "data"
    else:  # intree
        dll_dst = target_root / "obs-plugins" / "64bit" / dll.name
        data_dst = target_root / "data" / "obs-plugins" / PLUGIN_NAME
    files = [(dll, dll_dst)]
    for path in sorted(data.rglob("*")):
        if path.is_file():
            files.append((path, data_dst / path.relative_to(data)))
    return files


def plan_install(local: LocalObs, obs_version: tuple[int, int, int] | None = None) -> InstallPlan:
    """Decide layout y destino. `obs_version` (del WebSocket) tiene prioridad
    sobre la version leida del .exe. Sin version conocida se usa el layout
    legacy: OBS 33 todavia lo carga (hasta 34)."""
    version = obs_version or local.version
    major = version[0] if version else None
    use_new = major is not None and major >= NEW_LAYOUT_MIN_MAJOR
    if local.portable:
        if use_new:
            layout, target = LAYOUT_NEW, local.root / "plugins"
            desc = f"OBS portable {major}: carpeta plugins\\ de la raíz portable"
        else:
            layout, target = LAYOUT_INTREE, local.root
            desc = "OBS portable: árbol de la instalación (obs-plugins\\64bit + data\\obs-plugins)"
    else:
        target = programdata_plugins_dir()
        if use_new:
            layout, desc = LAYOUT_NEW, f"OBS {major} instalado: C:\\ProgramData\\obs-studio\\plugins (estructura nueva)"
        else:
            layout, desc = LAYOUT_LEGACY, "OBS instalado: C:\\ProgramData\\obs-studio\\plugins (estructura clásica)"
    return InstallPlan(layout=layout, target_root=target,
                       files=_layout_files(layout, target), description=desc)


def install(plan: InstallPlan) -> tuple[bool, str]:
    """Copia los archivos del plan. (ok, msg)."""
    if not is_bundled():
        return False, (f"El plugin no viene embebido en esta copia de la app "
                       f"(falta {bundled_root()}). Si corres desde código fuente, "
                       f"ejecuta scripts\\bundle_source_record.py.")
    copied = 0
    try:
        for src, dst in plan.files:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    except PermissionError as exc:
        if obs_launcher.is_obs_running():
            return False, (f"No se pudo escribir {exc.filename or ''}: OBS está abierto y "
                           "tiene cargada la versión anterior del plugin. Cierra OBS, "
                           "vuelve a pulsar Instalar y luego abre OBS de nuevo.")
        return False, (f"Sin permisos para escribir en {plan.target_root}. "
                       "Prueba a ejecutar la app como administrador o instala el plugin "
                       "manualmente desde el paquete exportado.")
    except OSError as exc:
        return False, f"Error copiando el plugin: {exc}"
    log.info("Source Record %s instalado (%s): %d archivos en %s",
             PLUGIN_VERSION, plan.layout, copied, plan.target_root)
    return True, (f"Source Record {PLUGIN_VERSION} instalado ({copied} archivos) en:\n"
                  f"{plan.dll_target.parent}")


# ---------------------------------------------------------------------------
# Paquete para OBS remoto
# ---------------------------------------------------------------------------

def _readme_text(layout: str, major: int | None) -> str:
    ver = f"OBS Studio {major}" if major else "OBS Studio"
    if layout == LAYOUT_NEW:
        where = ("1. OBS instalado: descomprime este zip dentro de C:\\ProgramData\\obs-studio\\\n"
                 "   (queda C:\\ProgramData\\obs-studio\\plugins\\source-record\\source-record.dll).\n"
                 "2. OBS portable: descomprime dentro de la carpeta raíz del OBS portable\n"
                 "   (queda <raíz>\\plugins\\source-record\\source-record.dll).\n")
    else:
        where = ("1. OBS instalado: descomprime este zip dentro de C:\\ProgramData\\obs-studio\\\n"
                 "   (queda C:\\ProgramData\\obs-studio\\plugins\\source-record\\bin\\64bit\\source-record.dll).\n"
                 "2. OBS portable (32 o anterior): copia plugins\\source-record\\bin\\64bit\\source-record.dll a\n"
                 "   <raíz>\\obs-plugins\\64bit\\ y el contenido de plugins\\source-record\\data\\ a\n"
                 "   <raíz>\\data\\obs-plugins\\source-record\\.\n")
    return (
        f"Plugin Source Record {PLUGIN_VERSION} (Exeldro, GPL-2.0) para {ver}\n"
        "Generado por OBS Automation Manager.\n\n"
        "DÓNDE DESCOMPRIMIR (en el equipo donde corre OBS):\n" + where +
        "\n3. Cierra y vuelve a abrir OBS Studio.\n"
        "4. Verifica: clic derecho en una escena → Filtros → Añadir filtro → debe aparecer \"Source Record\".\n"
        "5. Vuelve a OBS Automation Manager → Ajustes → Plugin Source Record → Verificar.\n\n"
        "Licencia: GPL-2.0 (archivo LICENSE incluido). Código fuente: https://github.com/exeldro/obs-source-record\n"
    )


def export_package(dest_dir: Path, obs_major: int | None) -> Path:
    """Crea `source-record-<ver>-OBS<major>.zip` en `dest_dir` con la
    estructura lista para descomprimir en el servidor + LEEME.txt + LICENSE."""
    if not is_bundled():
        raise FileNotFoundError(f"Plugin no embebido en {bundled_root()}")
    layout = LAYOUT_NEW if (obs_major or 0) >= NEW_LAYOUT_MIN_MAJOR else LAYOUT_LEGACY
    dll, data = _bundled_parts(layout)
    tag = f"OBS{obs_major}" if obs_major else "OBS"
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"source-record-{PLUGIN_VERSION}-{tag}.zip"
    base = f"plugins/{PLUGIN_NAME}/"
    dll_arc = base + (dll.name if layout == LAYOUT_NEW else f"bin/64bit/{dll.name}")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(dll, dll_arc)
        for path in sorted(data.rglob("*")):
            if path.is_file():
                z.write(path, base + "data/" + path.relative_to(data).as_posix())
        license_file = bundled_root() / "LICENSE"
        if license_file.is_file():
            z.write(license_file, "LICENSE")
        z.writestr("LEEME.txt", _readme_text(layout, obs_major))
    log.info("Paquete Source Record exportado: %s", out)
    return out
