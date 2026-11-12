"""Tests de la recarga en caliente de obs_scripts/autopilot_v2.lua (nivel B).

Ejecuta el Lua REAL con LuaJIT (lupa; el mismo Lua 5.1 que usa OBS) y un
`obslua` falso minimo: timers, text sources en memoria y log. Sin OBS ni Qt.

Escenarios:
  1. El archivo en disco cambia de version -> el script se descarga, ejecuta
     el archivo nuevo y arranca su script_load (timers y callbacks nuevos).
  2. El archivo nuevo no compila -> sigue la version en ejecucion y no se
     reintenta hasta pasado el cooldown.
  3. El archivo nuevo compila pero falla al ejecutarse -> se restauran los
     callbacks y timers de la version en ejecucion.

Uso: venv\\Scripts\\python.exe scripts\\test_autopilot_hot_reload.py
Requiere `pip install -r requirements-dev.txt` (lupa).
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.autopilot_paths import autopilot_v2_lua_path  # noqa: E402

try:
    try:
        from lupa.luajit21 import LuaRuntime
    except ImportError:  # pragma: no cover - fallback a Lua 5.1 sin JIT
        from lupa.lua51 import LuaRuntime
except ImportError:  # pragma: no cover
    LuaRuntime = None

FAKE_OBSLUA = r"""
local calls = { log = {}, timers = {}, sources = {} }
local obs = setmetatable({ LOG_INFO = 300, LOG_WARNING = 200 },
    { __index = function(_, k) return function() return nil end end })
