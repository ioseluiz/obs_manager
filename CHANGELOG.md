# CHANGELOG

Formato basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Las versiones estables (`v1.8.x`) viven en la rama de release
`release/v1.8.x-autopilot`; las beta de la línea v2 (canales
multi-salida) se publican como prereleases desde `main`.

## [Unreleased] — en preparación v2.0.0-beta.N+1

### Agregado — Autopilot v2 (port multi-canal)

Port completo del **Autopilot v1.8** (script Lua residente dentro de
OBS que mantiene la rotación de escenas activa cuando la app cliente se
cierra) a la arquitectura multi-canal de la v2:

- **Protocolo v2** (`obs_scripts/PROTOCOL_v2.md`): payload JSON con
  array `canales[]`, dos modos de rotación por canal (`program_global`
  para Canal Principal legacy, `scene_items` para canales multi-salida
  con filtro Source Record), nuevos buzones (`__autopilot_config_v2__`
  / `__autopilot_state_v2__`) que **conviven** con los v1 sin
  interferencia.
- **`core/autopilot_client.py`**: nueva clase `AutopilotClientV2` con
  validación de shape por canal, filtrado de handoff vacío (replica el
  fix del bug C del v1 — handoff con `seconds_remaining<=0` corrompía
  el cursor del script), y helper `read_canal_state(canal_id)`.
- **`obs_scripts/autopilot_v2.lua`**: script residente que gestiona
  `rotator_states` keyed por `canal_id`, mantiene habilitados los
  filtros Source Record en cada tick (defensa contra apagados
  accidentales), y traslada desde el día uno los tres fixes críticos
  del Lua v1 (timers zombi tras hot-reload, heartbeat
  auto-refrescante, handoff vacío).
- **`controllers/autopilot_v2_controller.py`**: `AutopilotV2Controller`
  Qt con heartbeat 5 s + debouncer 300 ms que coalesce ráfagas de
  `canal_status_changed`; publica un último payload con handoffs al
  shutdown (`stop(publish_handoff=True)`).
- **Sincronización bidireccional al reconectar**: nuevos métodos
  `sync_from_handoff` en `CanalController` y `SceneController`, más
  `MainController._sync_from_autopilot_v2()` que lee el state publicado
  por el Lua y restaura `_RotatorState.active_index + remaining_ms` y
  `scene_controller.active_scene_name + time_left` sin salto visible en
  la UI.
- **Status bar + wizard**:
  - Label permanente en `MainWindow` con refresco cada 3 s:
    `🎛 Autopilot v<N> listo · N canales` (standby) /
    `🚀 Autopilot v<N> activo · K/N rotando` (active).
  - Diálogo `AutopilotInstallV2Dialog` en Ajustes → sección Autopilot
    v2 con botones Exportar a Descargas / Exportar como… / Verificar
    instalación. Detecta y reporta la presencia de un Autopilot v1 ya
    instalado (los dos coexisten sin tocarse).
- **PyInstaller**: `OBS_Automation_Manager.spec` ahora incluye el
  directorio `obs_scripts/` en `datas` para que el `.lua` viaje dentro
  del `.exe`. `core/autopilot_paths.py` resuelve la ruta usando
  `sys._MEIPASS` cuando corre congelado (replica el fix v1.8.1).

### Agregado — fix calendar (viene también en `release/v1.8.x-autopilot`)

- **Bloqueo de controles del Calendario de Cumpleaños**: dos capas de
  defensa contra cambios accidentales por scroll de la rueda del mouse.
  Filtro global que descarta `QEvent.Wheel` cuando el widget no tiene
  foco + toggle explícito "🔒 Controles bloqueados / 🔓 Modo edición"
  que nace bloqueado. Reaplica el fix publicado como PR en
  `release/v1.8.x-autopilot` por el reporte de usuarios en v1.8.1.

### Tests

- 92 asserts headless nuevos distribuidos en:
  - `scripts/test_autopilot_client_v2.py` (44): serialización,
    monotonicidad de versión, filtrado de handoff vacío, validaciones.
  - `scripts/test_autopilot_v2_controller.py` (48):
    `collect_canales_payload` con y sin Canal Principal, debouncer,
    recuperación tras `AutopilotV2NotInstalled`, `sync_from_handoff` en
    ambos controllers.
- `scripts/test_autopilot_v2_single_canal.py`: prueba end-to-end
  manual con OBS real + Source Record + Lua v2 cargado. Valida fases
  standby → active → rotación activa + stream UDP contínuo. Validado
  en entorno real contra OBS portable + Iris Xe.

### Verificado contra OBS real

- 2 canales multi-salida rotando bajo control del Lua tras cierre de
  la app (observado durante prueba de Fase B/C en 2026-10-20).
- Hand-off reverso al reabrir la app: el `_RotatorState.active_index`
  queda sincronizado con el último que el Lua estaba mostrando.

### Convivencia con v1.8.x

- La rama de release `v1.8.x-autopilot` no se toca. El Autopilot v2
  coexiste con el v1 en un mismo servidor OBS: cada script usa su par
  de buzones; nombres de archivo distintos (`autopilot.lua` vs
  `autopilot_v2.lua`); nunca se pisan.
- Rollback: si v2 falla, cerrar la app v2 y abrir la v1.8.1 Latest; el
  script v1 toma control del Program global como siempre.

---

## [1.8.1] — 2026-09-18

Hotfix sobre v1.8.0 (rama `release/v1.8.x-autopilot`).

### Corregido

- **`core/autopilot_paths.bundle_root()`**: ahora usa `sys._MEIPASS`
  cuando corre bajo PyInstaller `>=6.0`. El wizard de instalación
  fallaba al exportar el script en la app empaquetada.

Probado en producción — funcionando.

## [1.8.0] — 2026-09-18

Primera versión de **Autopilot** sobre la línea `v1.7.1`. Script Lua
residente que mantiene la rotación de escenas en OBS cuando la app
cliente se cierra. Rama `release/v1.8.x-autopilot`, Latest para los
operadores en producción.

Ver detalles en [`obs_scripts/PROTOCOL.md`](obs_scripts/PROTOCOL.md).
