"""Procesa un logo a color sobre fondo blanco → silueta blanca sobre
fondo transparente.

Utilidad reutilizable: cuando llega un asset corporativo nuevo como
JPG/PNG con fondo blanco (los PNG del design pack suelen venir con el
fondo del propio pack pintado), se le aplica este procesamiento para
obtener la silueta blanca lista para pegar sobre fondos oscuros
(sidebar, overlays, badges).

Como funciona:

- Para cada pixel calcula la luminosidad perceptual
  L = 0.299 R + 0.587 G + 0.114 B
- Setea alpha = 255 - L (blanco original → transparente;
  oscuro original → opaco).
- Setea color = (255, 255, 255) siempre.

El resultado preserva el anti-aliasing de los bordes originales via
el alpha gradual — no quedan "escalones" en los contornos.

Uso:

    python scripts/logo_a_blanco_transparente.py <input> [--output <path>]

Si --output no se da, el archivo de salida se nombra
`<base>_blanco_transparent.png` en el mismo directorio del input.

Ejemplos reales (ya usados en el rediseno UI):

    python scripts/logo_a_blanco_transparente.py \\
        "assets/CP_RGB_p_VerAlt (1).jpg"
    # Genera assets/CP_RGB_p_VerAlt (1)_blanco_transparent.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def convertir(input_path: Path, output_path: Path) -> None:
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow no esta instalado. Ejecuta: pip install Pillow",
              file=sys.stderr)
        sys.exit(2)

    if not input_path.exists():
        print(f"ERROR: no existe {input_path}", file=sys.stderr)
        sys.exit(1)

    src = Image.open(input_path).convert("RGB")
    w, h = src.size
    dst = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    src_px = src.load()
    dst_px = dst.load()

    for y in range(h):
        for x in range(w):
            r, g, b = src_px[x, y]
            L = int(0.299 * r + 0.587 * g + 0.114 * b)
            alpha = 255 - L
            dst_px[x, y] = (255, 255, 255, alpha)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dst.save(output_path, "PNG")

    # Verificar corners
    v = Image.open(output_path).load()
    corners = [v[0, 0], v[w - 1, 0], v[0, h - 1], v[w - 1, h - 1]]
    print(f"OK → {output_path} ({w}x{h})")
    print(f"   corners alpha: {[c[3] for c in corners]} "
          f"(0 = transparente, se espera todos 0 si el input tiene "
          f"fondo blanco limpio)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="Ruta al JPG/PNG con fondo blanco")
    p.add_argument(
        "--output", "-o",
        help="Ruta del PNG de salida. Default: "
             "<input>_blanco_transparent.png",
    )
    args = p.parse_args()

    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = (
            input_path.parent
            / f"{input_path.stem}_blanco_transparent.png"
        )

    convertir(input_path, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
