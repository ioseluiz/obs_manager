"""Fase 0 — Portón de multi-salida.

Pregunta binaria:
    ¿Un filtro sobre una escena de OBS produce frames cuando esa escena NO
    es la escena de programa actual?

La respuesta gobierna la arquitectura de canales multi-salida:
- Portón ABIERTO → cada canal es una escena contenedora con filtro anclado,
  todos producen en paralelo sin importar cuál esté en programa.
- Portón CERRADO → sólo la escena que está en programa produce; canales
  multi-salida y rotador legacy quedan mutuamente excluyentes, y toda la
  arquitectura se replantea.

Diseño de la prueba
-------------------
1. Se crean dos escenas de color: Fase0_A (rojo) y Fase0_B (azul).
2. Se agrega el filtro bajo prueba a Fase0_B, configurado para grabar a un
   archivo local durante N segundos.
3. Se pone Fase0_A como programa (Fase0_B fuera de programa).
4. Se enciende el filtro por N segundos.
5. Se apaga el filtro y se mide: ¿el archivo tiene frames?
6. Control: se repite con Fase0_B EN programa (esperado: siempre pasa; si
   falla, el problema es la config del filtro, no el portón).
7. Veredicto:
     out-of-program PASS + in-program PASS → PORTÓN ABIERTO ✓
     out-of-program FAIL + in-program PASS → PORTÓN CERRADO ✗
     out-of-program FAIL + in-program FAIL → setup inválido, revisar config

Prerrequisitos
--------------
- OBS Studio abierto con WebSocket habilitado.
- ``.env`` del proyecto con OBS_HOST/PORT/PASSWORD válidos (se carga desde
  %LOCALAPPDATA%\\OBS_Automation_Manager\\.env; también acepta --host/--port/
  --password como override).
- Plugin bajo prueba INSTALADO en OBS antes de correr (Source Record y/o
  Branch Output). Si el ``--filter-kind`` no existe en OBS, el script imprime
  los kinds disponibles y sale.
- Correr en el mismo equipo que OBS (o con la ruta de salida en un share).

Uso
---
Source Record con defaults sensatos::

    python scripts/fase0_probe.py --filter-kind source_record_filter

Con override de settings (necesario para Branch Output u otro plugin)::

    python scripts/fase0_probe.py --filter-kind branch_output_filter \\
        --settings-json '{"path": "C:/temp/fase0", ...}'

Listar filtros disponibles y salir::

    python scripts/fase0_probe.py --list-kinds

Salida
------
Tabla con resultado por escenario y veredicto final.
Exit code: 0 (abierto), 1 (cerrado), 2 (setup inválido), 3 (inconsistente).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import obsws_python as obs
except ImportError:
    sys.exit("Falta obsws-python. Ejecute: pip install obsws-python")

LOG = logging.getLogger("fase0")

SCENE_A = "Fase0_A"
SCENE_B = "Fase0_B"
FILTER_NAME = "fase0_filter"

# Defaults para Source Record (Exeldro, v0.4.8+).
# Verificado en OBS 30+ portable con Iris Xe.
# Claves críticas:
#   record_mode: 1   — modo "record only". Con 0 el plugin es un no-op silencioso.
#   encoder: "x264"  — software, universal (Iris Xe no tiene NVENC).
#   rate_control / scale_type — copiados de los filtros preexistentes del user.
DEFAULT_SR_SETTINGS = {
    "record_mode": 1,
    "path": "",  # se completa con --output-dir en runtime
    "filename_formatting": "fase0",  # placeholder — se completa por escenario
    "rec_format": "hybrid_mp4",
    "encoder": "x264",
    "bitrate": 2500,
    "rate_control": "CBR",
    "scale_type": 3,
}


# ---------------------------------------------------------------------------
# .env loader (misma ubicación que usa la app)
# ---------------------------------------------------------------------------

def _load_env_from_appdata():
    localappdata = os.getenv("LOCALAPPDATA")
    if not localappdata:
        return None
    env_path = Path(localappdata) / "OBS_Automation_Manager" / ".env"
    if not env_path.exists():
        return None
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None
    load_dotenv(env_path)
    return env_path


# ---------------------------------------------------------------------------
# Setup / cleanup
# ---------------------------------------------------------------------------

def _list_filter_kinds(client):
    resp = client.get_source_filter_kind_list()
    kinds = getattr(resp, "source_filter_kinds", None)
    if kinds is None:
        # Nombre alterno según versión del cliente
        kinds = getattr(resp, "sourceFilterKinds", [])
    return list(kinds)


def _pick_color_source_kind(client):
    """Devuelve el mejor color_source disponible. Prioriza v3 > v2 > color_source."""
    try:
        resp = client.get_input_kind_list(False)
        kinds = getattr(resp, "input_kinds", None) or getattr(resp, "inputKinds", [])
    except Exception as e:
        raise RuntimeError(f"No se pudo listar input kinds: {e}") from e
    for candidate in ("color_source_v3", "color_source_v2", "color_source"):
        if candidate in kinds:
            return candidate
    raise RuntimeError(
        f"OBS no reporta ningún color_source*. Kinds disponibles: {sorted(kinds)}"
    )


def _create_color_scene(client, name, color_bgra, input_kind):
    try:
        client.create_scene(name)
    except Exception as e:
        LOG.debug("create_scene(%s) ignorado (probablemente ya existía): %s", name, e)
    input_name = f"{name}_color"
    try:
        client.create_input(
            name,             # sceneName
            input_name,       # inputName
            input_kind,
            {"color": color_bgra, "width": 1920, "height": 1080},
            True,             # sceneItemEnabled
        )
    except Exception as e:
        # Si el input ya existe con ese nombre, no es fatal — reusamos.
        msg = str(e).lower()
        if "already exists" in msg or "already_exists" in msg or "600" in msg:
            LOG.debug("Input %s ya existía; se reusa.", input_name)
            return
        raise RuntimeError(
            f"No se pudo crear color source '{input_name}' con kind '{input_kind}': {e}"
        ) from e


def _cleanup(client):
    # Los 600 "no source found" son esperados si el script sale temprano
    # (p. ej. --list-kinds). Silenciar el logger de obsws_python.reqs
    # durante el cleanup para no ensuciar el output.
    obsws_log = logging.getLogger("obsws_python.reqs")
    prev_level = obsws_log.level
    obsws_log.setLevel(logging.CRITICAL)
    try:
        for filter_source in (SCENE_B,):
            try:
                client.remove_source_filter(filter_source, FILTER_NAME)
            except Exception:
                pass
        for name in (SCENE_B, SCENE_A):
            try:
                client.remove_input(f"{name}_color")
            except Exception:
                pass
            try:
                client.remove_scene(name)
            except Exception:
                pass
    finally:
        obsws_log.setLevel(prev_level)


# ---------------------------------------------------------------------------
# Escenario
# ---------------------------------------------------------------------------

def _run_scenario(client, args, scene_b_is_program, output_dir, tag):
    LOG.info("=" * 60)
    LOG.info("Escenario '%s' — Fase0_B %s programa",
             tag, "EN" if scene_b_is_program else "FUERA DE")

    # 1. Fijar la escena de programa
    program = SCENE_B if scene_b_is_program else SCENE_A
    client.set_current_program_scene(program)
    time.sleep(1.0)

    # 2. Configurar filtro
    settings = dict(args.settings)
    settings["path"] = str(output_dir)
    filename_stamp = f"{tag}_{int(time.time())}"
    settings["filename_formatting"] = filename_stamp

    # Snapshot previo del dir para saber qué archivos son nuevos
    before = {p.name for p in output_dir.iterdir()} if output_dir.exists() else set()

    # Silenciar logger de obsws_python durante removes preventivos: el 600
    # "filter no existe" es esperado en la primera pasada, no es error real.
    obsws_log = logging.getLogger("obsws_python.reqs")
    prev_level = obsws_log.level
    obsws_log.setLevel(logging.CRITICAL)
    try:
        try:
            client.remove_source_filter(SCENE_B, FILTER_NAME)
        except Exception:
            pass
    finally:
        obsws_log.setLevel(prev_level)
    client.create_source_filter(
        source_name=SCENE_B,
        filter_name=FILTER_NAME,
        filter_kind=args.filter_kind,
        filter_settings=settings,
    )

    # 3. Encender filtro (dispara la grabación)
    client.set_source_filter_enabled(SCENE_B, FILTER_NAME, True)
    LOG.info("Filtro activo. Grabando %ds...", args.duration)
    time.sleep(args.duration)

    # 4. Apagar y limpiar
    client.set_source_filter_enabled(SCENE_B, FILTER_NAME, False)
    time.sleep(2.0)  # dejar que el plugin cierre el archivo
    try:
        client.remove_source_filter(SCENE_B, FILTER_NAME)
    except Exception:
        pass

    # 5. Detectar archivo nuevo generado por el filtro
    if not output_dir.exists():
        return {"scenario": tag, "produced": False, "bytes": 0, "path": None}
    after = list(output_dir.iterdir())
    new_files = [p for p in after if p.is_file() and p.name not in before]
    if not new_files:
        LOG.warning("El filtro no generó archivos nuevos.")
        return {"scenario": tag, "produced": False, "bytes": 0, "path": None}
    # Tomar el más grande (por si hay archivos temporales adyacentes)
    new_files.sort(key=lambda p: p.stat().st_size, reverse=True)
    winner = new_files[0]
    size = winner.stat().st_size
    LOG.info("Archivo generado: %s (%.1f KB)", winner.name, size / 1024)

    return {
        "scenario": tag,
        "produced": size > 50_000,  # >50 KB indica frames reales, no sólo header
        "bytes": size,
        "path": str(winner),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _load_env_from_appdata()

    parser = argparse.ArgumentParser(description="Fase 0 — portón de multi-salida")
    parser.add_argument("--filter-kind", default="source_record_filter",
                        help="Kind del filtro a probar (default: source_record_filter).")
    parser.add_argument("--settings-json",
                        help="Settings del filtro como JSON. Si se omite, "
                             "se usan defaults SÓLO para source_record_filter.")
    parser.add_argument("--output-dir",
                        default=str(Path(tempfile.gettempdir()) / "fase0"),
                        help="Carpeta donde el filtro escribe. Default: %(default)s")
    parser.add_argument("--duration", type=int, default=15,
                        help="Segundos de grabación por escenario (default: 15).")
    parser.add_argument("--host", default=os.getenv("OBS_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OBS_PORT", "4455")))
    parser.add_argument("--password", default=os.getenv("OBS_PASSWORD", ""))
    parser.add_argument("--list-kinds", action="store_true",
                        help="Listar filter kinds disponibles y salir.")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    LOG.info("Conectando a OBS %s:%s ...", args.host, args.port)
    try:
        client = obs.ReqClient(
            host=args.host, port=args.port, password=args.password, timeout=5,
        )
    except Exception as e:
        sys.exit(f"No se pudo conectar a OBS: {e}")

    try:
        kinds = _list_filter_kinds(client)
        if args.list_kinds:
            print("Filter kinds disponibles en OBS:")
            for k in sorted(kinds):
                print(f"  {k}")
            return

        if args.filter_kind not in kinds:
            sys.exit(
                f"El filter kind '{args.filter_kind}' no está disponible.\n"
                f"Kinds disponibles: {sorted(kinds)}\n"
                "¿Está instalado el plugin y OBS fue reiniciado?"
            )

        if args.settings_json:
            args.settings = json.loads(args.settings_json)
        elif args.filter_kind == "source_record_filter":
            args.settings = dict(DEFAULT_SR_SETTINGS)
        else:
            sys.exit(
                f"No hay settings default para '{args.filter_kind}'. "
                "Pase --settings-json."
            )

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        LOG.info("Output dir: %s", output_dir)

        color_kind = _pick_color_source_kind(client)
        LOG.info("Usando input kind '%s' para las escenas de color.", color_kind)
        _create_color_scene(client, SCENE_A, 0xFF0000FF, color_kind)  # rojo (BGRA)
        _create_color_scene(client, SCENE_B, 0xFFFF0000, color_kind)  # azul (BGRA)
        time.sleep(1.0)

        results = [
            _run_scenario(client, args, scene_b_is_program=False,
                          output_dir=output_dir, tag="fuera_de_programa"),
            _run_scenario(client, args, scene_b_is_program=True,
                          output_dir=output_dir, tag="en_programa"),
        ]
    finally:
        _cleanup(client)
        client.disconnect()

    # -----------------------------------------------------------------------
    # Reporte
    # -----------------------------------------------------------------------
    print()
    print("=" * 70)
    print("RESULTADOS")
    print("=" * 70)
    print(f"{'Escenario':<25} {'Produjo?':<10} {'Bytes':<15} Archivo")
    for r in results:
        print(f"{r['scenario']:<25} {str(r['produced']):<10} "
              f"{r['bytes']:<15,d} {r['path'] or '—'}")

    outp = next(r for r in results if r["scenario"] == "fuera_de_programa")
    inp = next(r for r in results if r["scenario"] == "en_programa")

    print()
    if outp["produced"] and inp["produced"]:
        print("VEREDICTO: PORTÓN ABIERTO.")
        print("  El filtro produce frames aunque la escena esté fuera de programa.")
        print("  Multi-salida vía filtros anclados es viable.")
        sys.exit(0)
    if not outp["produced"] and inp["produced"]:
        print("VEREDICTO: PORTÓN CERRADO.")
        print("  El filtro sólo produce cuando la escena está en programa.")
        print("  Multi-salida y rotador legacy quedan mutuamente excluyentes.")
        print("  Reconsultar al usuario antes de continuar la arquitectura.")
        sys.exit(1)
    if not outp["produced"] and not inp["produced"]:
        print("VEREDICTO: SETUP INVÁLIDO.")
        print("  El filtro no produjo frames en ningún escenario.")
        print("  Revisar filter-kind, settings, y permisos de escritura en output-dir.")
        print("  Reintentar con --verbose y --settings-json a medida.")
        sys.exit(2)
    print("VEREDICTO: Inconsistente (in-program falló pero out-of-program pasó).")
    print("  Reejecutar con --verbose y revisar logs.")
    sys.exit(3)


if __name__ == "__main__":
    main()
