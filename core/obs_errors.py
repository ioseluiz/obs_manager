"""Traducción de errores del cliente OBS WebSocket a mensajes accionables.

Se llama desde:
- OBSProbeWorker (botón "Probar conexión" en el diálogo de Ajustes).
- MainController._show_connection_error (diálogo de error al conectar).

Deja la excepción cruda en los logs; sólo traduce lo que se le muestra al usuario.
"""
from __future__ import annotations


_LOCAL_HOSTS = ("", "localhost", "127.0.0.1", "::1", "[::1]")


def _is_local(host: str) -> bool:
    return (host or "").strip().lower() in _LOCAL_HOSTS


def friendly_error(raw: str, host: str = "", port=None) -> str:
    """Traduce la excepción cruda a un mensaje con causa probable y siguiente paso.

    Devuelve el mensaje original como fallback si no reconoce el patrón.
    """
    raw = raw or ""
    low = raw.lower()
    host_txt = (host or "").strip()
    port_txt = str(port) if port else "4455"
    is_local = _is_local(host_txt)
    target = "OBS local" if is_local else f"{host_txt}:{port_txt}"

    # --- Timeout: SYN sin respuesta. Típicamente firewall haciendo DROP silencioso. ---
    if "timed out" in low or "timeouterror" in low:
        if is_local:
            return (
                "Timeout conectando a OBS local.\n"
                "¿OBS Studio está corriendo y con WebSocket habilitado "
                "(Herramientas → WebSocket Server Settings)?"
            )
        return (
            f"Timeout: {target} no respondió.\n\n"
            "Causa más probable: el firewall del equipo con OBS está bloqueando el puerto, "
            "o el equipo no es alcanzable en la red.\n\n"
            "Diagnóstico rápido (PowerShell en este equipo):\n"
            f"  Test-NetConnection -ComputerName {host_txt} -Port {port_txt}\n"
            "  • Si TcpTestSucceeded : False → abrir el puerto en el firewall del equipo con OBS.\n"
            "  • Si PingSucceeded : False → verificar IP o red / VLAN."
        )

    # --- Conexión activamente rechazada (RST). El puerto está cerrado o OBS no escucha. ---
    if "10061" in raw or "actively refused" in low or "connectionrefusederror" in low:
        if is_local:
            return (
                "OBS local no está aceptando conexiones en ese puerto.\n"
                "Abrir OBS Studio y habilitar WebSocket "
                "(Herramientas → WebSocket Server Settings)."
            )
        return (
            f"{target} respondió pero rechazó la conexión.\n\n"
            "Causa más probable: OBS no está abierto en el equipo remoto, o WebSocket "
            "no está habilitado, o el puerto configurado en OBS no coincide con el que "
            "tiene esta app.\n\n"
            "Verificar en el equipo remoto (PowerShell):\n"
            f"  netstat -an | Select-String \"{port_txt}\"\n"
            f"  Debe aparecer una línea:  TCP 0.0.0.0:{port_txt} ... LISTENING"
        )

    # --- DNS fail / host inválido ---
    if "gaierror" in low or "getaddrinfo failed" in low or "name or service not known" in low:
        return (
            f"No se pudo resolver el host «{host_txt or '?'}».\n"
            "Verificar que la IP o nombre sean correctos."
        )

    # --- Autenticación (obsws-python lanza OBSSDKError con mensaje que contiene 'auth') ---
    if ("authentication" in low or "authenticate" in low
            or ("auth" in low and ("fail" in low or "invalid" in low))
            or "password" in low):
        return (
            "Autenticación fallida.\n"
            "La contraseña no coincide con la configurada en OBS "
            "(Herramientas → WebSocket Server Settings)."
        )

    # --- Handshake fallido: TCP abrió pero no era un WebSocket ---
    if ("handshake" in low or "bad status" in low
            or "invalid" in low and "response" in low):
        return (
            f"Handshake WebSocket fallido con {target}.\n"
            "El puerto está abierto pero la respuesta no es de un servidor WebSocket. "
            "Confirmar que el puerto configurado en OBS coincide con el de esta app."
        )

    # --- Red / socket genérico ---
    if "network is unreachable" in low or "10051" in raw:
        return (
            f"Red inalcanzable hacia {target}.\n"
            "Verificar conectividad de red / VLAN entre los dos equipos."
        )

    # Fallback: dejar el mensaje original.
    return raw
