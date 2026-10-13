#!/usr/bin/env python3
"""
Convert a Spreadtrum panel init sequence ("sprd,initial-command" array from a
downstream lcd/*.dtsi, or the same array decompiled out of the dtbo the
bootloader hands over) into mainline mipi_dsi_dcs_write_seq_multi() calls.

Usage:
    python3 -I lcd-dtsi-to-c.py < file.dtsi
    dtc -I dtb -O dts board.dtb | python3 -I lcd-dtsi-to-c.py

Each array line is a DSI packet: <data-type> <vc> <ack> <len> <payload...>
    29 -> DCS long write        (payload = cmd + params)
    05 -> DCS short write, 1 param
    15 -> DCS short write, no param
    13 -> generic short write, no param
Anything else is emitted as a comment for manual handling, as are lines that
look like delays (the vendor encodes some waits in the sequence and some as
separate properties - check both).

Delays are NOT reconstructed: read them off the original node
(sprd,sleep-*-command / explicit msleep notes) and insert mipi_dsi_msleep().
"""
import re
import sys

LINE = re.compile(r"^\s*([0-9a-fA-F]{2}(?:\s+[0-9a-fA-F]{2})*)\s*$")


def emit(payload: list[int]) -> str:
    b = ", ".join(f"0x{x:02x}" for x in payload)
    return f"\tmipi_dsi_dcs_write_seq_multi(&dsi_ctx, {b});"


def main() -> None:
    started = False
    for raw in sys.stdin:
        line = raw.split("#")[0].strip()
        if "initial-command" in line:
            started = True
            continue
        if not started:
            continue
        if line.startswith("]"):
            break
        m = LINE.match(line)
        if not m:
            continue
        data = [int(x, 16) for x in m.group(1).split()]
        if len(data) < 4:
            print(f"\t/* short packet, check by hand: {' '.join(m.group(1).split())} */")
            continue
        dtype, _vc, _ack, length = data[0], data[1], data[2], data[3]
        payload = data[4:]
        if length != len(payload):
            print(
                f"\t/* length says {length} but {len(payload)} bytes follow - check by hand */"
            )
        if dtype == 0x29 or dtype == 0x05:
            print(emit(payload))
        elif dtype in (0x15, 0x13):
            print(emit(payload[:1]))
        else:
            print(f"\t/* data type 0x{dtype:02x}, handle by hand: {payload} */")


if __name__ == "__main__":
    main()
