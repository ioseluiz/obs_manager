# CHANGELOG

Formato basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Las versiones estables (`v1.8.x`) viven en la rama de release
`release/v1.8.x-autopilot`; las beta de la línea v2 (canales
multi-salida) se publican como prereleases desde `main`.

## [2.0.0] — 2026-10-21

Release final de la línea v2 (canales multi-salida). Acumula lo validado
en `v2.0.0-beta` más la unificación de canales, el rediseño UI con
branding Canal de Panamá y el soporte de parámetros multicast. Instalar
sobre v1.x o v2.0.0-beta preserva DB, logs y `.env`.

### Agregado — Parámetros multicast opcionales por canal (TTL / pkt_size)

- **Campos `TTL` y `pkt_size` en el diálogo de canal**
  (`views/canal_edit_dialog.py`): dos spinners opcionales debajo de la
  URL de destino. Se persisten como query params dentro del campo
  `url_destino` existente (`udp://230.x.x.x:8000?ttl=32&pkt_size=1316`)
  — zero cambios de schema. Al abrir un canal, la URL se descompone en
  base + params; al guardar se recompone. Un campo en `(sin setear)` no
  agrega el parámetro. Valores típicos: `ttl=32` para multicast entre
  subredes, `pkt_size=1316` para MPEG-TS (7 × 188 bytes).
- **`_OptionalSpinBox`**: subclase de `QSpinBox` donde dejar el campo
  vacío equivale a `(sin setear)` — el `QSpinBox` estándar revertía al
  último valor válido al borrar el texto.
- **`core/udp_url_params.py`** (nuevo, puro stdlib):
  `extract_multicast_params(url)` / `compose_url(base, ttl, pkt_size)`.
  Preserva query params ajenos (`fifo_size`, `localaddr`…), keys
  case-insensitive, round-trip idempotente. Tests: 21 asserts en
  `scripts/test_udp_url_params.py`.
- `core/output_adapter.py` no cambia: ya pasaba `url_destino` tal cual
  al filtro Source Record, cuyo FFmpeg interno honra los query params.

### Corregido

