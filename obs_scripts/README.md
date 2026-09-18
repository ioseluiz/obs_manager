# OBS Automation Manager — Scripts para OBS

Esta carpeta contiene scripts nativos que corren **dentro de OBS Studio**
(a diferencia de la app cliente que corre en la laptop del operador).

## Contenido

| Archivo | Descripción |
|---|---|
| `autopilot.lua` | Rotador autónomo. Mantiene la rotación de escenas activa cuando la app cliente se desconecta. |
| `PROTOCOL.md` | Contrato JSON entre la app y el script. |

## Instalación del `autopilot.lua`

**Prerequisito**: acceso al servidor donde corre OBS (RDP, físico, etc.).
Esta instalación se hace **una sola vez**; después el operador de la app
no vuelve a tocar OBS.

> **Ojo con OBS portable**: no hay una carpeta fija donde OBS "auto-descubra"
> los scripts. El `.lua` puede vivir en cualquier ruta accesible — lo
> importante es registrarlo desde OBS con **Herramientas → Scripts → +**.
> Una vez registrado, queda persistido en la scene collection actual y se
> auto-carga en cada arranque.

### Paso 1 — Copiar el `.lua` al servidor

Copiar `autopilot.lua` a una carpeta del servidor donde OBS pueda leerlo.

**Ubicación recomendada según el tipo de OBS:**

| Tipo de OBS | Ubicación sugerida |
|---|---|
| **OBS Portable** | Al lado del ejecutable, por ejemplo `<obs-portable>\scripts\autopilot.lua` (crear la carpeta `scripts` si no existe). |
| **OBS instalado** | `%APPDATA%\obs-studio\scripts\autopilot.lua` (crear la carpeta si no existe). |

Estas ubicaciones son sugerencias — el `.lua` puede vivir en **cualquier
ruta accesible** al usuario que corre OBS. Lo que importa es el paso 2.

### Paso 2 — Registrar el script en OBS

1. Abrir **OBS Studio** en el servidor.
2. Menú **Herramientas → Scripts** (Tools → Scripts).
3. Click en el botón **+** (arriba a la izquierda del panel).
4. Navegar hasta la ruta del `autopilot.lua` (paso 1) y seleccionarlo.
5. En el panel derecho debería aparecer la descripción:
   *"OBS Automation Manager — Autopilot"*.

Si aparece la descripción, el script está cargado. OBS persiste la ruta
en la scene collection actual — al próximo arranque queda auto-cargado.

### Paso 3 — Verificar carga en logs

Abrir el log actual de OBS: **Help → Log Files → View Current Log**.

Buscar líneas que empiecen con `[autopilot]`:

```
[autopilot] cargando v1.0.0
[autopilot] creado text source: __autopilot_config__
[autopilot] creado text source: __autopilot_state__
[autopilot] timers armados; a la espera de config de la app
```

Si aparecen, todo OK. Si no aparecen o hay errores, ver la sección
Troubleshooting abajo.

### Paso 4 — Verificación cruzada desde la app cliente

En la app OBS Automation Manager (Ajustes → sección Autopilot — llega en
el PR AUT-3) va a aparecer:

```
✓ Autopilot instalado en OBS (v1.0.0)
```

## Actualización a versión nueva

Cuando saquemos una versión nueva de `autopilot.lua`:

1. Reemplazar el archivo `.lua` en la ubicación donde lo copiaste (paso 1).
2. En OBS → **Herramientas → Scripts** → seleccionar el script en la
   lista de la izquierda → click en el botón **↻** (Reload script) arriba
   a la derecha.

O directamente reiniciar OBS — la ruta persiste en la scene collection.

## Desinstalación

En OBS → **Herramientas → Scripts** → seleccionar `autopilot.lua` → click
en **–**. El script deja de correr inmediatamente.

Los text sources `__autopilot_config__` y `__autopilot_state__` quedan
"huérfanos" en OBS pero no molestan — son sources sueltos que no forman
parte de ninguna escena. Si querés borrarlos:
1. Panel **Sources** de una escena cualquiera → botón + → seleccionar
   uno de los text sources huérfanos → **Add Existing**.
2. Ahora aparece en la escena. Click derecho → **Remove**.

O simplemente ignorarlos — no consumen recursos cuando nadie los usa.

## Troubleshooting

### El log de OBS no muestra líneas `[autopilot]`

- Verificar que el archivo `.lua` no tenga errores de sintaxis. OBS
  reporta el error cuando falla el load. Buscar en el log líneas del
  script Lua con "error at line X".
- Verificar que la versión de OBS soporte Lua scripting. OBS 28+ lo
  incluye por defecto.

### Aparece "Scripts unavailable"

- OBS puede estar sin soporte de scripting. En Windows, esto es raro
  con OBS oficial. Si usás una build no-oficial, verificar que incluya
  Lua.

### No se crean los text sources `__autopilot_config__` / `__autopilot_state__`

- Revisar en el panel **Sources** de una escena (podés ir agregando
  "Add Existing") si aparecen en la lista.
- Si no aparecen, quizás la creación falló. Verificar el log de OBS
  para líneas de error del script (buscar "text_gdiplus" o "no se
  pudo crear").

### El script se carga pero en el log dice "mode active" sin rotar

- Correcto — sin config publicada (`playlist_size: 0`), el script no
  tiene nada que rotar. Esto es el estado normal antes de que la app
  cliente le mande la playlist.
