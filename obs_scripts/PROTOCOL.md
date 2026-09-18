# Protocolo Autopilot v1.0

Contrato entre la app cliente y el script `autopilot.lua`. Ambos lados se
comunican **únicamente** vía dos "text sources" ocultos en OBS que actúan
como buzones — no hay endpoints custom del websocket, sólo
`SetInputSettings` / `GetInputSettings` estándar.

Los text sources se crean solos (los crea el script al arrancar). No están
adosados a ninguna escena — son sources "sueltos" que sirven de canal.

## Buzones

| Text source | Dueño escritor | Dueño lector |
|---|---|---|
| `__autopilot_config__` | App | Script |
| `__autopilot_state__` | Script | App |

## Config: `__autopilot_config__` (App → Script)

El campo `text` del text source contiene un JSON con esta forma:

```json
{
  "version": 42,
  "generated_at": "2026-09-18T14:30:00Z",
  "app_heartbeat_at": "2026-09-18T14:29:59Z",
  "playlist": [
    {
      "name": "Bienvenida",
      "duration_seg": 20,
      "active_days": 127,
      "active_time_start": null,
      "active_time_end": null
    },
    {
      "name": "Menú comedor",
      "duration_seg": 15,
      "active_days": 31,
      "active_time_start": "11:30",
      "active_time_end": "13:30"
    }
  ],
  "handoff": {
    "active_scene": "Bienvenida",
    "seconds_remaining": 12,
    "at": "2026-09-18T14:29:59Z"
  }
}
```

### Campos

**`version`** (int, requerido)
Monotónico. El script sólo re-carga la playlist cuando `version` sube. La
app lo incrementa cada vez que publica una config nueva.

**`generated_at`** (string ISO 8601 UTC, opcional)
Timestamp de cuando la app generó la config. Sólo informativo.

**`app_heartbeat_at`** (string ISO 8601 UTC)
Cada publicación cuenta como heartbeat — el script registra `os.time()` y
usa el timeout (30s por defecto) para decidir si tomar control. **La app
debe publicar al menos cada 15s** (con la misma `version` si no hubo
cambios) para mantener al script en standby.

**`playlist`** (array de objetos, requerido)
Escenas en orden de rotación. Cada item:
- `name` (string): nombre exacto de la escena en OBS.
- `duration_seg` (int): segundos que dura antes de rotar.
- `active_days` (int, 0-127): bitmask de días. Bit 0 = lunes, ..., bit 6 =
  domingo. `127` = todos los días. `0` se trata como `127` para no romper
  configs sin campo.
- `active_time_start` (string "HH:MM" o null): inicio de ventana horaria.
- `active_time_end` (string "HH:MM" o null): fin de ventana horaria.
  Si `start > end`, la ventana cruza medianoche (`22:00` → `02:00`).
  Si ambos son null → siempre activa (con día ok).

**`handoff`** (objeto, opcional)
Presente sólo cuando la app está entregando control (al cerrar) o
recuperándolo (al reconectar). Sin `handoff` el script empieza desde
`active_index=0`.
- `active_scene` (string): nombre de la escena donde estaba la rotación.
- `seconds_remaining` (int): segundos que quedaban antes de rotar.

## Estado: `__autopilot_state__` (Script → App)

El script publica en cada tick (1s):

```json
{
  "script_version": "1.0.0",
  "mode": "active",
  "active_scene": "Bienvenida",
  "active_index": 1,
  "seconds_remaining": 12,
  "last_rotation_at": "2026-09-18T14:29:59Z",
  "last_config_version": 42,
  "playlist_size": 5,
  "updated_at": "2026-09-18T14:30:00Z"
}
```

### Campos

**`script_version`**: versión del script en el servidor. La app la usa
para saber si necesita actualizarse.

**`mode`**: `"standby"` o `"active"`.
- `"standby"` → la app está viva (heartbeat fresco). El script no rota.
- `"active"` → sin heartbeat por >30s. El script está rotando por su cuenta.

**`active_scene`**: nombre de la escena en pantalla ahora (según el script).

**`active_index`**: 1-indexed dentro de la playlist recibida. `0` = ninguna.

**`seconds_remaining`**: countdown para próxima rotación.

**`last_rotation_at`**: ISO 8601 UTC de la última vez que el script cambió
de escena. Vacío si aún no rotó nada.

**`last_config_version`**: `version` de la última config aplicada.
Confirma a la app que su publicación llegó.

**`playlist_size`**: cantidad de items en la playlist actual.

**`updated_at`**: ISO 8601 UTC del tick que generó este estado.

## Flujo end-to-end

### App corriendo — modo standby

```
[ App tick cada 5s ]                 [ Script tick cada 500ms ]
        │                                       │
        │ SetInputSettings(config, {            │
        │   version: 42,                        │
        │   app_heartbeat_at: "...",            │
        │   playlist: [...]                     │
        │ })                                    │
        │ ──────────────────────────────────▶   │
        │                                       │ ingest_config()
        │                                       │ last_heartbeat_epoch=now
        │                                       │ mode = "standby"
        │                                       │
        │                                       │ tick_rotation():
        │                                       │   mode=standby → no rota
        │                                       │   publica state
        │
        │ GetInputSettings(state)               │
        │ ◀──────────────────────────────────   │
        │ ve mode="standby", ok                 │
```

### La laptop se apaga — hand-off

```
[ App shutdown ]                     [ Script ]
        │                                       │
        │ Publica config final con handoff:     │
        │ {                                     │
        │   version: 43,                        │
        │   app_heartbeat_at: null,             │
        │   handoff: {                          │
        │     active_scene: "Menú",             │
        │     seconds_remaining: 8              │
        │   }                                   │
        │ }                                     │
        │ ──────────────────────────────────▶   │
        │                                       │ ingest: aplica handoff
        │ App se cierra                         │ active_index → índice de "Menú"
        │                                       │ seconds_remaining → 8
        │                                       │
        │                                       │ 30s después: heartbeat vencido
        │                                       │ mode → "active"
        │                                       │ empieza a rotar
```

### La laptop vuelve — retoma control

```
[ App reconecta ]                    [ Script ]
        │                                       │
        │ Lee state                             │
        │ ◀──────────────────────────────────   │
        │ mode=active, active_scene="Grafana",  │
        │ seconds_remaining=5                   │
        │                                       │
        │ Sincroniza timer local: arranca en    │
        │ "Grafana" con 5s restantes.           │
        │                                       │
        │ Publica config con                    │
        │ app_heartbeat_at="ahora"              │
        │ ──────────────────────────────────▶   │
        │                                       │ mode → "standby"
        │                                       │ (deja de rotar; la app toma control)
```

## Reglas de compatibilidad

- El script debe tolerar JSON con campos que no reconoce (ignorarlos).
- El script debe tolerar `playlist` vacía (no rota, pero sigue publicando estado).
- El script debe tolerar `active_days=0` (se trata como `127`).
- La app debe tolerar `active_index=0` (ningún activo) y `mode` desconocido
  (asumir "active" conservador).
- Un `version` menor o igual al último aplicado es no-op (ni rechazo ni
  error) — permite que la app republique la misma config como heartbeat.

## Sin script instalado

Si el script no está corriendo en el servidor:
- `GetInputSettings(state)` va a devolver 404 (source no existe).
- La app detecta esto y desactiva el modo autopilot en la UI.
- Comportamiento normal (rotador local) sigue funcionando como antes.
