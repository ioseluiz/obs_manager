"""Tests headless para core/udp_url_params.py.

Verifica el round-trip URL <-> campos TTL/pkt_size del CanalEditDialog.
No requiere PyQt, OBS ni BD.

Uso:
    venv\\Scripts\\python.exe scripts\\test_udp_url_params.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.udp_url_params import compose_url, extract_multicast_params


_failures: list[str] = []


def _check(cond: bool, label: str) -> None:
    status = "OK " if cond else "FAIL"
    print(f"  [{status}] {label}")
    if not cond:
        _failures.append(label)


# ---------------------------------------------------------------------
# extract_multicast_params
# ---------------------------------------------------------------------

print("extract_multicast_params:")

base, ttl, pkt = extract_multicast_params("")
_check((base, ttl, pkt) == ("", "", ""), "URL vacia -> todo vacio")

base, ttl, pkt = extract_multicast_params("udp://230.2.1.36:8000")
_check(base == "udp://230.2.1.36:8000" and ttl == "" and pkt == "",
       "URL sin query -> base igual, params vacios")

base, ttl, pkt = extract_multicast_params("udp://230.2.1.36:8000?ttl=32")
_check(base == "udp://230.2.1.36:8000" and ttl == "32" and pkt == "",
       "URL con solo ttl -> extrae ttl")

base, ttl, pkt = extract_multicast_params("udp://230.2.1.36:8000?pkt_size=1316")
_check(base == "udp://230.2.1.36:8000" and ttl == "" and pkt == "1316",
       "URL con solo pkt_size -> extrae pkt_size")

base, ttl, pkt = extract_multicast_params(
    "udp://230.2.1.36:8000?ttl=32&pkt_size=1316"
)
_check(base == "udp://230.2.1.36:8000" and ttl == "32" and pkt == "1316",
       "URL con ttl y pkt_size -> extrae ambos, base limpia")

# Preservar otros query params ajenos.
base, ttl, pkt = extract_multicast_params(
    "udp://230.2.1.36:8000?fifo_size=100&ttl=32"
)
_check(base == "udp://230.2.1.36:8000?fifo_size=100" and ttl == "32" and pkt == "",
       "query params ajenos se preservan en base")

# Orden distinto.
base, ttl, pkt = extract_multicast_params(
    "udp://230.2.1.36:8000?pkt_size=1316&ttl=32"
)
_check(base == "udp://230.2.1.36:8000" and ttl == "32" and pkt == "1316",
       "orden pkt_size,ttl -> extrae ambos")

# Case-insensitive para los keys.
base, ttl, pkt = extract_multicast_params(
    "udp://230.2.1.36:8000?TTL=64&PKT_SIZE=1500"
)
_check(ttl == "64" and pkt == "1500",
       "keys en mayusculas -> extrae igual")


# ---------------------------------------------------------------------
# compose_url
# ---------------------------------------------------------------------

print("\ncompose_url:")

_check(compose_url("") == "", "base vacia -> ''")

_check(compose_url("udp://230.2.1.36:8000", "", "") == "udp://230.2.1.36:8000",
       "base sin params -> igual")

_check(compose_url("udp://230.2.1.36:8000", "32", "") ==
       "udp://230.2.1.36:8000?ttl=32",
       "solo ttl -> agrega ttl")

_check(compose_url("udp://230.2.1.36:8000", "", "1316") ==
       "udp://230.2.1.36:8000?pkt_size=1316",
       "solo pkt_size -> agrega pkt_size")

_check(compose_url("udp://230.2.1.36:8000", "32", "1316") ==
       "udp://230.2.1.36:8000?ttl=32&pkt_size=1316",
       "ambos -> agrega ambos en orden ttl,pkt_size")

# Valor "0" = no agregar.
_check(compose_url("udp://230.2.1.36:8000", "0", "0") ==
       "udp://230.2.1.36:8000",
       "ttl=0, pkt_size=0 -> no agrega nada")

_check(compose_url("udp://230.2.1.36:8000", "0", "1316") ==
       "udp://230.2.1.36:8000?pkt_size=1316",
       "ttl=0, pkt_size=1316 -> solo pkt_size")

# Sobre-escribir params existentes en la base (no duplicar).
_check(compose_url("udp://230.2.1.36:8000?ttl=5", "32", "") ==
       "udp://230.2.1.36:8000?ttl=32",
       "sobre-escribe ttl existente en base")

_check(compose_url("udp://230.2.1.36:8000?ttl=5&pkt_size=100", "32", "1316") ==
       "udp://230.2.1.36:8000?ttl=32&pkt_size=1316",
       "sobre-escribe ambos existentes en base")

# Otros query params preservados.
result = compose_url("udp://230.2.1.36:8000?fifo_size=100", "32", "1316")
_check("fifo_size=100" in result and "ttl=32" in result and "pkt_size=1316" in result,
       "preserva query ajenos al agregar ttl+pkt_size")


# ---------------------------------------------------------------------
# Round-trip extract -> compose -> extract
# ---------------------------------------------------------------------

print("\nround-trip:")

original = "udp://230.2.1.36:8000?ttl=32&pkt_size=1316"
base, ttl, pkt = extract_multicast_params(original)
rebuilt = compose_url(base, ttl, pkt)
_check(rebuilt == original, f"idempotente: {original} -> {rebuilt}")

original = "udp://230.2.1.36:8000"
base, ttl, pkt = extract_multicast_params(original)
rebuilt = compose_url(base, ttl, pkt)
_check(rebuilt == original, f"idempotente sin params: {original} -> {rebuilt}")

original = "udp://230.2.1.36:8000?fifo_size=100&ttl=32"
base, ttl, pkt = extract_multicast_params(original)
rebuilt = compose_url(base, ttl, pkt)
_check("fifo_size=100" in rebuilt and "ttl=32" in rebuilt,
       f"preserva fifo_size en round-trip: {original} -> {rebuilt}")


# ---------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------

print(f"\n{'=' * 50}")
if _failures:
    print(f"FAIL -- {len(_failures)} test(s) fallaron:")
    for f in _failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("OK -- todos los tests pasaron.")
    sys.exit(0)
