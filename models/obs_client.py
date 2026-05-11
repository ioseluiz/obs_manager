import obsws_python as obs
import os
from PIL import Image

class OBSClient:
    def __init__(self):
        self.client = None

    def connect(self, host="localhost", port=4455, password=""):
        try:
            self.client = obs.ReqClient(host=host, port=port, password=password)
            return True, "Conexión exitosa"
        except Exception as e:
            self.client = None
            return False, str(e)

    def disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client = None

    # --- FUNCIONES DEL ROTADOR ---
    def change_scene(self, scene_name):
        """Cambia la escena activa en OBS."""
        if not self.client: return False
        try:
            self.client.set_current_program_scene(scene_name)
            return True
        except: return False

    def create_scene_with_media(self, scene_name, media_input):
        """Crea una escena genérica (Rotador) y le añade imagen, video o URL."""
        if not self.client:
            return False, "OBS no está conectado."
            
        try:
            self.client.create_scene(scene_name)
            media_input_lower = media_input.lower()
            
            if media_input_lower.startswith(("http://", "https://")):
                input_kind = "browser_source"
                input_settings = {
                    "url": media_input, "width": 1920, "height": 1080, "fps": 30, "reroute_audio": True 
                }
            else:
                clean_path = os.path.abspath(media_input).replace('\\', '/')
                if media_input_lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    input_kind = "image_source"
                    input_settings = {"file": clean_path}
                else:
                    input_kind = "ffmpeg_source"
                    input_settings = {"local_file": clean_path, "looping": True}
                
            source_name = f"{scene_name}_Contenido"
            self.client.create_input(scene_name, source_name, input_kind, input_settings, True)
            return True, "Escena creada con éxito."
        except Exception as e:
            return False, f"Error creando escena en OBS: {str(e)}"
        
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

    # --- FUNCIONES DEL CALENDARIO ---
    def move_scene_item(self, scene_name, source_name, x, y):
        """Mueve un item a coordenadas X, Y. Respeta la escala."""
        if not self.client: return False
        try:
            response = self.client.get_scene_item_id(scene_name, source_name)
            item_id = response.scene_item_id
            
            transform = {
                "positionX": float(x),
                "positionY": float(y)
            }
            self.client.set_scene_item_transform(scene_name, item_id, transform)
            return True
        except Exception as e:
            print(f"Error moviendo fuente '{source_name}': {e}")
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