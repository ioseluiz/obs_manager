"""Smoke test del RealObsFacade (Fase 2c) — mock del OBSClient, sin OBS real.

Verifica:
- Cada método del facade llama al método correcto del cliente subyacente
  con argumentos esperados.
- Idempotencia: apply_calibration_filter remueve antes de crear.
- Errores 'already exists' / 600 en ensure_baseline_scene se ignoran.
- get_output_frame_stats extrae skipped/total del response.

Uso: venv\\Scripts\\python.exe scripts\\test_calibration_facade.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _check(cond: bool, msg: str) -> None:
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"  ok - {msg}")


class FakeReqClient:
    """Registra llamadas para verificación. Puede fallar según el escenario."""
    def __init__(self, fail_on=None):
        self.calls = []
        self._fail_on = fail_on or {}
    def _log(self, op, **kwargs):
        self.calls.append((op, kwargs))
        if op in self._fail_on:
            raise self._fail_on[op]

    def create_scene(self, name):
        self._log("create_scene", scene=name)
    def remove_scene(self, name):
        self._log("remove_scene", scene=name)
    def create_input(self, scene, input_name, kind, settings, enable):
        self._log("create_input", scene=scene, input_name=input_name,
                  kind=kind, settings=settings, enable=enable)
    def remove_input(self, input_name):
        self._log("remove_input", input_name=input_name)
    def get_scene_item_id(self, scene, input_name):
        self._log("get_scene_item_id", scene=scene, input_name=input_name)
        return SimpleNamespace(scene_item_id=1)
    def create_scene_item(self, scene, input_name, enabled):
        self._log("create_scene_item", scene=scene, input_name=input_name, enabled=enabled)
    def remove_source_filter(self, source, fname):
        self._log("remove_source_filter", source=source, fname=fname)
    def create_source_filter(self, source_name, filter_name, filter_kind, filter_settings):
        self._log("create_source_filter", source_name=source_name,
                  filter_name=filter_name, filter_kind=filter_kind,
                  filter_settings=filter_settings)
    def get_stats(self):
        self._log("get_stats")
        return SimpleNamespace(output_skipped_frames=42, output_total_frames=1000)


class FakeObsClient:
    """Wrapper que expone _raw_client() como el OBSClient real."""
    def __init__(self, req):
        self._req = req
    def _raw_client(self):
        return self._req


def main():
    from core.calibration_facade import RealObsFacade

    # === Test 1: ensure_baseline_scene con escena nueva ===
    print("\n[ensure_baseline_scene — camino feliz]")
    req = FakeReqClient()
    facade = RealObsFacade(FakeObsClient(req))
    facade.ensure_baseline_scene("Baseline", "ColorSrc")
    names = [c[0] for c in req.calls]
    _check("create_scene" in names, "llama create_scene")
    _check("create_input" in names, "llama create_input")
    input_call = next(c for c in req.calls if c[0] == "create_input")
    _check(input_call[1]["kind"] == "color_source_v3", "kind es color_source_v3")
    _check(input_call[1]["settings"]["width"] == 1920, "width=1920")
    _check(input_call[1]["settings"]["height"] == 1080, "height=1080")

    # === Test 2: ensure_baseline_scene idempotente (escena ya existe) ===
    print("\n[ensure_baseline_scene — 'already exists' no rompe]")
    req = FakeReqClient(fail_on={
        "create_scene": Exception("Scene already exists (code 601)"),
        "create_input": Exception("Input already exists"),
    })
    facade = RealObsFacade(FakeObsClient(req))
    facade.ensure_baseline_scene("Baseline", "ColorSrc")  # NO debe lanzar
    _check(True, "ensure_baseline_scene ignoró 'already exists'")

    # === Test 3: remove_baseline_scene llama remove_input y remove_scene ===
    print("\n[remove_baseline_scene]")
    req = FakeReqClient()
    facade = RealObsFacade(FakeObsClient(req))
    facade.remove_baseline_scene("Baseline", "ColorSrc")
    names = [c[0] for c in req.calls]
    _check("remove_input" in names, "remueve el input")
    _check("remove_scene" in names, "remueve la escena")

    # === Test 4: apply_calibration_filter idempotente ===
    print("\n[apply_calibration_filter — remove primero, luego create]")
    req = FakeReqClient()
    facade = RealObsFacade(FakeObsClient(req))
    facade.apply_calibration_filter(
        "Baseline", "udp_out_0", "x264", "udp://127.0.0.1:9700", 2500,
    )
    names = [c[0] for c in req.calls]
    _check(names[0] == "remove_source_filter", "primero remove (idempotencia)")
    _check(names[1] == "create_source_filter", "después create")
    create_call = req.calls[1][1]
    _check(create_call["filter_name"] == "udp_out_0", "filter_name propagado")
    _check(create_call["filter_kind"] == "source_record_filter", "filter_kind correcto")
    _check(create_call["filter_settings"]["encoder"] == "x264", "encoder propagado")
    _check(create_call["filter_settings"]["server"] == "udp://127.0.0.1:9700",
           "server URL propagado")
    _check(create_call["filter_settings"]["keyint_sec"] == 2,
           "keyint_sec del build_settings")
    _check(create_call["filter_settings"]["profile"] == "high", "profile heredado")

    # === Test 5: get_output_frame_stats extrae del response ===
    print("\n[get_output_frame_stats]")
    req = FakeReqClient()
    facade = RealObsFacade(FakeObsClient(req))
    skipped, total = facade.get_output_frame_stats()
    _check(skipped == 42, f"skipped=42 (dio {skipped})")
    _check(total == 1000, f"total=1000 (dio {total})")

    # === Test 6: remove_calibration_filter silencia error ===
    print("\n[remove_calibration_filter — silencia 'no filter']")
    req = FakeReqClient(fail_on={
        "remove_source_filter": Exception("no filter found (code 600)"),
    })
    facade = RealObsFacade(FakeObsClient(req))
    facade.remove_calibration_filter("Baseline", "no_existe")  # NO debe lanzar
    _check(True, "remove_calibration_filter silenció 600")

    print("\nTODOS LOS CHECKS PASARON")


if __name__ == "__main__":
    main()
