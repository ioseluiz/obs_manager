# OBS Automation Manager - División de Ingeniería

Aplicación de escritorio desarrollada en Python con PyQt6 para la automatización y gestión remota de transmisiones corporativas en OBS Studio. Este sistema ha sido diseñado para centralizar la operación de pantallas digitales, permitiendo una rotación de contenido autónoma y la gestión dinámica de calendarios técnicos.

## 🌟 Características Principales

* **Rotador de Escenas Universal:** Gestión de una lista de reproducción en bucle que admite imágenes (JPG/PNG), videos locales (MP4/MOV), sitios web y Dashboards (Power BI) mediante *Browser Sources*.
* **Monitoreo en Tiempo Real:** Visualización de la fecha actual del sistema y conteo regresivo segundo a segundo del tiempo de exposición de cada escena.
* **Módulo de Calendario Automatizado:**
    * Construcción de escenas "Cero Manual" que integran fondo y marcador.
    * Lógica de **Auto-Escala** basada en Pillow para forzar el marcador a un ancho visual de 275px.
    * **Auto-Calibración:** Desplazamiento matemático automático de la figura dorada hacia el día correspondiente a la medianoche (basado en la cuadrícula de 274x155px con espaciados de 159x148px).
* **Sincronización de Base de Datos:** Eliminación y creación de escenas en espejo (App + OBS) para mantener el entorno de trabajo limpio.

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

- En OBS: Herramientas -> Ajustes del servidor WebSocket.
- Habilitar el servidor, definir puerto (4455 por defecto) y contraseña.

4. **Vincular la Aplicación:**

- En la pestaña de ⚙️ Ajustes de la App, ingresar las credenciales de OBS.
- Al conectar, se generará automáticamente un archivo .env para persistir la configuración y la calibración.

## ▶️ Ejecución

Para iniciar el centro de mando de la transmisión, ejecuta:

```bash
python main.py
```

## 📝 Notas de Operación

- Sincronización Horaria: Para que el marcador del calendario cambie de día automáticamente a la medianoche, la aplicación debe permanecer abierta y con el rotador iniciado.
- Seguridad: El archivo .env contiene información sensible de conexión y calibración local; asegúrese de que esté incluido en el .gitignore antes de cualquier despliegue en repositorios compartidos.