# Protocolo Autopilot v2.0 (multi-canal)

Contrato entre la app cliente y el script `autopilot_v2.lua` para la rama
v2.x de la app, que introduce **canales multi-salida** (ver guía de
usuario, sección "Canales Multi-Salida").

Como el v1.x, la comunicación es **únicamente** vía dos text sources
ocultos en OBS que actúan como buzones — sólo APIs estándar de
obs-websocket (`SetInputSettings` / `GetInputSettings`), sin endpoints
custom. Los text sources se crean solos (los crea el script al arrancar);
no están adosados a ninguna escena.

El Autopilot v2 **convive** con un posible Autopilot v1 ya instalado
en el mismo servidor: usa pares de buzones distintos y nombres de
script distintos. Cada versión opera sobre su propio ámbito.

## Buzones

| Text source | Dueño escritor | Dueño lector |
|---|---|---|
| `__autopilot_config_v2__` | App | Script |
| `__autopilot_state_v2__` | Script | App |

## Config: `__autopilot_config_v2__` (App → Script)

El campo `text` del text source contiene un JSON con esta forma:

```json
{
  "protocol_version": 2,
  "version": 42,
  "generated_at": "2026-10-20T14:30:00Z",
  "app_heartbeat_at": "2026-10-20T14:29:59Z",
  "canales": [
    {
      "canal_id": -1,
      "modo_rotacion": "program_global",
      "playlist": [
        {
          "name": "Bienvenida",
          "duration_seg": 20,
          "active_days": 127,
          "active_time_start": "",
          "active_time_end": ""
        },
        {
          "name": "Menu comedor",
          "duration_seg": 15,
          "active_days": 31,
          "active_time_start": "11:30",
          "active_time_end": "13:30"
        }
      ],
      "handoff": {
        "active_scene": "Bienvenida",
        "seconds_remaining": 12,
        "at": "2026-10-20T14:29:59Z"
      }
    },
    {
      "canal_id": 3,
      "modo_rotacion": "scene_items",
      "scene_name": "canal_721",
      "filter_name": "udp_out",
      "playlist": [
        {
          "name": "Dashboard 721",
          "scene_item_id": 7,
          "duration_seg": 30,
          "active_days": 127,
          "active_time_start": "",
          "active_time_end": ""
        },
        {
          "name": "Video corporativo",
          "scene_item_id": 9,
          "duration_seg": 45,
          "active_days": 127,
          "active_time_start": "",
          "active_time_end": ""
        }
      ],
      "handoff": {
        "active_index": 2,
        "seconds_remaining": 20,
        "at": "2026-10-20T14:29:59Z"
      }
    }
  ]
}
```

### Campos de nivel raíz

**`protocol_version`** (int, requerido)
Fija a `2` en este documento. El script usa este campo para rechazar
payloads escritos para una versión futura del protocolo (y seguir con la
última config válida en memoria).

**`version`** (int, requerido)
Monotónico. El script sólo re-carga las playlists cuando `version` sube.
La app lo incrementa cada vez que publica una config nueva. Un `version`
menor o igual al último aplicado es no-op (ni rechazo ni error) —
permite republicar la misma config como heartbeat.

**`generated_at`** (string ISO 8601 UTC, opcional)
Timestamp de cuando la app generó la config. Sólo informativo.

**`app_heartbeat_at`** (string ISO 8601 UTC)
Cada publicación cuenta como heartbeat — el script registra `os.time()`
cuando este valor cambia respecto al anterior y usa el timeout (30 s
por defecto) para decidir si tomar control. **La app debe publicar al
menos cada 15 s** para mantener al script en standby. Si el valor no
cambia entre llamadas (porque la app está colgada escribiendo el mismo
JSON), el script lo trata como *sin heartbeat* y el timeout corre.

**`canales`** (array de objetos, requerido)
Un entry por cada canal activo que la app quiere delegar al script
cuando pierda heartbeat. Puede estar vacío (el script no rota nada en
modo active, pero sigue publicando estado).

### Campos por canal

**`canal_id`** (int, requerido)
Identificador del canal. Convención:
- `-1` → Canal Principal (legacy, rota el Program global de OBS).
- `0..N` → canales multi-salida de la tabla `canales`.

**`modo_rotacion`** (string, requerido)
- `"program_global"`: para rotar, el script llama
  `obs_frontend_set_current_scene(playlist[active_index].name)`. El
  canal cambia la escena en el Program global de OBS. **Sólo un canal
  puede tener este modo** (típicamente `canal_id=-1`); si hay más de uno
  configurado así, el comportamiento es indeterminado.
