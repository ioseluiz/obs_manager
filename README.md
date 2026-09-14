# OBS Automation Manager - División de Ingeniería

Aplicación de escritorio desarrollada en Python con PyQt6 para la automatización y gestión remota de transmisiones corporativas en OBS Studio. Diseñada para centralizar la operación de pantallas digitales, permitiendo una rotación de contenido autónoma, gestión dinámica de dashboards live y programación temporal por escena.

## 📑 Contenido

- [🌟 Características Principales](#-características-principales)
- [🛠️ Requisitos del Sistema](#️-requisitos-del-sistema)
- [🚀 Instalación y Configuración](#-instalación-y-configuración)
- [🌐 Conectar a OBS en otro equipo](#-conectar-a-obs-en-otro-equipo)
- [🧭 Guía de uso — primeros pasos](#-guía-de-uso--primeros-pasos)
- [🎛 Canales Multi-Salida](#-canales-multi-salida)
- [🎥 Reproducir un canal en una pantalla](#-reproducir-un-canal-en-una-pantalla)
- [📊 Calibración de Capacidad](#-calibración-de-capacidad)
- [🔐 Sesiones de Dashboard (Power BI)](#-sesiones-de-dashboard-power-bi-sistemas-con-login)
- [📂 Ubicaciones de Datos](#-ubicaciones-de-datos)
- [📦 Instalador de Windows](#-instalador-de-windows)
- [🏗 Arquitectura](#-arquitectura)
- [📝 Notas de Operación](#-notas-de-operación)

## 🌟 Características Principales

### Rotador de Escenas Universal
Gestión de una lista de reproducción en bucle con soporte para múltiples tipos de contenido:
- **Imágenes** (JPG, PNG, GIF, BMP) — image_source de OBS.
- **Videos locales** (MP4, MOV, MKV, AVI, WEBM, FLV, M4V) — ffmpeg_source con controles avanzados de reproducción.
- **Sitios web / Dashboards live** (Power BI, Grafana, dashboards internos) — browser_source con manejo de sesión persistente.

### Escenas Web (Dashboards / Sitios Live)
- Ancho, alto y FPS configurables por escena.
- **Persistencia de sesión** — mantiene el navegador de OBS vivo entre rotaciones para preservar login (Power BI, sistemas corporativos con autenticación).
- **Recargar al entrar** — F5 automático cada vez que la escena se activa (opcional).
- **CSS custom** — inyección de estilos en la página cargada (ocultar sidebars, ajustar layout de dashboards).
- **Auto-refresh periódico** — recarga programada cada N segundos mientras la escena está activa (útil para dashboards live que no se actualizan solos).

### Opciones de Video Avanzadas
- **Loop on/off** — reproducir en bucle o quedar en el último frame.
- **Reiniciar al entrar** — restart from beginning en cada activación.
- **Mute + control de volumen** (0–100%).
- **Offset de inicio** — reproducir desde un segundo específico (fragmentos del video).
- **Detección automática de duración** — ajusta la duración de la escena al largo del video.

### Ajuste Visual por Escena
- **Zoom** (10–500%) y **Pan X/Y** persistentes por escena.
- Aplica a cualquier tipo de source (web, imagen, video).
- **Panel "Ajuste en vivo"** con sliders que envían el transform a OBS en tiempo real mientras arrastras — el cambio se ve inmediatamente en el navegador de Power BI **sin recargar la página** (preserva sesión).

### Programación Temporal por Escena
- **Días de la semana activos** — bitmask configurable (Lu-Do).
- **Ventana horaria opcional** — solo mostrar entre HH:MM y HH:MM.
- Soporta ventanas que cruzan la medianoche (`22:00` a `02:00`).
- Ejemplos: menú del comedor L-V 11:30-13:30, dashboard operativo horario laboral, aviso de fin de semana.
- Si no hay escenas en ventana, el rotador espera y reintenta cada 60s.

### Edición In-Place (sin perder sesión)
Cambios en las escenas se aplican al navegador vivo de OBS **sin recrear el browser_source**:
- URL, dimensiones, FPS, CSS, zoom/pan, volumen: patch in-place → sesión de Power BI intacta.
- Cambio de tipo (archivo ↔ URL): recrea solo el input, mantiene la escena.
- Nombre: renombra escena e input en OBS.
- **Reflejo en escena activa sin esperar rotación**: si editas la escena que se está mostrando, el countdown se recalcula preservando el tiempo transcurrido, el intervalo de auto-refresh se reprograma, y el offset de video reajusta el cursor en el acto.

### Control Operacional
- **▶ Iniciar / ⏹ Detener** rotación.
- **⏸ Pausar / ▶ Reanudar** — congela el countdown sin salir del ciclo.
- **⏮ Anterior / ⏭ Siguiente** — salto manual entre escenas.
- **Doble-click en fila** — ir directo a esa escena.
- **📋 Duplicar** — clonar una escena con todos sus ajustes.
- **▲ Subir / ▼ Bajar** — reordenar en caliente sin interrumpir la escena en pantalla.
- **Highlight visual** de la escena en reproducción en la tabla.
- **Preview thumbnail** por escena en la tabla — captura automática al rotar + botón `🔄 Previews` para refresh manual completo.

### Templates de Escena
Presets configurables al agregar una escena para acelerar casos comunes:
- **Dashboard Power BI Corporativo** — 1920×1080, mantiene sesión, refresh 5 min, CSS que oculta sidebars.
- **Grafana / Monitoreo Live** — refresh cada 60s, sin sesión.
- **Sitio Público / Landing** — recarga al entrar, sin refresh.
- **Video Corporativo Silencioso** — loop + restart + mute.
- **Imagen Estática 20s** — duración fija.

### Export / Import de Configuración
- **📤 Exportar** todas las escenas a un archivo JSON portable (todos los campos: tipo, dimensiones, CSS, transform, programación, video ops).
- **📥 Importar** desde JSON con vista previa (lista de escenas, formato, fecha) y modo:
  - **➕ Añadir al final** (renombra colisiones como "X (importada)").
  - **♻ Reemplazar todas las existentes** (con confirmación fuerte).
- Al importar, opcionalmente se crean también en OBS con todos los settings.

### Robustez (Producción 24/7)
- **Auto-reconexión con watchdog** — ping cada 10s a OBS. Al detectar caída: reintenta con backoff exponencial (1, 2, 4, 8… 60s).
- **Indicador de estado** en la barra superior: 🟢 Conectado / 🟠 Reconectando / 🔴 Sin conexión.
- **Pausa/reanuda automática del rotador** durante caídas de OBS.
- **Logs persistentes** con rotación (5 archivos × 1 MB) en `%LOCALAPPDATA%\OBS_Automation_Manager\logs\app.log`. Auditoría de cada rotación, reconexión, error.
- **Pestaña Logs** integrada en la UI: últimas 200 líneas con auto-refresh cada 5s, botón "Abrir carpeta".

### Módulo de Calendario Automatizado
- Construcción de escenas "Cero Manual" que integran fondo y marcador.
- **Auto-Escala** basada en Pillow (marcador a 275px de ancho).
- **Auto-Calibración** — desplazamiento matemático de la figura dorada al día correspondiente a la medianoche.

### Módulo de Contadores
- Cuenta regresiva/adelante hacia fechas objetivo.
- Actualización automática de sources de texto en OBS (días/horas/minutos/segundos).
- Opción de repetición anual.

### Sincronización de Base de Datos
Eliminación y creación de escenas en espejo (App + OBS) para mantener el entorno limpio.

### Canales Multi-Salida (streaming UDP paralelo)
- **N canales independientes** — cada uno con su propia rotación, encoder, bitrate, resolución y URL destino UDP. Ideal para mandar contenidos distintos a distintas pantallas físicas desde un solo OBS.
- **Preset por canal** — resolución (720p, 1080p, 1440p, 4K) y FPS (30/60) explícitos. El validador conoce el costo real de cada preset (720p30 = 0.5 unidades vs 1080p60 = 2 unidades).
- **Calibración automática** — mide cuántos canales aguanta cada encoder (x264, qsv, nvenc, amf) en este equipo. Se guarda por fingerprint del equipo — reinstalar mantiene la calibración.
- **Validación al conectar** — si la config excede la capacidad calibrada, sale un dialog con sugerencias por canal. Nunca auto-degrada — el user decide.
- **Watchdog runtime** — vigila `encoding_lag` cada 10s durante producción, avisa non-blocking si detecta degradación sostenida.
- **Botón 🎥 Preview** — verificá localmente lo que sale por el UDP del canal sin depender del firewall.
- **Botón 🔬 Diagnóstico** — inspecciona los settings efectivos del filtro `udp_out` en OBS.

## 🛠️ Requisitos del Sistema

**Requeridos siempre:**
* **Python 3.10+** (o el instalador `.exe` que ya trae Python embebido)
* **OBS Studio 28.0+** con WebSocket habilitado
* **Plugin Source Record de Exeldro** — necesario para canales multi-salida
* **Librerías Python:** `PyQt6`, `obsws-python`, `python-dotenv`, `Pillow`

**Opcionales (solo si querés usar el botón 🎥 Preview):**
* **ffmpeg / ffplay** — reproductor local de canales UDP sin depender del firewall

## 🚀 Instalación y Configuración

### Opción A — Instalador .exe (recomendado para usuarios finales)

1. Descargar `OBS_Automation_Manager_Setup_vX.Y.Z.exe` desde la última release en GitHub.
2. Doble click → instala per-user en `%LOCALAPPDATA%\Programs\OBS_Automation_Manager\` sin pedir admin.
3. Continuar con el paso **⚙ Configurar OBS WebSocket** más abajo.

### Opción B — Ejecutar desde código fuente (desarrolladores)

1. **Preparar el entorno virtual:**
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```

2. **Instalar dependencias:**
   ```powershell
   pip install PyQt6 obsws-python python-dotenv Pillow pywin32
   ```

3. **Ejecutar:**
   ```powershell
   python main.py
   ```

### ⚙ Configurar OBS WebSocket

1. En OBS Studio: **Herramientas → Ajustes del servidor WebSocket**.
2. Habilitar el servidor, definir puerto (4455 por defecto) y contraseña.
3. Copiar la contraseña — la vas a necesitar en el próximo paso.

### 🔌 Vincular la Aplicación

1. Al abrir la app por primera vez aparece el ⚙ **Ajustes**. Si no aparece, click en el botón Ajustes del toolbar.
2. Ingresar **Host / IP**, **Puerto** y **Contraseña** copiada de OBS.
3. Pulsar **Probar conexión** — valida sin guardar. Si sale verde ✓, guardá.
4. La app genera automáticamente un archivo `.env` en `%LOCALAPPDATA%\OBS_Automation_Manager\` para persistir la configuración.

### 🔌 Instalar el plugin Source Record (para canales multi-salida)

Los canales multi-salida requieren el plugin **Source Record** de Exeldro. Si sólo vas a usar el rotador global (Canal Principal), podés saltar este paso.

1. Descargar desde: https://obsproject.com/forum/resources/source-record.1285/ (o la última versión estable en GitHub Releases del plugin).
2. Ejecutar el instalador (`.exe`). Instala en la carpeta de OBS automáticamente.
3. Reiniciar OBS. Verificar: click derecho sobre cualquier escena → **Filtros** → **Añadir filtro** → debe aparecer **"Source Record"** en la lista.

### 🎬 Instalar ffmpeg (opcional — solo para el botón 🎥 Preview)

El botón **🎥 Preview** del panel de canal usa `ffplay` para mostrar el UDP localmente sin tocar el firewall. Si no lo instalás, el botón mostrará un aviso pidiéndolo.

**Con winget** (Windows 10+ / 11 con winget habilitado):
```powershell
winget install Gyan.FFmpeg
```

**Sin admin (portable)**:
1. Descargar el zip desde https://www.gyan.dev/ffmpeg/builds/ (elegir "release essentials").
2. Descomprimir en `%USERPROFILE%\ffmpeg\`.
3. Agregar `%USERPROFILE%\ffmpeg\bin` al **PATH del usuario** (Panel de Control → Variables de entorno → PATH del usuario → Nuevo). No requiere admin.
4. **Reiniciar la app** para que agarre el PATH nuevo.

Verificar: en PowerShell `ffplay -version` debe mostrar la versión sin errores.

## 🌐 Conectar a OBS en otro equipo

Cuando OBS Studio corre en una máquina distinta a la app (setup típico: PC de operación separado del PC de streaming), hay que preparar ambos lados.

### En el equipo con OBS Studio

1. Habilitar el servidor WebSocket (Herramientas → *WebSocket Server Settings*), fijar puerto (default 4455) y contraseña.
2. Abrir el puerto en el firewall de Windows. En PowerShell **como Administrador**:

   ```powershell
   New-NetFirewallRule -DisplayName "OBS WebSocket 4455" -Direction Inbound -Protocol TCP -LocalPort 4455 -Action Allow
   ```

3. Anotar la IP LAN del equipo:

   ```powershell
   ipconfig | Select-String "IPv4"
   ```

### En el equipo con la app

1. Abrir ⚙ Ajustes → poner en **Host / IP** la IP del equipo con OBS (no `localhost`). Puerto y contraseña iguales a los de OBS.
2. Pulsar **Probar conexión** antes de Guardar. Si falla, el label rojo muestra el error exacto (auth, timeout, conexión rechazada) sin tocar la sesión activa.
3. Si `Probar conexión` da timeout: verificar conectividad TCP al equipo remoto:

   ```powershell
   Test-NetConnection -ComputerName 192.168.1.42 -Port 4455
   ```

   Si `TcpTestSucceeded : False` → firewall bloqueando o OBS sin WebSocket habilitado.

### Notas

- El **auto-launch de OBS local** se salta automáticamente cuando el Host apunta a otra máquina (no tiene sentido lanzar un OBS local si esperamos conectarnos a uno remoto).
- La opción "Abrir OBS automáticamente si no está corriendo" puede quedar activa aunque uses OBS remoto — sólo aplica al equipo local.
- El watchdog reconecta con timeout de 3s por intento, así que caídas del OBS remoto se detectan y reintentan sin colgar la UI.

## ▶️ Ejecución

```bash
python main.py
```

## 🧭 Guía de uso — primeros pasos

La app se organiza en pestañas en la barra superior. Estos son los primeros pasos recomendados tras instalar y conectar:

| Pestaña | Para qué sirve |
|---|---|
| **Biblioteca de Escenas** | Crear/editar/borrar todas las escenas del rotador (imágenes, videos, dashboards). No transmite — sólo administra. |
| **Producción** | Panel operativo. Arriba a la izquierda hay un sidebar con **Canal Principal (Global)** + los canales multi-salida que hayas creado. Elegí uno y en el panel de la derecha aparecen los controles de rotación + botón **▶ Transmitir**. |
| **Calendario** | Configura la escena de calendario automático con el marcador dorado que se mueve al día actual. |
| **Contadores** | Cuenta regresiva/adelante a fecha objetivo. |
| **Logs** | Últimas 200 líneas de eventos. Auto-refresh cada 5s. |

### Flujo típico

**Caso A — Una sola salida global (usar Canal Principal):**
1. Ir a **Biblioteca de Escenas** y crear escenas (imágenes, videos, dashboards).
2. Ir a **Producción → Canal Principal (Global)**.
3. Pulsar **▶ Transmitir** → OBS empieza a grabar el output global.
4. Pulsar **▶** (Play del rotador) → empiezan las rotaciones entre las escenas de la Biblioteca.

**Caso B — Varias salidas independientes (canales multi-salida):**
1. Verificar que el plugin **Source Record** está instalado en OBS (ver Instalación).
2. En la primera conexión, la app te va a preguntar **"¿Calibrar ahora?"** — aceptar. Toma ~4 minutos y mide cuántos canales aguanta el equipo por encoder. Ver *📊 Calibración* más abajo.
3. Ir a **Producción → botón ➕ Nuevo canal en el sidebar**. Rellenar:
   - **Nombre** (será el nombre de la escena OBS contenedora).
   - **URL destino** (ej: `udp://192.168.1.50:9001` — la IP de la pantalla receptora).
   - **Encoder / Bitrate / Resolución / FPS** — el cost hint del dialog muestra cuánto pesa este canal.
4. Guardar → el canal aparece en el sidebar. Seleccionarlo → panel de la derecha.
5. Botón **➕ Agregar** para armar la playlist del canal (elegís escenas de la Biblioteca).
6. Botón **📡 Aplicar cambios en OBS** → crea la escena contenedora y el filtro Source Record.
7. Botón **▶ Transmitir** → arranca el output UDP.
8. Botón **▶** (Play del rotador) → empieza a alternar entre los items del canal.

## 🎛 Canales Multi-Salida

**Concepto**: mientras el Canal Principal usa el "Program" global de OBS (una sola escena en pantalla a la vez), los canales multi-salida cada uno tiene:
- Su **propia escena contenedora** en OBS.
- Su **propio filtro Source Record** que streamea a un **URL UDP independiente**.
- Su **propia rotación interna** (alterna visibilidad de scene items dentro de su escena madre).

Esto permite mandar contenido distinto a distintas pantallas (por ejemplo: dashboard operativo al edificio 721, video corporativo a Miraflores) desde un solo OBS.

### Panel de un canal

Al seleccionar un canal en el sidebar de Producción, el panel derecho muestra:

| Botón | Función |
|---|---|
| **▶ Transmitir** | Habilita/deshabilita el filtro UDP del canal. Cuando está prendido, el UDP sale. |
| **▶ / ⏮ / ⏸ / ⏭ / ⏹** | Play / anterior / pausar / siguiente / stop del rotador de ESE canal (independiente de otros canales). |
| **📡 Aplicar cambios en OBS** | Recrea la escena contenedora, el filtro y los scene items desde la config actual. Úsalo tras editar el canal o si OBS se reinició. |
| **🔬 Diagnóstico** | Lee los settings efectivos del filtro `udp_out` desde OBS. Útil cuando el stream no se ve como esperás — verifica encoder, bitrate, keyframe, profile, etc. |
| **🎥 Preview** | Abre una ventana ffplay local con la salida UDP del canal (requiere ffmpeg instalado — ver Instalación). |

## 🎥 Reproducir un canal en una pantalla

Los canales emiten **MPEG-TS sobre UDP**. Para verlos en la pantalla receptora tenés varias opciones:

### Opción A — En tu propio equipo, usando el botón 🎥 Preview

La forma más rápida para verificar que el canal está emitiendo bien:

1. En la app: **Producción → seleccionar el canal → 🎥 Preview**.
2. Se abre una ventana ffplay con el stream en vivo.
3. Cerrar con Ctrl+C en la terminal negra que también se abre.

**Requiere ffmpeg instalado** (ver Instalación).

### Opción B — En una pantalla receptora, usando VLC

Instalar VLC en la máquina receptora. Después:

```powershell
"C:\Program Files\VideoLAN\VLC\vlc.exe" --demux=ts udp://@:9001
```

Reemplazar `9001` con el puerto del URL destino del canal. **El flag `--demux=ts` es obligatorio** — sin él, VLC auto-detecta como MPEG-PS (formato de DVDs) y muestra pantalla negra con timecode avanzando.

**Alternativa permanente en VLC** (evita escribir el flag cada vez):
1. VLC → **Herramientas → Preferencias**.
2. Abajo izquierda: **Show settings: All**.
3. **Input / Codecs → Demuxers**.
4. **Demux module** → cambiar de *Automatic* a **MPEG-TS**.
5. Guardar. Ahora `Media → Open Network Stream → udp://@:9001` funciona sin flag.

### Opción C — Autorizar VLC en el firewall (si tenés admin)

Si tenés permisos de administrador en la máquina receptora y querés que VLC funcione sin trucos:

```powershell
# Como Administrador
New-NetFirewallRule -DisplayName "VLC UDP Multi-Salida" `
  -Direction Inbound `
  -Program "C:\Program Files\VideoLAN\VLC\vlc.exe" `
  -Protocol UDP -Action Allow
```

Después VLC puede abrir el UDP sin `--demux=ts` desde la UI normal.

### Firewall corporativo bloquea UDP a VLC/ffplay

En entornos corporativos, Windows Defender Firewall **suele bloquear inbound UDP** para `vlc.exe` y `ffplay.exe` **sin popup ni error visible** — parece que el stream no llega. Python.exe suele estar autorizado (por otras apps).

**Verificación rápida**: si el archivo `.ts` grabado se ve bien pero el UDP en vivo con VLC es negro, es firewall.

**Workaround sin admin** — el botón 🎥 Preview de la app usa este pattern: Python bindea el puerto UDP (permitido por firewall) y pipea el stream por stdin a ffplay. **Nunca abre puerto UDP con el reproductor directamente**.

Script equivalente que podés usar en cualquier máquina con Python + ffmpeg:

```powershell
venv\Scripts\python.exe scripts\play_canal_local.py 9001
```

## 📊 Calibración de Capacidad

Antes de configurar canales multi-salida, la app necesita saber **cuántos canales UDP simultáneos aguanta este equipo por encoder**. Sin esa medición, no puede validar si tu config va a saturar la CPU/GPU.

### Cuándo se calibra automáticamente

- **Primera vez** que conectás la app a OBS en un equipo → aparece un popup preguntando "¿Calibrar ahora?".
- Después de un **cambio de hardware** o **upgrade mayor de OBS** — la app detecta que el fingerprint del equipo cambió y vuelve a preguntar.

### Cómo re-calibrar manualmente

1. **Ajustes → sección "Calibración de capacidad"**.
2. El label muestra el estado: ✓ calibrado con `x264=N, qsv=M, …` o ⚠ sin calibrar.
3. Botón **🔬 Re-calibrar este equipo**.

### Qué hace la calibración

1. Crea una escena baseline temporal en OBS con un color source gris (1920×1080).
2. Para cada encoder (`x264`, `qsv`, `nvenc`, `amf`):
   - Va agregando filtros UDP a puertos loopback (nadie los lee).
   - Mide `output_skipped_frames_ratio` durante 10 segundos por paso.
   - Cuando supera 5%, marca `nmax = N - 1` para ese encoder.
   - Encoders no disponibles (nvenc sin GPU NVIDIA, amf sin AMD) fallan rápido y se marcan `nmax=0`.
3. Persiste el resultado en `%LOCALAPPDATA%\OBS_Automation_Manager\calibrations.json`, keyed por fingerprint.

Toma ~60 segundos por encoder. Se puede cancelar — guarda lo que alcanzó a medir.

### Validación en tiempo real

- **Al conectar OBS**: la app compara los canales habilitados vs el `nmax` calibrado. Si excede, aparece un dialog con las sugerencias por canal ("baje `edif721` a 720p" o "cambie encoder a qsv"). Nunca auto-degrada — el user decide.
- **Durante producción**: un watchdog cada 10s mide skipped frames. Si sostenidamente >5% durante 30s, aparece un aviso en la barra de estado. También non-bloqueante.

## 🔐 Sesiones de Dashboard (Power BI, sistemas con login)

1. Crea una escena tipo **URL / Dashboard** con `☑ Mantener sesión activa` marcado.
2. En OBS, click derecho sobre el `_Web` source → **Interactuar**.
3. Loguéate en la ventana embebida y marca "Recordarme" cuando el sistema lo ofrezca.
4. Cierra la ventana de Interactuar. La sesión se preserva mientras OBS siga abierto (cookies persistentes si marcaste "Recordarme").

Los cambios posteriores (URL, ancho, alto, CSS, zoom, pan, refresh interval, mute/volumen) se aplican **sin destruir el navegador**, respetando el login.

## 📂 Ubicaciones de Datos

| Archivo | Ruta |
|---|---|
| Base de datos SQLite | `%LOCALAPPDATA%\OBS_Automation_Manager\obs_manager.db` |
| Logs de la aplicación | `%LOCALAPPDATA%\OBS_Automation_Manager\logs\app.log` |
| Configuración de OBS + calibración calendario | `%LOCALAPPDATA%\OBS_Automation_Manager\.env` |

> **Nota de migración**: versiones antiguas guardaban `.env` junto al ejecutable. En el primer arranque tras actualizar, la app detecta ese `.env` legacy y lo mueve automáticamente a la nueva ubicación en `%LOCALAPPDATA%`.

## 📦 Instalador de Windows

Cada tag `vX.Y.Z` pusheado a `main` dispara automáticamente el workflow `.github/workflows/release.yml` que:

1. Compila la app con PyInstaller en modo `--onedir` (vía `OBS_Automation_Manager.spec`).
2. Empaqueta la carpeta resultante con **Inno Setup** (`installer.iss`).
3. Publica el instalador `OBS_Automation_Manager_Setup_vX.Y.Z.exe` como asset del GitHub Release.

**Características del instalador:**
- **Per-user, sin admin**: no requiere UAC ni password de administrador.
- Instala en `%LOCALAPPDATA%\Programs\OBS_Automation_Manager\`.
- Crea shortcut en Start Menu (Desktop opcional).
- Aparece en "Aplicaciones instaladas" del usuario con desinstalador propio.
- Al desinstalar preserva `%LOCALAPPDATA%\OBS_Automation_Manager\` (BD, logs, `.env`) — reinstalar / upgrade conserva la configuración.

**Compilación local (opcional):**
```bash
# 1. Generar la carpeta dist\OBS_Automation_Manager\
build.bat

# 2. Compilar el instalador (requiere Inno Setup 6 instalado)
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=0.0.0-dev installer.iss
# → Output\OBS_Automation_Manager_Setup_v0.0.0-dev.exe
```

## 🏗 Arquitectura

MVC clásico:
- `models/` — capa de datos (SQLite via `SceneModel`, `SettingsModel`, `CalendarModel`, `CountdownModel`; cliente OBS via `OBSClient`).
- `views/` — widgets PyQt6 (`SceneView`, `SceneEditDialog`, `ImportPreviewDialog`, `ScheduleWidget`, `LogsView`, `CalendarView`, `CountdownView`, `SettingsDialog`, `MainWindow`).
- `controllers/` — orquestación (`MainController`, `SceneController`, `CalendarController`, `CountdownController`).
- `core/` — infraestructura (`database`, `workers` con `OBSConnectionWorker`/`OBSWatchdog`, `logging_setup`, `templates`, `importexport`).

## 📝 Notas de Operación

- **Sincronización Horaria**: para que el calendario cambie de día automáticamente a la medianoche, la app debe permanecer abierta y con el rotador iniciado.
- **Seguridad**: el `.env` contiene información sensible; asegúrate de mantenerlo en `.gitignore`.
- **Auditoría**: la pestaña Logs muestra cada rotación (`Rotar → 'X' (dur 20s, tipo url)`), reconexión y error. Los archivos rotan a 1 MB.
