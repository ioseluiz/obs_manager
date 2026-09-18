# Changelog

## v1.8.0 — Autopilot: rotación 24/7 (2026-09-18)

**Objetivo del release**: resolver el problema reportado por operadores donde,
al cerrarse la app o apagarse la laptop del operador, la rotación de escenas
en OBS se detenía. Con Autopilot instalado, la rotación sigue funcionando en
el servidor de OBS **sin depender de la app**.

### 🌟 Nueva feature: Autopilot

Un script Lua (`obs_scripts/autopilot.lua`) se instala una sola vez en el OBS
del servidor. Mientras la app corre, envía heartbeats y el script queda en
standby. Al perder heartbeat por >30s, el script asume el control de la
rotación autónomamente. Al volver la app, cede el control.

- **Wizard visual de instalación** en Ajustes → 🚀 Instalar Autopilot en OBS.
  Guía en 6 pasos, no requiere conocimientos técnicos avanzados del operador.
- **Indicador en la barra de estado**: 🎛 Autopilot listo (verde, en standby)
  vs. 🚀 Autopilot activo (rojo, controlando la rotación).
- **Respeta programación horaria completa**: bitmask de días de la semana +
  rangos HH:MM (soporta cruces por medianoche).
- **Handoff automático al cerrar la app**: publica escena actual + segundos
  restantes para que el script retome exactamente desde ahí.
- **Sincronización bidireccional al reconectar**: la app adopta el estado
  del script y retoma control.
- **Silencioso si no está instalado**: el comportamiento de la app cuando
  el Autopilot no está cargado es idéntico al de v1.7.1.

### 🏗 Arquitectura

- Comunicación entre app y script vía dos text sources ocultos que actúan
  como buzones JSON (`__autopilot_config__` y `__autopilot_state__`).
- Sólo APIs estándar de `obs-websocket v5` (`SetInputSettings` /
  `GetInputSettings`) — sin plugins custom.
- Protocolo documentado en `obs_scripts/PROTOCOL.md`.

### ⚙ Requisitos

- Windows 10/11 (x64).
- OBS Studio 28.0+ (portable o instalado) con WebSocket habilitado.
- Al arrancar la app por primera vez tras instalar, ir a Ajustes → Autopilot
  y seguir el wizard de instalación (una sola vez).

### 🔄 Actualización desde v1.7.1

El instalador preserva la base de datos, logs y `.env` en
`%LOCALAPPDATA%\OBS_Automation_Manager\`. Al reinstalar la nueva versión no se
pierde nada de la configuración anterior.

**Nota**: el Autopilot es opcional. Si un operador no lo instala, la app
funciona exactamente igual que en v1.7.1 (la rotación se pierde al cerrar
la app, como antes). Se recomienda instalarlo en cualquier deploy con OBS
remoto.

### 🐛 Fixes incluidos

- Text sources del buzón mantienen referencia viva para no ser recolectados
  por OBS entre ticks (evita spam de "creado text source" en logs).
- Timers del script se limpian antes de re-registrarse tras reload
  (evita timers zombi tras hot-reload de OBS).
- Heartbeat sólo refresca el estado interno cuando el timestamp cambia
  (evita que el script quede en standby indefinido tras cerrarse la app).
- Handoff con `active_scene` vacía se omite del payload (evita corromper
  el estado del script cuando el rotador no se inició antes de cerrar).

---

## v1.7.1 y anteriores

Ver `git log --oneline v1.7.1` para el historial detallado.