- `"scene_items"`: para rotar, el script oculta todos los scene items
  de `scene_name` listados en la playlist y muestra el que corresponde
  al `active_index` nuevo. No toca el Program global; afecta solo lo
  que compone la escena contenedora del canal.

**`scene_name`** (string, requerido si `modo_rotacion="scene_items"`)
Nombre de la escena contenedora del canal en OBS, donde viven los
scene items que se van a alternar.

**`filter_name`** (string, opcional)
Nombre del filtro Source Record anclado a `scene_name` que emite el
UDP del canal. Si está presente, el script verifica en cada tick que
el filtro esté habilitado y lo re-habilita si lo encuentra deshabilitado.
Defensa contra apagados accidentales mientras la app no está. En v2
siempre es `"udp_out"` (constante del `output_adapter`).

**`playlist`** (array de objetos, requerido)
Items a rotar. Cada item:
- `name` (string): etiqueta del item. En `scene_items`, es el nombre
  del scene item (informativo); el que importa para ocultar/mostrar es
  `scene_item_id`. En `program_global`, es el nombre exacto de la
  escena en OBS.
- `scene_item_id` (int, requerido en modo `scene_items`): ID del scene
  item dentro de `scene_name`. Lo devuelve OBS cuando se crea el item;
  la app lo persiste en la tabla `canal_items` o lo lee con
  `GetSceneItemList`.
- `duration_seg` (int): segundos que dura antes de rotar.
- `active_days` (int, 0–127): bitmask de días. Bit 0 = lunes, …, bit 6
  = domingo. `127` = todos los días. `0` se trata como `127` para no
  romper configs sin campo.
- `active_time_start` (string "HH:MM" o ""): inicio de ventana horaria.
- `active_time_end` (string "HH:MM" o ""): fin de ventana horaria. Si
  `start > end`, la ventana cruza medianoche (`22:00` → `02:00`). Si
  ambos son `""` → siempre activa (con día ok).

**`handoff`** (objeto, opcional)
Presente sólo cuando la app está entregando control de este canal
(al cerrar) o recuperándolo (al reconectar). Sin `handoff` el script
empieza desde `active_index = 1` (1-indexed, igual que v1).
- Modo `program_global`: `{active_scene: str, seconds_remaining: int, at: iso}`.
- Modo `scene_items`:   `{active_index: int, seconds_remaining: int, at: iso}`.

Un `handoff` con `seconds_remaining <= 0` se trata como ausente (fix
del bug C del v1 — handoff vacío corrompía el cursor del script).

## Estado: `__autopilot_state_v2__` (Script → App)

El script publica en cada tick de rotación (1 s):

```json
{
  "script_version": "2.0.0",
  "protocol_version": 2,
  "mode": "active",
  "updated_at": "2026-10-20T14:30:00Z",
  "last_config_version": 42,
  "canales": [
    {
      "canal_id": -1,
      "modo_rotacion": "program_global",
      "active_scene": "Bienvenida",
      "active_index": 1,
      "seconds_remaining": 12,
      "last_rotation_at": "2026-10-20T14:29:59Z",
      "playlist_size": 2
    },
    {
      "canal_id": 3,
      "modo_rotacion": "scene_items",
      "scene_name": "canal_721",
      "active_scene_item_id": 7,
      "active_index": 1,
      "seconds_remaining": 20,
      "last_rotation_at": "2026-10-20T14:29:59Z",
      "playlist_size": 2
    }
  ]
}
```

### Campos de nivel raíz

**`script_version`**: versión del script en el servidor (por ejemplo
`"2.0.0"`). La app la usa para saber si hay que actualizar.

**`protocol_version`**: fijo a `2`. Permite a la app validar que está
hablando con un script v2 antes de confiar en el shape del state.

**`mode`**: `"standby"` o `"active"`.
- `"standby"` → la app está viva (heartbeat fresco). El script no rota
  ningún canal, pero sigue vigilando los filtros `filter_name` para
  mantenerlos habilitados.
- `"active"` → sin heartbeat por >30 s. El script está rotando todos
  los canales habilitados.

**`updated_at`**: ISO 8601 UTC del tick que generó este estado.

**`last_config_version`**: `version` de la última config aplicada.
Confirma a la app que su publicación llegó.

**`canales`**: array con el estado de cada canal recibido en la última
config, en el mismo orden.

### Campos por canal

**`canal_id`**: igual que en la config.

**`modo_rotacion`**: igual que en la config (reflejo del valor
aplicado).

