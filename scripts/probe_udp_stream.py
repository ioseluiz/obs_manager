"""Captura N segundos del UDP y diagnostica si es un stream MPEG-TS válido.

Uso::

    venv\\Scripts\\python.exe scripts\\probe_udp_stream.py 9001

Escucha UDP en `0.0.0.0:<puerto>`, captura 5 segundos, y reporta:
- Bytes totales + paquetes recibidos.
- Si el stream es MPEG-TS (los packets TS empiezan con byte 0x47 cada 188).
- Si hay evidencia de video H.264 (NAL start codes: 00 00 00 01 o 00 00 01).
- Si aparecen keyframes (NAL unit type 5 = IDR, o 7 = SPS, 8 = PPS).

No depende de ffplay/VLC — sólo Python stdlib.
"""
from __future__ import annotations

import socket
import sys
import time
from collections import Counter


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/probe_udp_stream.py <puerto>  (ej: 9001)")

    port = int(sys.argv[1])
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"Escuchando UDP en 0.0.0.0:{port} durante {duration} segundos...")
    print(f"IMPORTANTE: el canal debe estar transmitiendo (▶ Transmitir + ▶ Play).\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
    except OSError:
        pass
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)

    buffer = bytearray()
    packets = 0
    start = time.time()
    deadline = start + duration
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        packets += 1
        buffer.extend(data)

    sock.close()
    total_bytes = len(buffer)
    elapsed = time.time() - start

    # Guardar captura a archivo .ts para reproducción posterior con VLC.
    # Si el .ts se ve bien como archivo local, el problema del "VLC negro"
    # en modo UDP es de red / detección de container, no del stream mismo.
    if total_bytes > 0:
        import pathlib
        out_path = pathlib.Path(f"capture_udp_{port}.ts").resolve()
        out_path.write_bytes(bytes(buffer))
        print(f"  💾 Captura guardada en: {out_path}")
        print(f"     Abrir con VLC: doble click sobre el archivo, o")
        print(f"     'vlc \"{out_path}\"' desde terminal.\n")

    print("=" * 70)
    print(f"RESULTADO — {elapsed:.1f}s escuchados")
    print("=" * 70)
    print(f"  Bytes totales:      {total_bytes:,}")
    print(f"  Paquetes UDP:       {packets:,}")
    if total_bytes == 0:
        print("\n  ❌ NADA llegó. Verificá:")
        print("     - Canal transmitiendo en la app (▶ Transmitir prendido)")
        print("     - URL destino del canal = udp://127.0.0.1:9001")
        print("     - Puerto correcto en el comando (arg 1)")
        sys.exit(1)
    bps = total_bytes * 8 / elapsed / 1000
    print(f"  Bitrate promedio:   {bps:,.0f} kbps")

    # ==== Test 1: es MPEG-TS? ====
    # Los packets TS son 188 bytes cada uno empezando con 0x47.
    # Si encontramos 0x47 en offsets múltiplos de 188 consistentemente, es TS.
    print()
    print("=" * 70)
    print("TEST 1: ¿Es MPEG-TS?")
    print("=" * 70)
    ts_hits = 0
    ts_probes = min(100, total_bytes // 188)
    for i in range(ts_probes):
        if buffer[i * 188] == 0x47:
            ts_hits += 1
    ts_ratio = ts_hits / ts_probes if ts_probes else 0
    if ts_ratio > 0.9:
        print(f"  ✓ SÍ — {ts_hits}/{ts_probes} packets empiezan con 0x47 "
              f"({ts_ratio*100:.0f}%). Stream es MPEG-TS.")
        is_ts = True
    elif ts_ratio > 0.3:
        print(f"  ⚠ PARCIAL — {ts_hits}/{ts_probes} ({ts_ratio*100:.0f}%). "
              f"Alineamiento raro. Puede ser TS con desfase por UDP header.")
        is_ts = True
    else:
        print(f"  ✗ NO — {ts_hits}/{ts_probes} ({ts_ratio*100:.0f}%). "
              f"El stream NO parece MPEG-TS.")
        # Probemos con offset variable (por si hay header extra)
        for offset in range(4, 12):
            hits = sum(1 for i in range(min(50, (total_bytes - offset) // 188))
                       if buffer[offset + i * 188] == 0x47)
            if hits > 40:
                print(f"     Pero con offset={offset}, {hits}/50 packets "
                      f"alineados. Podría haber header extra.")
        is_ts = False

    # ==== Test 2: hay NAL units H.264? ====
    print()
    print("=" * 70)
    print("TEST 2: ¿Hay video H.264? (buscar NAL start codes)")
    print("=" * 70)
    # NAL start codes: 00 00 00 01 o 00 00 01
    nal_count_4 = buffer.count(b"\x00\x00\x00\x01")
    nal_count_3 = buffer.count(b"\x00\x00\x01") - nal_count_4  # sin contar los 4-byte
    total_nals = nal_count_4 + nal_count_3
    print(f"  NAL start codes (4-byte): {nal_count_4:,}")
    print(f"  NAL start codes (3-byte): {nal_count_3:,}")
    print(f"  Total NAL units:          {total_nals:,}")
    if total_nals == 0:
        print("  ✗ NO hay NAL start codes. El stream NO contiene H.264 crudo.")
        print("     (Puede ser problema del encoder — no está emitiendo frames)")
    else:
        print(f"  ✓ Hay NAL units — el encoder ESTÁ produciendo H.264.")

    # ==== Test 3: hay keyframes / SPS / PPS? ====
    if total_nals > 0:
        print()
        print("=" * 70)
        print("TEST 3: ¿Hay keyframes / SPS / PPS?")
        print("=" * 70)
        # Después de un start code, el siguiente byte tiene el NAL type en los
        # bits 0-4 (mask 0x1F): 5=IDR (keyframe), 7=SPS, 8=PPS, 1=non-IDR slice.
        types = Counter()
        # Buscar sistemáticamente
        i = 0
        found = 0
        while i < len(buffer) - 5 and found < 5000:
            # Match 3-byte o 4-byte start code
            if buffer[i:i+4] == b"\x00\x00\x00\x01":
                nal_type = buffer[i+4] & 0x1F
                types[nal_type] += 1
                found += 1
                i += 4
            elif buffer[i:i+3] == b"\x00\x00\x01":
                nal_type = buffer[i+3] & 0x1F
                types[nal_type] += 1
                found += 1
                i += 3
            else:
                i += 1
        print(f"  NAL types encontrados (top {len(types)}):")
        type_names = {
            1: "P/B slice (non-IDR)",
            5: "IDR slice (KEYFRAME)",
            6: "SEI",
            7: "SPS",
            8: "PPS",
            9: "AUD (access unit delim)",
        }
        for t, count in sorted(types.items()):
            name = type_names.get(t, f"tipo {t}")
            marker = " ⭐" if t == 5 else ""
            print(f"    {t:>3}: {count:>6}  ({name}){marker}")
        keyframes = types.get(5, 0)
        sps = types.get(7, 0)
        pps = types.get(8, 0)
        print()
        if keyframes > 0:
            print(f"  ✓ Hay {keyframes} keyframes (IDR) — el video ES decodable.")
        else:
            print(f"  ✗ NO hay keyframes (IDR). Sin ellos, ningún reproductor")
            print(f"     puede arrancar el decode. Problema serio del encoder.")
        if sps > 0 and pps > 0:
            print(f"  ✓ SPS ({sps}) y PPS ({pps}) presentes — headers OK.")
        else:
            print(f"  ⚠ SPS={sps}, PPS={pps}. Sin ambos, el decoder no puede")
            print(f"     inicializarse.")

    # ==== Veredicto ====
    print()
    print("=" * 70)
    print("VEREDICTO")
    print("=" * 70)
    if is_ts and total_nals > 0 and types.get(5, 0) > 0:
        print("  El stream ES MPEG-TS con H.264 y keyframes válidos.")
        print("  Si VLC ve negro con esto, el problema es del reproductor")
        print("  o de detección de formato. Probar:")
        print("    - VLC → Media → Open Network Stream → udp://@:{}".format(port))
        print("    - Cambiar URL del canal a udp://127.0.0.1:{}?pkt_size=1316".format(port))
    elif is_ts and total_nals == 0:
        print("  Stream es MPEG-TS pero SIN video H.264 crudo dentro.")
        print("  El encoder no está emitiendo NAL units. Problema del encoder.")
        print("  Sugerencia: cambiar 'encoder' de 'x264' a 'qsv' en el canal.")
    elif not is_ts:
        print("  Stream NO es MPEG-TS reconocible.")
        print("  Falta el muxer/container en la config del filtro.")
        print("  Requiere agregar settings de encapsulación en core/output_adapter.")


if __name__ == "__main__":
    main()
