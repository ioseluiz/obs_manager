"""Introspecta los settings efectivos del filtro udp_out de un canal.

Uso::

    venv\\Scripts\\python.exe scripts\\inspect_canal_filter.py "edificio 721"

Se conecta a OBS con las credenciales de `.env` y lista TODOS los settings
que el plugin Source Record reporta para el filtro `udp_out` sobre la
escena `<nombre_canal>`. Diferencia entre defaults (no seteados) y valores
efectivos.

Contexto: cuando el filtro emite paquetes UDP pero VLC ve negro,
tipicamente falta `output_width` / `output_height` / `output_fps_*`
o el `encoder` está mal.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/inspect_canal_filter.py '<nombre canal>'")

    canal_nombre = sys.argv[1]

    # Cargar .env con dotenv (la app ya lo usa) para respetar el mismo
    # parsing que el runtime — quita comillas, escape sequences, etc.
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
    except ImportError:
        # Fallback manual — strippea comillas al valor si están.
        env_path = _PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or \
                   (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                os.environ.setdefault(k.strip(), v)

    host = os.environ.get("OBS_HOST", "localhost")
    port = int(os.environ.get("OBS_PORT", "4455"))
    password = os.environ.get("OBS_PASSWORD", "")
    # Diagnóstico útil para el error "failed to identify client"
    print(f"[.env] OBS_HOST={host}  OBS_PORT={port}  "
          f"password_len={len(password)}  password_first2={password[:2]!r}")
    if not password:
        print("  ⚠ OBS_PASSWORD vacío — el server con auth habilitado rechazará.")

    import obsws_python as obs
    client = obs.ReqClient(host=host, port=port, password=password, timeout=5)

    print(f"Conectado a OBS en {host}:{port}")
    print(f"Buscando filtro 'udp_out' en escena '{canal_nombre}'\n")

    # 1. ¿Existe la escena?
    try:
        scenes = client.get_scene_list().scenes
    except Exception as e:
        sys.exit(f"get_scene_list falló: {e}")
    scene_names = [s["sceneName"] for s in scenes]
    if canal_nombre not in scene_names:
        print(f"ESCENA '{canal_nombre}' NO EXISTE en OBS")
        print(f"Escenas disponibles: {scene_names}")
        sys.exit(1)
    print(f"OK — escena '{canal_nombre}' existe")

    # 2. ¿Existe el filtro?
    try:
        filters = client.get_source_filter_list(canal_nombre).filters
    except Exception as e:
        sys.exit(f"get_source_filter_list falló: {e}")
    print(f"Filtros en la escena: {[f.get('filterName') for f in filters]}")
    udp_filter = next((f for f in filters if f.get("filterName") == "udp_out"), None)
    if not udp_filter:
        print("FILTRO 'udp_out' NO EXISTE — el canal no está aplicado en OBS")
        sys.exit(2)
    print(f"OK — filtro 'udp_out' presente, enabled={udp_filter.get('filterEnabled')}\n")

    # 3. Settings efectivos + defaults
    print("=" * 70)
    print("SETTINGS EFECTIVOS (los que devuelve get_source_filter):")
    print("=" * 70)
    try:
        resp = client.get_source_filter(canal_nombre, "udp_out")
        settings = dict(resp.filter_settings)
    except Exception as e:
        sys.exit(f"get_source_filter falló: {e}")
    for k, v in sorted(settings.items()):
        print(f"  {k:<30} {v!r}")

    print()
    print("=" * 70)
    print("DEFAULTS DEL PLUGIN (get_source_filter_default_settings):")
    print("=" * 70)
    try:
        defaults_resp = client.get_source_filter_default_settings("source_record_filter")
        defaults = dict(defaults_resp.default_filter_settings)
        for k, v in sorted(defaults.items()):
            marker = "  " if k in settings else "* "
            print(f"  {marker}{k:<30} {v!r}")
        print("\n  (* = key con default; si NO está en settings efectivos, "
              "el filtro usa este default)")
    except Exception as e:
        print(f"  get_source_filter_default_settings falló: {e}")

    # 4. Chequeo: ¿faltan width/height?
    print()
    print("=" * 70)
    print("DIAGNÓSTICO:")
    print("=" * 70)
    keys_criticas = ["output_width", "output_height", "output_fps_num",
                     "output_fps_den", "encoder", "bitrate", "server",
                     "stream_mode", "rate_control"]
    for k in keys_criticas:
        if k in settings:
            print(f"  OK  {k} = {settings[k]!r} (efectivo)")
        else:
            default_val = defaults.get(k, "<no aparece>") if 'defaults' in dir() else "<?>"
            print(f"  ??  {k} NO seteado (default plugin: {default_val!r})")

    client.disconnect()


if __name__ == "__main__":
    main()