**`active_scene`** (modo `program_global`): nombre de la escena activa
ahora (según el script).

**`scene_name`** (modo `scene_items`): escena contenedora.

**`active_scene_item_id`** (modo `scene_items`): scene item visible
ahora en la escena contenedora.

**`active_index`** (1-indexed, 0 = ninguno): cursor dentro de la
playlist de este canal.

**`seconds_remaining`**: countdown para la próxima rotación de este
canal.

**`last_rotation_at`**: ISO 8601 UTC de la última vez que el script
rotó este canal. Vacío si aún no rotó nada.

**`playlist_size`**: cantidad de items en la playlist actual del canal.

## Flujo end-to-end

### App corriendo — modo standby

```
[ App tick cada 5s ]                      [ Script tick cada 500ms ]
        │                                           │
        │ SetInputSettings(config, {                │
        │   version: 42,                            │
        │   app_heartbeat_at: "...",                │
        │   canales: [                              │
        │     {canal_id:-1, modo:"program_global",  │
        │      playlist:[...]},                     │
        │     {canal_id:3, modo:"scene_items",      │
        │      scene_name:"canal_721",              │
        │      filter_name:"udp_out",               │
        │      playlist:[...]}                      │
        │   ]                                       │
        │ })                                        │
        │ ──────────────────────────────────────▶   │
        │                                           │ ingest_config()
        │                                           │ last_heartbeat_str cambia
        │                                           │ → last_heartbeat_epoch=now
        │                                           │ mode = "standby"
        │                                           │
        │                                           │ tick_rotation():
        │                                           │   mode=standby → no rota
        │                                           │   verifica filter_name
        │                                           │   publica state
        │
        │ GetInputSettings(state)                   │
        │ ◀──────────────────────────────────────   │
        │ ve mode="standby", N canales ok           │
```

### Laptop apagada — hand-off

Al cerrar la app, se publica una config final con `handoff` por canal.
Después el script toma control cuando el timeout vence y rota cada
canal independientemente, cada uno con su propio `active_index` y
`seconds_remaining`. Los filtros `udp_out` quedan habilitados.

### App vuelve — retoma

Al reconectar, la app lee `__autopilot_state_v2__`, localiza cada
canal por `canal_id` y sincroniza su `_RotatorState` local:
`active_index` + `seconds_remaining` desde el estado publicado. El
primer heartbeat devuelve el script a `standby`.

## Reglas de compatibilidad

- El script debe tolerar JSON con campos que no reconoce (ignorarlos).
- El script debe tolerar `canales` vacío (no rota nada, pero sigue
  publicando estado).
- El script debe tolerar un canal con `playlist` vacía (no rota ese
  canal; sigue vigilando su filtro si tiene `filter_name`).
- El script debe tolerar `active_days = 0` (se trata como `127`).
- La app debe tolerar `active_index = 0` (ningún activo), `mode`
  desconocido (asumir "active" conservador), y canales en el state que
  ella ya no conoce (ignorar — probablemente un canal que fue borrado
  entre publicaciones).
- Un `version` menor o igual al último aplicado es no-op.
- `protocol_version` != 2 → script loguea y mantiene última config
  válida (no se cuelga ni rompe).

## Convivencia con Autopilot v1

Si el servidor OBS tiene ambos scripts cargados (`autopilot.lua` v1 +
`autopilot_v2.lua` v2):
- Cada script observa sólo su propio par de buzones.
- Las publicaciones de la app v1 llegan sólo a los buzones v1
  (`__autopilot_config__` / `__autopilot_state__`).
- Las publicaciones de la app v2 llegan sólo a los buzones v2
  (`__autopilot_config_v2__` / `__autopilot_state_v2__`).
- Un canal gestionado por v2 en modo `program_global` compite con el
  rotador v1 por el Program global. El operador no debe habilitar esta
  combinación: v2 cubre el mismo caso de v1 y además los canales
  multi-salida, así que la ruta esperada en servidores v2 es
  "deshabilitar o remover `autopilot.lua` v1 cuando `autopilot_v2.lua`
  esté estable".

## Sin script instalado

Si el script v2 no está corriendo en el servidor:
- `GetInputSettings(__autopilot_config_v2__)` devuelve 404.
- La app detecta esto, oculta el label "Autopilot v2 activo" y el
  comportamiento normal (rotador local por canal) sigue funcionando
  como antes.
- La app no cae a v1 automáticamente — si quieres rotación persistente
  en v2, instala `autopilot_v2.lua`.

---

Contenido elaborado con apoyo de IA (TD-NCI-013 num. 5.2)
