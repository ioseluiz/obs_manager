import obsws_python as obs
import os
import logging
from PIL import Image

log = logging.getLogger(__name__)

VIDEO_EXTS = ('.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.m4v')
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')


def is_video_file(path):
    return bool(path) and path.lower().endswith(VIDEO_EXTS)


def is_image_file(path):
    return bool(path) and path.lower().endswith(IMAGE_EXTS)


class OBSClient:
    def __init__(self):
        self.client = None
        self.canvas_width = 1920
        self.canvas_height = 1080

    def connect(self, host="localhost", port=4455, password=""):
        # Cerrar cliente previo para evitar sockets huérfanos que rompen el handshake
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None
        try:
            self.client = obs.ReqClient(host=host, port=port, password=password)
            self._refresh_canvas_size()
            return True, "Conexión exitosa"
        except Exception as e:
            self.client = None
            return False, str(e)

    def _refresh_canvas_size(self):
        """Consulta dimensiones del canvas de OBS. Fallback silencioso a 1920x1080."""
        try:
            settings = self.client.get_video_settings()
            self.canvas_width = int(getattr(settings, "base_width", 1920))
            self.canvas_height = int(getattr(settings, "base_height", 1080))
        except Exception:
            pass

    def disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client = None

    # --- FUNCIONES DEL ROTADOR ---
    def change_scene(self, scene_name):
        """Cambia la escena activa en OBS. Loguea el motivo si falla."""
        if not self.client:
            return False
        try:
            self.client.set_current_program_scene(scene_name)
            return True
        except Exception as e:
            log.warning("change_scene falló para %r: %s", scene_name, e)
            return False

    def create_scene_with_media(self, scene_name, media_input,
                                video_loop=True, video_restart_on_activate=True,
                                video_mute=False, video_volume_pct=100,
                                video_offset_seg=0):
        """Crea una escena genérica (Rotador) y le añade imagen, video o URL.

        Los parámetros de video solo aplican si el archivo es un video.
        Si video_offset_seg > 0, forzamos restart_on_activate=false para que
        el controller pueda gestionar el cursor manualmente sin carreras.
        """
        if not self.client:
            return False, "OBS no está conectado."

        try:
            self.client.create_scene(scene_name)
            media_input_lower = media_input.lower()
            source_name = f"{scene_name}_Contenido"
            is_video = False

            if media_input_lower.startswith(("http://", "https://")):
                input_kind = "browser_source"
                input_settings = {
                    "url": media_input, "width": 1920, "height": 1080, "fps": 30, "reroute_audio": True
                }
            else:
                clean_path = os.path.abspath(media_input).replace('\\', '/')
                if is_image_file(media_input):
                    input_kind = "image_source"
                    input_settings = {"file": clean_path}
                else:
                    is_video = True
                    input_kind = "ffmpeg_source"
                    input_settings = {
                        "local_file": clean_path,
                        "looping": bool(video_loop),
                        "restart_on_activate": (
                            False if video_offset_seg > 0 else bool(video_restart_on_activate)
                        ),
                    }

            self.client.create_input(scene_name, source_name, input_kind, input_settings, True)

            # Aplicar mute + volumen para videos (propiedades del input, no settings)
            if is_video:
                self._apply_audio(source_name, video_mute, video_volume_pct)

            return True, "Escena creada con éxito."
        except Exception as e:
            return False, f"Error creando escena en OBS: {str(e)}"

    def _apply_audio(self, input_name, muted, volume_pct):
        try:
            self.client.set_input_mute(input_name, bool(muted))
        except Exception as e:
            log.warning("set_input_mute falló para %s: %s", input_name, e)
        try:
            self.client.set_input_volume(input_name, vol_mul=max(0.0, min(1.0, float(volume_pct) / 100.0)))
        except Exception as e:
            log.warning("set_input_volume falló para %s: %s", input_name, e)

    def set_media_cursor(self, input_name, position_ms):
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.set_media_input_cursor(input_name, int(position_ms))
            return True, "Cursor movido."
        except Exception as e:
            return False, f"Error moviendo cursor: {str(e)}"

    def get_video_duration_ms(self, input_name):
        if not self.client:
            return None
        try:
            status = self.client.get_media_input_status(input_name)
            return int(getattr(status, "media_duration", 0)) or None
        except Exception:
            return None

    def patch_video_settings(self, input_name, loop, restart_on_activate, offset_seg):
        """Patch in-place de settings de video (loop, restart_on_activate)."""
        if not self.client:
            return False, "OBS no está conectado."
        try:
            delta = {
                "looping": bool(loop),
                "restart_on_activate": False if offset_seg > 0 else bool(restart_on_activate),
            }
            self.client.set_input_settings(input_name, delta, True)
            return True, "Video actualizado."
        except Exception as e:
            return False, f"Error actualizando video: {str(e)}"

    def set_input_audio(self, input_name, muted, volume_pct):
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self._apply_audio(input_name, muted, volume_pct)
            return True, "Audio actualizado."
        except Exception as e:
            return False, f"Error actualizando audio: {str(e)}"

    def create_web_scene(self, scene_name, url, width=1920, height=1080, fps=30,
                         reload_on_activate=False, keep_session=True, custom_css=None):
        """Crea una escena con browser_source configurable (dashboards, sitios live).

        keep_session=True mantiene el navegador vivo entre rotaciones (preserva login).
        reload_on_activate=True fuerza recarga cada vez que se activa la escena.
        custom_css se inyecta en la página cargada (ocultar sidebars, zoom, etc.).
        """
        if not self.client:
            return False, "OBS no está conectado."

        try:
            self.client.create_scene(scene_name)
            input_settings = {
                "url": url,
                "width": int(width),
                "height": int(height),
                "fps": int(fps),
                "reroute_audio": True,
                "restart_when_active": bool(reload_on_activate),
                "shutdown": not bool(keep_session),
            }
            if custom_css:
                input_settings["css"] = custom_css
            source_name = f"{scene_name}_Web"
            self.client.create_input(scene_name, source_name, "browser_source", input_settings, True)
            return True, "Escena web creada con éxito."
        except Exception as e:
            return False, f"Error creando escena web en OBS: {str(e)}"
        
    def delete_scene(self, scene_name):
        """Elimina una escena directamente de OBS."""
        if not self.client:
            return False, "OBS no está conectado."
        try:
            # Envía el comando a OBS para borrar la escena por su nombre
            self.client.remove_scene(scene_name)
            return True, "Escena eliminada de OBS."
        except Exception as e:
            return False, f"Error eliminando escena en OBS: {str(e)}"

    # --- EDICIÓN IN-PLACE ---
    def rename_scene(self, old_name, new_name):
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.set_scene_name(old_name, new_name)
            return True, "Escena renombrada."
        except Exception as e:
            return False, f"Error renombrando escena: {str(e)}"

    def rename_input(self, old_input_name, new_input_name):
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.set_input_name(old_input_name, new_input_name)
            return True, "Input renombrado."
        except Exception as e:
            return False, f"Error renombrando input: {str(e)}"

    def patch_input_settings(self, input_name, settings_delta):
        """Aplica solo los cambios pasados en settings_delta (overlay=True).

        Preserva el estado interno del input — clave para browser_source con sesión.
        """
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.set_input_settings(input_name, settings_delta, True)
            return True, "Input actualizado."
        except Exception as e:
            return False, f"Error actualizando input: {str(e)}"

    def remove_input(self, input_name):
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.remove_input(input_name)
            return True, "Input eliminado."
        except Exception as e:
            return False, f"Error eliminando input: {str(e)}"

    def add_file_input(self, scene_name, source_name, file_path,
                       video_loop=True, video_restart_on_activate=True,
                       video_mute=False, video_volume_pct=100, video_offset_seg=0):
        """Añade una imagen o video como input dentro de una escena existente."""
        if not self.client:
            return False, "OBS no está conectado."
        try:
            clean_path = os.path.abspath(file_path).replace('\\', '/')
            if is_image_file(file_path):
                input_kind = "image_source"
                input_settings = {"file": clean_path}
                is_video = False
            else:
                input_kind = "ffmpeg_source"
                input_settings = {
                    "local_file": clean_path,
                    "looping": bool(video_loop),
                    "restart_on_activate": (
                        False if video_offset_seg > 0 else bool(video_restart_on_activate)
                    ),
                }
                is_video = True
            self.client.create_input(scene_name, source_name, input_kind, input_settings, True)
            if is_video:
                self._apply_audio(source_name, video_mute, video_volume_pct)
            return True, "Input creado."
        except Exception as e:
            return False, f"Error creando input: {str(e)}"

    def get_source_screenshot_base64(self, source_name, width=160, height=90):
        """Devuelve el screenshot del source como string base64 (data URI stripped) o None.

        OBS soporta el source aunque no sea el activo, mientras esté renderizando
        (browser_source con shutdown=false, image/video ya cargados).
        """
        if not self.client:
            return None
        try:
            resp = self.client.get_source_screenshot(
                source_name, "jpeg", int(width), int(height), 60
            )
            img_data = getattr(resp, "image_data", None)
            if not img_data:
                return None
            # Formato de OBS: "data:image/jpeg;base64,<base64>"
            if img_data.startswith("data:"):
                return img_data.split(",", 1)[1]
            return img_data
        except Exception as e:
            log.debug("Screenshot falló para %s: %s", source_name, e)
            return None

    def list_input_names(self):
        """Devuelve un set con los nombres de todos los inputs de OBS, o None si falla."""
        if not self.client:
            return None
        try:
            resp = self.client.get_input_list()
            inputs = getattr(resp, "inputs", []) or []
            names = set()
            for item in inputs:
                # Cada item viene como dict con la clave 'inputName'
                if isinstance(item, dict):
                    n = item.get("inputName")
                    if n:
                        names.add(n)
            return names
        except Exception as e:
            log.warning("list_input_names falló: %s", e)
            return None

    def set_text_source_text(self, source_name, text):
        """Actualiza el texto de un text source (text_gdiplus_v3 / text_ft2_source_v2).

        Devuelve (ok, msg). No lanza excepciones — logea y sigue, para que un
        source inexistente no rompa el loop de sincronización de contadores.
        """
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.set_input_settings(source_name, {"text": str(text)}, True)
            return True, "OK"
        except Exception as e:
            log.warning("set_text_source_text falló para '%s': %s", source_name, e)
            return False, str(e)

    def refresh_browser_source(self, input_name):
        """Fuerza F5 sobre un browser_source. Preserva cookies/sesión."""
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.press_input_properties_button(input_name, "refreshnocache")
            return True, "Browser recargado."
        except Exception as e:
            return False, f"Error refrescando browser: {str(e)}"

    def set_source_transform(self, scene_name, source_name, zoom_pct, pan_x, pan_y):
        """Aplica zoom (%) y pan (offset desde el centro del canvas) a un source.

        - alignment=0 (centro): zoom mantiene el contenido centrado.
        - pan_x, pan_y: desplazamiento en píxeles desde el centro del canvas.
        - Preserva el estado interno del source (no destruye browser_source).
        """
        if not self.client:
            return False, "OBS no está conectado."
        try:
            response = self.client.get_scene_item_id(scene_name, source_name)
            item_id = response.scene_item_id
            scale = float(zoom_pct) / 100.0
            transform = {
                "alignment": 0,
                "scaleX": scale,
                "scaleY": scale,
                "positionX": float(self.canvas_width) / 2.0 + float(pan_x),
                "positionY": float(self.canvas_height) / 2.0 + float(pan_y),
            }
            self.client.set_scene_item_transform(scene_name, item_id, transform)
            return True, "Transform aplicado."
        except Exception as e:
            return False, f"Error aplicando transform: {str(e)}"

    def add_browser_input(self, scene_name, source_name, url, width, height, fps,
                          reload_on_activate, keep_session, custom_css=None):
        """Añade un browser_source dentro de una escena existente."""
        if not self.client:
            return False, "OBS no está conectado."
        try:
            input_settings = {
                "url": url,
                "width": int(width),
                "height": int(height),
                "fps": int(fps),
                "reroute_audio": True,
                "restart_when_active": bool(reload_on_activate),
                "shutdown": not bool(keep_session),
            }
            if custom_css:
                input_settings["css"] = custom_css
            self.client.create_input(scene_name, source_name, "browser_source", input_settings, True)
            return True, "Input web creado."
        except Exception as e:
            return False, f"Error creando input web: {str(e)}"

    # --- FUNCIONES DEL CALENDARIO ---
    def move_scene_item(self, scene_name, source_name, x, y, scale_pct=None):
        """Mueve un item a coordenadas X, Y.

        Si scale_pct viene, aplica scaleX = scaleY = scale_pct / 100. El
        alignment=5 (top-left) que ya deja build_calendar_scene mantiene el
        ancla al escalar, así que la posición no salta.
        """
        if not self.client:
            return False
        try:
            response = self.client.get_scene_item_id(scene_name, source_name)
            item_id = response.scene_item_id

            transform = {
                "positionX": float(x),
                "positionY": float(y),
            }
            if scale_pct is not None:
                s = float(scale_pct) / 100.0
                transform["scaleX"] = s
                transform["scaleY"] = s
            self.client.set_scene_item_transform(scene_name, item_id, transform)
            return True
        except Exception as e:
            log.error("move_scene_item falló en '%s/%s': %s", scene_name, source_name, e)
            return False

    def build_calendar_scene(self, scene_name, bg_path, source_path, source_name, x_space):
        """Construye el calendario con anclaje superior izquierdo y ancho auto-ajustado (275px)."""
        if not self.client:
            return False, "OBS no está conectado."
            
        try:
            self.client.create_scene(scene_name)
            
            clean_bg = os.path.abspath(bg_path).replace('\\', '/')
            clean_source = os.path.abspath(source_path).replace('\\', '/')
            
            self.client.create_input(scene_name, f"{scene_name}_Fondo", "image_source", {"file": clean_bg}, True)
            self.client.create_input(scene_name, source_name, "image_source", {"file": clean_source}, True)
            
            response = self.client.get_scene_item_id(scene_name, source_name)
            item_id = response.scene_item_id

            # Anclaje Top-Left (5)
            self.client.set_scene_item_transform(scene_name, item_id, {"alignment": 5})

            with Image.open(source_path) as img:
                orig_width, _ = img.size
            
            # Forzamos los 275px que mediste
            target_width = 275.0
            auto_scale = target_width / float(orig_width)
            
            self.client.set_scene_item_transform(scene_name, item_id, {
                "scaleX": auto_scale,
                "scaleY": auto_scale
            })
            
            return True, "Escena construida con éxito."

        except Exception as e:
            return False, f"Error: {str(e)}"

    # --- GRABACIÓN ---
    def start_recording(self):
        """Inicia la grabación en OBS. Devuelve (ok, msg)."""
        if not self.client:
            return False, "OBS no está conectado."
        try:
            self.client.start_record()
            return True, "Grabación iniciada."
        except Exception as e:
            log.warning("start_recording falló: %s", e)
            return False, str(e)

    def stop_recording(self):
        """Detiene la grabación. Devuelve (ok, output_path_or_error).

        Si OBS entrega output_path, se devuelve como mensaje para que la UI
        pueda mostrarlo y ofrecer 'Abrir carpeta'.
        """
        if not self.client:
            return False, "OBS no está conectado."
        try:
            resp = self.client.stop_record()
            output_path = getattr(resp, "output_path", "") or ""
            return True, output_path
        except Exception as e:
            log.warning("stop_recording falló: %s", e)
            return False, str(e)

    def get_recording_status(self):
        """Devuelve dict con estado de grabación o None si OBS no responde.

        Claves: active (bool), paused (bool), timecode (str "HH:MM:SS.mmm"),
        duration_ms (int).
        """
        if not self.client:
            return None
        try:
            resp = self.client.get_record_status()
            return {
                "active": bool(getattr(resp, "output_active", False)),
                "paused": bool(getattr(resp, "output_paused", False)),
                "timecode": getattr(resp, "output_timecode", "00:00:00.000") or "00:00:00.000",
                "duration_ms": int(getattr(resp, "output_duration", 0) or 0),
            }
        except Exception as e:
            log.debug("get_recording_status falló: %s", e)
            return None