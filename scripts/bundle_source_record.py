"""Descarga y verifica el plugin Source Record (Exeldro, GPL-2.0) para
empaquetarlo con la app.

Se ejecuta en build (build.bat / release.yml) ANTES de PyInstaller. Deja
en `vendor/source-record/` los dos layouts que OBS reconoce, sin
modificar los binarios:

    vendor/source-record/
      legacy/source-record/bin/64bit/source-record.dll   (OBS <= 32; tambien
      legacy/source-record/data/{locale/*.ini, manifest.json}   sirve para el
                                                           arbol portable)
      new/source-record/source-record.dll                 (OBS >= 33)
      new/source-record/data/{locale/*.ini, manifest.json}
      LICENSE      (GPL-2.0, tal cual la publica el autor)
      SOURCE.txt   (procedencia: URLs, SHA-256, version)

Mismo patron que el antiguo bundle_ffplay.py: URLs y SHA-256 fijados,
cache en build/, fallo duro si el hash no coincide, allowlist de
miembros del zip y guardia contra zip-slip.
"""
from __future__ import annotations

import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.5.0"
_BASE = f"https://github.com/exeldro/obs-source-record/releases/download/{VERSION}/"

# (url, sha256, nombre en cache)
ZIP_LEGACY = (
    _BASE + f"source-record-{VERSION}-windows.zip",
    "de144eb052fea0b23edc22d65f89a6b4f11aef5aca585670719b1c2af9bf7769",
    f"source-record-{VERSION}-windows.zip",
)
ZIP_NEW = (
    _BASE + f"source-record-{VERSION}-windows-OBS33.zip",
    "76dace28442d8cbcd41635b2f9833ae26d16ee4886e49875728ae364f8436443",
    f"source-record-{VERSION}-windows-OBS33.zip",
)
LICENSE = (
    "https://raw.githubusercontent.com/exeldro/obs-source-record/master/LICENSE",
    "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643",
    "source-record-LICENSE",
)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "build"
TARGET = ROOT / "vendor" / "source-record"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(url: str, sha256: str, cache_name: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / cache_name
    if cached.exists() and _sha256(cached.read_bytes()) == sha256:
        return cached.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "obs-automation-manager-build"})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    if _sha256(data) != sha256:
        raise RuntimeError(f"SHA-256 mismatch for {url}")
    cached.write_bytes(data)
    return data


def _safe_relative(name: str) -> Path | None:
    rel = Path(name)
    if not rel.parts or rel.is_absolute() or ".." in rel.parts:
        return None
    return rel


def _extract(zip_bytes: bytes, prefix: str, dest: Path, keep) -> int:
    """Extrae los miembros bajo `prefix` que pasen `keep(rel)` en `dest/rel`."""
    count = 0
    with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            rel = _safe_relative(info.filename)
            if rel is None:
                continue
            posix = rel.as_posix()
            if not posix.startswith(prefix):
                continue
            inner = Path(posix[len(prefix):])
            if not inner.parts or not keep(inner):
                continue
            out = dest / inner
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(info))
            count += 1
    return count


def _keep_runtime(inner: Path) -> bool:
    # DLL de 64 bits + data (locale, manifest). Nada de .pdb ni 32bit.
    if inner.suffix.lower() == ".pdb":
        return False
    if "32bit" in inner.parts:
        return False
    return True


def main() -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)

    legacy_zip = _fetch(*ZIP_LEGACY)
    new_zip = _fetch(*ZIP_NEW)
    license_text = _fetch(*LICENSE)

    legacy_dir = TARGET / "legacy" / "source-record"
    # zip generico: obs-plugins/64bit/source-record.dll -> bin/64bit/...
    #               data/obs-plugins/source-record/**   -> data/**
    n = _extract(legacy_zip, "obs-plugins/64bit/", legacy_dir / "bin" / "64bit", _keep_runtime)
    n += _extract(legacy_zip, "data/obs-plugins/source-record/", legacy_dir / "data", _keep_runtime)
    if not (legacy_dir / "bin" / "64bit" / "source-record.dll").is_file():
        raise RuntimeError("legacy layout: source-record.dll missing")
    if not (legacy_dir / "data" / "locale" / "en-US.ini").is_file():
        raise RuntimeError("legacy layout: locale missing")

    new_dir = TARGET / "new" / "source-record"
    # zip OBS33: plugins/source-record/** -> ** (ya trae dll + data/)
    m = _extract(new_zip, "plugins/source-record/", new_dir, _keep_runtime)
    if not (new_dir / "source-record.dll").is_file():
        raise RuntimeError("new layout: source-record.dll missing")
    if not (new_dir / "data" / "manifest.json").is_file():
        raise RuntimeError("new layout: manifest.json missing")

    (TARGET / "LICENSE").write_bytes(license_text)
    (TARGET / "SOURCE.txt").write_text(
        "Source Record plugin for OBS Studio, version " + VERSION + ", by Exeldro.\n"
        "Unmodified binaries redistributed under the GNU GPL-2.0 (see LICENSE).\n"
        "Source code: https://github.com/exeldro/obs-source-record\n"
        "Resource page: https://obsproject.com/forum/resources/source-record.1285/\n"
        "\n"
        "legacy/ (OBS <= 32, also used for portable in-tree install) from:\n"
        f"  {ZIP_LEGACY[0]}\n  SHA-256 {ZIP_LEGACY[1]}\n"
        "new/ (OBS >= 33 plugin folder structure) from:\n"
        f"  {ZIP_NEW[0]}\n  SHA-256 {ZIP_NEW[1]}\n"
        "LICENSE from:\n"
        f"  {LICENSE[0]}\n  SHA-256 {LICENSE[1]}\n"
        "\n"
        "Only the 64-bit DLL and the data folder (locale, manifest) are kept;\n"
        ".pdb symbol files and 32-bit builds are omitted.\n",
        encoding="utf-8",
    )
    dll_legacy = _sha256((legacy_dir / "bin" / "64bit" / "source-record.dll").read_bytes())
    dll_new = _sha256((new_dir / "source-record.dll").read_bytes())
    print(f"Source Record {VERSION} bundled: {n} legacy files, {m} new-layout files "
          f"(dll identical: {dll_legacy == dll_new})")


if __name__ == "__main__":
    main()