function obs.script_log(_, msg) calls.log[#calls.log + 1] = msg end
function obs.timer_add(fn, ms) calls.timers[fn] = ms end
function obs.timer_remove(fn) calls.timers[fn] = nil end
function obs.obs_get_source_by_name(name) return calls.sources[name] end
function obs.obs_source_create(_, name, settings)
    local s = { name = name, settings = {} }
    for k, v in pairs(settings or {}) do s.settings[k] = v end
    calls.sources[name] = s
    return s
end
function obs.obs_data_create() return {} end
function obs.obs_data_set_string(d, k, v) d[k] = v end
function obs.obs_data_get_string(d, k) return d[k] or "" end
function obs.obs_source_get_settings(s)
    local c = {}
    for k, v in pairs(s.settings) do c[k] = v end
    return c
end
function obs.obs_source_update(s, d) for k, v in pairs(d) do s.settings[k] = v end end
_G.obslua = obs
_G.__calls = calls
"""

_VERSION_RE = re.compile(r'(local\s+SCRIPT_VERSION\s*=\s*")([^"]+)(")')
TICK_CONFIG_MS = 500
RELOAD_CHECK_SEC = 10
TICKS_PER_CHECK = RELOAD_CHECK_SEC * 1000 // TICK_CONFIG_MS


def real_script_with_version(version: str) -> str:
    text = autopilot_v2_lua_path().read_text(encoding="utf-8")
    assert _VERSION_RE.search(text)
    return _VERSION_RE.sub(lambda m: m.group(1) + version + m.group(3), text, count=1)


@unittest.skipIf(LuaRuntime is None, "lupa no instalado (pip install -r requirements-dev.txt)")
class HotReloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aplua_"))
        self.script = self.tmp / "autopilot_v2.lua"
        self.L = LuaRuntime(unpack_returned_tuples=True)
        self.L.execute(FAKE_OBSLUA)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers --------------------------------------------------------
    def write(self, text: str):
        self.script.write_text(text, encoding="utf-8", newline="\n")

    def load_script(self):
        self.L.execute(f'dofile("{self.script.as_posix()}")')
        self.L.eval("script_load")(None)

    def logs(self) -> list[str]:
        return [str(m) for m in self.L.eval("__calls.log").values()]

    def timer_ids(self) -> list[str]:
        return list(self.L.eval(
            "(function() local t = {} for fn in pairs(__calls.timers) do t[#t+1] = tostring(fn) end "
            "table.sort(t) return t end)()").values())

    def config_tick(self):
        """La funcion registrada con el intervalo de 500 ms (tick_config)."""
        for fn, ms in self.L.eval("__calls.timers").items():
            if int(ms) == TICK_CONFIG_MS:
                return fn
        self.fail("no hay timer de 500 ms registrado")

    def run_checks(self, n_checks: int = 1):
        tick = self.config_tick()
        for _ in range(TICKS_PER_CHECK * n_checks):
            tick()

    def unload_id(self) -> str:
        return str(self.L.eval("tostring(script_unload)"))

    # -- tests ----------------------------------------------------------
    def test_reloads_when_file_version_changes(self):
        self.write(real_script_with_version("2.1.9"))
        self.load_script()
        self.assertTrue(any("cargando v2.1.9 desde " + self.script.as_posix() in m for m in self.logs()),
                        "el script debe resolver su propia ruta: %s" % self.logs())
        old_timers, old_unload = self.timer_ids(), self.unload_id()
        self.assertEqual(len(old_timers), 2)

        # Sin cambios en disco: nada pasa.
        self.run_checks()
        self.assertEqual(self.timer_ids(), old_timers)

        # La app sobrescribe el archivo con la version embebida real.
        real = autopilot_v2_lua_path().read_text(encoding="utf-8")
        real_version = _VERSION_RE.search(real).group(2)
        self.write(real)
        self.run_checks()

        logs = self.logs()
        self.assertTrue(any(f"recarga en caliente: v2.1.9 -> v{real_version}" in m for m in logs), logs)
        self.assertTrue(any("descargado" in m for m in logs))
        self.assertTrue(any(f"cargando v{real_version}" in m for m in logs))
        new_timers = self.timer_ids()
        self.assertEqual(len(new_timers), 2, "dos timers frescos")
        self.assertFalse(set(new_timers) & set(old_timers), "los timers viejos se quitaron")
        self.assertNotEqual(self.unload_id(), old_unload, "script_unload es el del archivo nuevo")
        # El buzon de estado sigue existiendo (adoptado, no recreado).
        n_sources = self.L.eval("(function() local n=0 for _ in pairs(__calls.sources) do n=n+1 end return n end)()")
        self.assertEqual(int(n_sources), 2)
        # La version nueva tambien vigila: sin cambios, se queda quieta.
        self.run_checks()
        self.assertEqual(self.timer_ids(), new_timers)

    def test_broken_file_keeps_running_version_with_cooldown(self):
        self.write(real_script_with_version("2.2.0"))
        self.load_script()
        timers, unload = self.timer_ids(), self.unload_id()

        self.write('local SCRIPT_VERSION = "9.9.9"\nthis is not lua\n')
        self.run_checks()
        logs = self.logs()
        self.assertEqual(sum("no compila" in m for m in logs), 1, logs)
        self.assertEqual(self.timer_ids(), timers)
        self.assertEqual(self.unload_id(), unload)

        # Dentro del cooldown no se reintenta (mismo archivo roto).
        self.run_checks(3)
        self.assertEqual(sum("no compila" in m for m in self.logs()), 1)

    def test_runtime_error_restores_running_version(self):
        self.write(real_script_with_version("2.2.0"))
        self.load_script()
        timers, unload = self.timer_ids(), self.unload_id()

        self.write('local SCRIPT_VERSION = "9.9.8"\nerror("boom en el archivo nuevo")\n')
        self.run_checks()
        logs = self.logs()
        self.assertTrue(any("fallo al ejecutar" in m and "restaurando v2.2.0" in m for m in logs), logs)
        # Se descargo y volvio a cargar la version en ejecucion.
        self.assertEqual(sum("cargando v2.2.0" in m for m in logs), 2)
        self.assertEqual(self.unload_id(), unload)
        self.assertEqual(self.timer_ids(), timers, "script_load viejo re-arma los mismos callbacks")

        # Un archivo que compila pero no define script_load tampoco pasa.
        self.write('local SCRIPT_VERSION = "9.9.7"\nscript_load = nil\n')
        self.L.execute("__calls.log = {}")  # version distinta: se intenta sin cooldown
        self.run_checks()
        logs = self.logs()
        self.assertTrue(any("restaurando v2.2.0" in m for m in logs), logs)
        self.assertEqual(self.unload_id(), unload)
        self.assertEqual(self.timer_ids(), timers)


if __name__ == "__main__":
    unittest.main()