- `scripts/inspect_canal_filter.py` cargaba el `.env` de la raíz del
  proyecto (legacy) en vez del de `%LOCALAPPDATA%\OBS_Automation_Manager\`
  que usa la app — fallaba con "failed to identify client" aunque las
  credenciales fueran correctas. Ahora resuelve la ruta con
  `core.paths.get_app_data_dir()` y cae a la del proyecto solo como
  fallback, e imprime cuál usó.

### Agregado — Unificación de canales (eliminación del Canal Principal legacy)

Colapso del modelo dual (Canal Principal legacy + canales multi-salida)
a un solo paradigma: todos los canales son multi-salida con filtro
Source Record. Las secuencias (`Biblioteca de Escenas`) se mantienen
como pool reusable que varios canales pueden referenciar via
`canal_items`. 7 commits incrementales en `feature/unify-canales`:

- **Fase 1.F1/F2/F3 — Show-hooks por tipo en CanalController**
  (`controllers/canal_controller.py`): nueva infra `_RotatorState.item_to_seq`
  + `refresh_timer` + `active_input_name`. Al mostrar un item nuevo,
  despacha según el tipo de secuencia:
  - URL con `refresh_interval_seg > 0` → arma QTimer que llama
    `OBSClient.refresh_browser_source` cada N segundos sobre
    `{secuencia_nombre}_Web`.
  - File con `video_offset_seg > 0` → `set_media_cursor` tras mostrar.
  - Nombre coincide con `settings.cal_scene` →
    `calendar_controller.move_circle_to_today(show_messages=False)`.
  Nuevo arg opcional `calendar_controller` en el constructor.
  Tests: 9 asserts en `scripts/test_canal_show_hooks.py`.

- **Fix auto-apply** (`views/canal_detail_view.py`): nuevo helper
  `_auto_apply_after_playlist_change` llamado tras cada operación de
  playlist (agregar / quitar / reordenar / editar duración). Elimina
  la fricción de tener que pulsar "📡 Aplicar cambios en OBS"
  manualmente tras cada cambio. El botón sigue disponible como
  fallback explícito.

- **Fase 2 — Wizard de migración "Canal Legacy"**
  (`core/legacy_migrator.py`, `views/legacy_migration_dialog.py`):
  diálogo modal que al primer launch tras la unificación ofrece
  convertir las secuencias existentes en un canal nuevo con filtro
  `udp_out`. Tres salidas: Convertir / Omitir por ahora (re-ofrece la
  próxima vez) / No volver a preguntar (marca flag
  `LEGACY_MIGRATION_DONE`). Validaciones in-dialog (nombre, URL,
  selección no vacía). `models/settings_model.py` gana `get_flag` /
  `set_flag` para persistir banderas genéricas en el `.env`. Tests:
  16 asserts en `scripts/test_legacy_migrator.py`.

- **Fase 3a — AutopilotV2 ya no soporta Canal Principal legacy**
  (`controllers/autopilot_v2_controller.py`): eliminada
  `_collect_canal_principal_entry` y la constante
  `CANAL_ID_PRINCIPAL`. `collect_canales_payload` solo recorre
  canales multi-salida (modo `scene_items`). El Lua v2 sigue
  soportando ambos modos — tolera payloads sin canales
  `program_global`. En `MainController._sync_from_autopilot_v2` se
  ignoran `canal_id < 0` que pudieran venir del Lua viejo.

- **Fase 3b/4 — Canal Principal fuera de la UI**:
  - `controllers/main_controller.py`: eliminados `toggle_recording`,
    `_sync_recording_state`, `_update_recording_ui`,
    `_poll_recording_status`, `_is_recording`, `_record_timer`,
    `_rotator_was_running`. `ProduccionView` se construye con 3 args
    (sin `scene_controller` ni `on_transmit_principal_toggle`).
  - `views/produccion_view.py` reescrito: sin sentinel
    `_CANAL_PRINCIPAL_ID`, sin `CanalPrincipalDetailView`. El sidebar
    lista solo canales reales + placeholder "Selecciona un canal..."
    cuando no hay ninguno.
  - `views/canal_principal_detail_view.py`: **eliminado**.
  - `views/main_window.py`: sin `lbl_record_timer` ni
    `set_recording_ui` — ya no hay indicador 🔴 EN VIVO global.

- **Fix hero Calendario**: `calendar_view.py` ahora agrega el
  `QScrollArea` con stretch=1 — el hero header mantiene su
  `minimumHeight` de 96px igual que en las otras pestañas. Antes
  robaba altura y disparaba scrollbar innecesaria.

**Preservado explícitamente**:
- La `Biblioteca de Escenas` sigue siendo CRUD de secuencias — el
  SceneController mantiene su CRUD (`add_scene`, `edit_scene`,
  `delete_scene`), thumbnails (`refresh_all_previews`) y live tuning.
  Los métodos de rotación (`start_rotation`, `rotate_to_next_scene`,
  etc.) quedan como código muerto temporal — nadie los invoca ya; se
  podarán en una fase futura si el riesgo lo justifica.
- Autopilot v2 Lua intacto — soporta ambos modos aunque el cliente
  Python ya no publique canales `program_global`. Operadores con el
  script v2 instalado no necesitan recargar.
- Secuencias no se tocan — son pool reusable referenciado por
  `canal_items` via FK.

**Verificación**: 12 tests headless siguen verdes, incluyendo nuevos
`test_canal_show_hooks` (9 asserts) y `test_legacy_migrator`
(16 asserts). Validación manual contra OBS real: wizard de migración
ejecutado por el operador — conversión exitosa a canal regular, URL
nuevo agregado se incluye en la rotación tras auto-apply.

### Agregado — Rediseño UI (branding Canal de Panamá)

Rediseño visual completo basado en 4 mockups entregados por el equipo
de diseño (`assets/screens/*.png`). 11 commits incrementales en
`feature/ui-redesign` desde `feature/aut-v2-multi-canal`:

- **Fase 0 — Design tokens** (`views/theme/`): paleta, espaciados,
  radios y tipografía centralizados. QSS global con property roles
  (`role="primary|success|danger|warning|muted"` para botones;
  `role="hero-title|kpi-number|status-ok|status-warn|status-danger|
  status-muted|..."` para labels). `views/styles.py` queda como shim
  de compat.
- **Fase 1 — Helper de iconos** (`views/theme/icons.py`): carga PNGs
  corporativos de `assets/icono_*.png` con tinting opcional via
  QPainter CompositionMode. Reemplaza 36 emojis Unicode (▶ ⏮ ⏸ ⚙ 📤
  📥 ➕ ✏ 🗑 🔌 🔄 ...) por iconos corporativos en main_window,
  canal_principal_detail_view, canal_detail_view, scene_view. Fix
  posterior para tintar en blanco sobre botones de color.
- **Fase 2 — Shell nuevo** (`views/widgets/sidebar.py`,
  `views/widgets/app_header.py`, `views/main_window.py` reescrito):
  sidebar vertical oscuro (azul marino + logo CP al pie, item activo
  marcado con barra roja) + header blanco con logo app, acciones y
  branding CP + QStackedWidget. El antiguo QTabWidget + QToolBar
  horizontales se eliminan. Shim `_StackTabsCompat` preserva
  `main_window.tabs.addTab(view, name)` para que el MainController
  siga llamándolo sin cambios.
- **Fase 3 — Pestaña Inicio** (`views/home_view.py`,
  `controllers/home_controller.py` + widgets KpiCard, ActionButton,
  ChannelPreviewCard): nueva primera sección del sidebar con hero,
  4 KPI cards, 4 acciones rápidas, card de estado OBS, grid de vista
  previa de canales. Datos reales desde CanalModel, SceneModel,
  OBSClient con refresco cada 5 s.
- **Fase 4 — Hero sections** (`views/widgets/hero_header.py`
  reusable): aplicado como primer widget de las 5 vistas internas
  (Calendario, Biblioteca, Contadores, Producción, Logs) con variante
  cromática por vista.
- **Fase 5 — Refinamiento por vista**: 5 subcommits migrando
  `setStyleSheet` inline a `setProperty("role", ...)`. ~30 inline
  reemplazados en scene_view, countdown_view, canal_detail,
  canal_principal_detail, calendar_view, logs_view.
- **Fase 6 — Diálogos**: pass de theming en SettingsDialog +
  scene_edit, canal_edit, calendar_simulation, autopilot_install_v2,
  import, capacity_validation, calibration.
- **Fase 7 — QA + limpieza**: 11 tests headless siguen verdes
  (test_autopilot_client_v2, test_autopilot_v2_controller,
  test_canal_model, test_canal_rotator_controls, test_canal_schedule,
  test_output_adapter, test_calibration_engine/facade,
  test_capacity_repo/validator, test_encoding_lag_watchdog).
  Removidos 5 archivos duplicados por OneDrive conflict copy
  (`*-O-387404-NINCZL.py`), agregados a `.gitignore`.

Herramienta auxiliar: `scripts/logo_a_blanco_transparente.py`
convierte un JPG/PNG a color con fondo blanco → silueta blanca sobre
fondo transparente usando luminosidad perceptual como alpha. Se usó
para generar `assets/logo_canal_blanco_transparent.png` desde
`CP_RGB_p_VerAlt (1).jpg`.

**Preservación de funcionalidad**: cero cambios en models,
controllers de negocio (CanalController, SceneController,
CalendarController, CountdownController, AutopilotV2Controller) ni
señales/slots. El refactor es puramente visual + reestructuración de
layout del shell. Toda la operación (rotación, transmisión, apply
canal, calibración, Autopilot v2) funciona idéntica.

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
