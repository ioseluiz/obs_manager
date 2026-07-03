"""Presets de escenas para acelerar la creación de casos comunes.

Cada template es un dict con overrides sobre los defaults del formulario. Solo
las claves presentes se aplican; el resto queda con lo que el usuario haya tipeado.
"""

_POWERBI_CSS = """/* Ocultar sidebars y navbar de Power BI */
.navbar-container, .quickAccessToolbar, .navPaneContainer,
.sidebar, .navBar { display: none !important; }
body { background: transparent; margin: 0; overflow: hidden; }
::-webkit-scrollbar { display: none; }"""


TEMPLATES = {
    "Sin template": {
        # No overrides — usa los valores por defecto de la vista.
    },
    "🌐 Dashboard Power BI Corporativo": {
        "tipo": "url",
        "duration": 60,
        "ancho": 1920,
        "alto": 1080,
        "fps": 30,
        "keep_session": True,
        "reload_on_activate": False,
        "refresh_interval_seg": 300,  # cada 5 min
        "custom_css": _POWERBI_CSS,
    },
    "📊 Grafana / Monitoreo Live": {
        "tipo": "url",
        "duration": 30,
        "ancho": 1920,
        "alto": 1080,
        "fps": 30,
        "keep_session": False,
        "reload_on_activate": False,
        "refresh_interval_seg": 60,
    },
    "🌍 Sitio Público / Landing": {
        "tipo": "url",
        "duration": 20,
        "ancho": 1920,
        "alto": 1080,
        "fps": 30,
        "keep_session": False,
        "reload_on_activate": True,
        "refresh_interval_seg": 0,
    },
    "🎬 Video Corporativo Silencioso": {
        "tipo": "file",
        "duration": 30,
        "video_loop": True,
        "video_restart_on_activate": True,
        "video_mute": True,
        "video_volume_pct": 0,
    },
    "🖼 Imagen Estática 20s": {
        "tipo": "file",
        "duration": 20,
    },
}


def get_template_names():
    return list(TEMPLATES.keys())


def get_template_defaults(name):
    return TEMPLATES.get(name, {})
