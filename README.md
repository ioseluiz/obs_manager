# OBS Automation Manager - División de Ingeniería

Aplicación de escritorio desarrollada en Python con PyQt6 para la automatización y gestión remota de transmisiones corporativas en OBS Studio. Diseñada para centralizar la operación de pantallas digitales, permitiendo una rotación de contenido autónoma, gestión dinámica de dashboards live y programación temporal por escena.

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

## 🛠️ Requisitos del Sistema

* **Python 3.10+**
* **OBS Studio 28.0+** (con WebSocket habilitado)
* **Librerías:** `PyQt6`, `obsws-python`, `python-dotenv`, `Pillow`

## 🚀 Instalación y Configuración

1. **Preparar el entorno virtual:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

2. **Instalar dependencias:**
   ```bash
   pip install PyQt6 obsws-python python-dotenv Pillow
   ```

3. **Configurar OBS WebSocket:**
   - En OBS: Herramientas → Ajustes del servidor WebSocket.
   - Habilitar el servidor, definir puerto (4455 por defecto) y contraseña.

4. **Vincular la Aplicación:**
   - En el botón ⚙ Ajustes de la app, ingresar las credenciales de OBS.
   - Al conectar se genera automáticamente un archivo `.env` para persistir la configuración.

## ▶️ Ejecución

```bash
python main.py
```

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
| Configuración de OBS + calibración calendario | `.env` en la raíz del ejecutable |

## 📦 Generar Ejecutable (.exe)

El proyecto incluye `build.bat` para compilar en un ejecutable de Windows sin necesidad de Python instalado.

**Requisito previo (solo la primera vez):**
```bash
pip install pyinstaller
```

**Uso:** doble-click en `build.bat`. El proceso limpia compilaciones anteriores y genera el ejecutable en `dist\OBS_Automation_Manager.exe`.

## 🏗 Arquitectura

MVC clásico:
- `models/` — capa de datos (SQLite via `SceneModel`, `SettingsModel`, `CalendarModel`, `CountdownModel`; cliente OBS via `OBSClient`).
- `views/` — widgets PyQt6 (`SceneView`, `SceneEditDialog`, `ScheduleWidget`, `LogsView`, `CalendarView`, `CountdownView`, `SettingsDialog`, `MainWindow`).
- `controllers/` — orquestación (`MainController`, `SceneController`, `CalendarController`, `CountdownController`).
- `core/` — infraestructura (`database`, `workers` incluye `OBSConnectionWorker` y `OBSWatchdog`, `logging_setup`).

## 📝 Notas de Operación

- **Sincronización Horaria**: para que el calendario cambie de día automáticamente a la medianoche, la app debe permanecer abierta y con el rotador iniciado.
- **Seguridad**: el `.env` contiene información sensible; asegúrate de mantenerlo en `.gitignore`.
- **Auditoría**: la pestaña Logs muestra cada rotación (`Rotar → 'X' (dur 20s, tipo url)`), reconexión y error. Los archivos rotan a 1 MB.
