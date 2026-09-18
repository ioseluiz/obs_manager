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

1. Copiá `autopilot.lua` al servidor donde vive OBS. Ubicación recomendada:

   ```
   %APPDATA%\obs-studio\scripts\autopilot.lua
   ```

   (podés ponerlo en cualquier otro lado, la carpeta anterior es la típica
   para scripts de usuario).

2. Abrí OBS Studio en el servidor.

3. Menú **Herramientas → Scripts** (Tools → Scripts).

4. Click en el botón **+** (arriba a la izquierda del panel de scripts).

5. Seleccionar el archivo `autopilot.lua` copiado en el paso 1.

6. En el panel de descripción del script vas a ver un texto que empieza con
   *"OBS Automation Manager — Autopilot"*. Si aparece, el script está
   cargado correctamente.

7. Verificar en la consola de logs de OBS (View → Docks → Logs, o menú
   Help → Log Files → View Current Log):

   ```
   [autopilot] cargando v1.0.0
   [autopilot] creado text source: __autopilot_config__
   [autopilot] creado text source: __autopilot_state__
   [autopilot] timers armados; a la espera de config de la app
   ```

## Verificación desde la app cliente

Después de la instalación, en la app OBS Automation Manager
(Ajustes → sección Autopilot) debería aparecer:

```
✓ Autopilot instalado en OBS (v1.0.0)
```

Si aparece `⚠ Autopilot no encontrado`, revisar:
- Que OBS Studio esté corriendo en el servidor.
- Que el WebSocket de OBS esté habilitado y accesible (misma
  conexión que usa la app para todo lo demás).
- Que el script esté cargado (paso 5 arriba).

## Actualización a versión nueva

Cuando saquemos una versión nueva de `autopilot.lua`:

1. Reemplazar el `.lua` en el servidor (`%APPDATA%\obs-studio\scripts\`).
2. En OBS → Herramientas → Scripts, seleccionar el script y click en
   **Recargar scripts** (botón con flecha circular).

O simplemente reiniciar OBS — el script se auto-carga si estaba en la
lista.

## Desinstalación

En OBS → Herramientas → Scripts → seleccionar `autopilot.lua` → **–**.

Los text sources ocultos (`__autopilot_config__` y `__autopilot_state__`)
quedan huérfanos en OBS pero no molestan — se pueden borrar manualmente
desde el panel Sources si aparecen en alguna escena (no deberían).
