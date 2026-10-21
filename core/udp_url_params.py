"""Helpers puros para gestionar los query params `ttl` y `pkt_size`
dentro del campo `url_destino` de un canal multi-salida.

Convencion:
- La URL de un canal puede incluir query params multicast estandar como
  `?ttl=32&pkt_size=1316`. Esos params los consume el FFmpeg interno del
  plugin Source Record y son casi obligatorios cuando `url_destino` es
  multicast cross-subnet.
- La UI (CanalEditDialog) expone esos dos valores como campos separados
  para que el operador no tenga que recordar la sintaxis exacta. La BD
  sigue guardando TODO en el mismo campo `url_destino` -- zero cambios
  de schema. Estos helpers hacen el round-trip URL <-> campos.
- Otros query params (ej. `?fifo_size=X`, `?localaddr=Y`) se PRESERVAN
  intactos en la URL base. Solo `ttl` y `pkt_size` se manejan explicito.

Modulo puro: sin PyQt, sin OBS, sin BD. Solo stdlib.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


_MANAGED_KEYS = ("ttl", "pkt_size")


def extract_multicast_params(url: str) -> tuple[str, str, str]:
    """Separa la URL en (base, ttl, pkt_size).

    - `base`: URL sin los params `ttl`/`pkt_size`. Otros query params se
      preservan (ej. `?fifo_size=X` queda en la base).
    - `ttl`, `pkt_size`: strings con el valor o "" si no estan.

    Si la URL es malformada, devuelve la original como base y params
    vacios -- no lanza.
    """
    if not url:
        return "", "", ""
    try:
        parts = urlsplit(url)
    except Exception:
        return url, "", ""

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    ttl = ""
    pkt_size = ""
    remaining: list[tuple[str, str]] = []
    for k, v in pairs:
        kl = k.lower()
        if kl == "ttl":
            ttl = v
        elif kl == "pkt_size":
            pkt_size = v
        else:
            remaining.append((k, v))

    new_query = urlencode(remaining) if remaining else ""
    base = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )
    return base, ttl, pkt_size


def compose_url(base: str, ttl: str = "", pkt_size: str = "") -> str:
    """Reconstruye la URL agregando/reemplazando `ttl` y `pkt_size`.

    - Valores vacios o "0" se tratan como "no agregar".
    - Si la URL base ya contiene `ttl`/`pkt_size` en query, se reemplazan
      por los nuevos (nunca duplicados).
    - Otros query params en la base se preservan.

    Si la URL es malformada, devuelve la base original -- no lanza.
    """
    if not base:
        return ""
    try:
        parts = urlsplit(base)
    except Exception:
        return base

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    filtered = [(k, v) for k, v in pairs if k.lower() not in _MANAGED_KEYS]

    ttl_s = (ttl or "").strip()
    pkt_s = (pkt_size or "").strip()
    if ttl_s and ttl_s != "0":
        filtered.append(("ttl", ttl_s))
    if pkt_s and pkt_s != "0":
        filtered.append(("pkt_size", pkt_s))

    new_query = urlencode(filtered) if filtered else ""
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )
