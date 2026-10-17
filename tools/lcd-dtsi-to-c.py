#!/usr/bin/env python3
"""
Convert a Spreadtrum panel init sequence into mainline mipi_dsi_* calls.

Two input forms are supported.

  --lines (default): the `sprd,initial-command = [ ... ];` array as it appears in
  a downstream lcd/*.dtsi, one DSI packet per source line.

  --stream: the same data as a flat byte stream, which is how it comes out of a
  decompiled board DTB, e.g.

      python3 -I dtb-dump.py board.dtb -n lcd_td4160_hx -p sprd,initial-command -r \
          | python3 -I lcd-dtsi-to-c.py --stream

  Both use the same packet layout: [data type][vc][ack][len][payload x len].
  One vendor quirk has to be handled: for `--stream`, packets with data type
  0x13 carry a *delay in milliseconds in the vc byte* and then a command in the
  payload, which is how the sleep-out/sleep-in timing is stored (e.g.
  `13 78 00 01 11` = wait 120 ms, then DCS 0x11).

Delays are otherwise not reconstructed - check the original node for explicit
waits and insert mipi_dsi_msleep() where needed.
"""
import argparse
import re
import sys

LINE = re.compile(r"^\s*([0-9a-fA-F]{2}(?:\s+[0-9a-fA-F]{2})*)\s*$")

LONG_WRITE_DCS = {0x39, 0x23}
LONG_WRITE_GENERIC = {0x29}
SHORT_WRITE_DCS = {0x05, 0x15}
SHORT_WRITE_GENERIC = {0x03}
DELAY_OPCODE = 0x13


def fmt(payload):
    return ", ".join(f"0x{b:02x}" for b in payload)


def emit(payload, comment=""):
    if not payload:
        return
    tail = f"\t/* {comment} */" if comment else ""
    print(f"\tmipi_dsi_dcs_write_seq_multi(&dsi_ctx, {fmt(payload)});{tail}")


def emit_packet(dt, vc, payload, index):
    if dt in LONG_WRITE_DCS or dt in SHORT_WRITE_DCS or dt == DELAY_OPCODE:
        emit(payload)
    elif dt in LONG_WRITE_GENERIC or dt in SHORT_WRITE_GENERIC:
        print(f"\tmipi_dsi_generic_write_seq_multi(&dsi_ctx, {fmt(payload)});")
    else:
        print(f"\t/* packet {index}: data type 0x{dt:02x}, handle by hand: {fmt(payload)} */")


def do_stream(tokens):
    i = idx = 0
    delays = 0
    while i + 3 < len(tokens):
        dt, vc, _ack, length = tokens[i:i + 4]
        i += 4
        if i + length > len(tokens):
            print(f"\t/* truncated packet at byte {i - 4}: {fmt(tokens[i - 4:])} */")
            break
        payload = tokens[i:i + length]
        i += length
        idx += 1
        if dt == DELAY_OPCODE:
            if vc:
                print(f"\tmipi_dsi_msleep(&dsi_ctx, {vc});\t/* vendor delay */")
                delays += 1
            emit(payload, f"opcode 0x13, delay {vc}ms")
        else:
            emit_packet(dt, vc, payload, idx)
    print(f"/* {idx} packets, {delays} delays, {len(tokens)} bytes */", file=sys.stderr)


def do_lines():
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
        dt, vc, _ack, length = data[0], data[1], data[2], data[3]
        payload = data[4:]
        if length != len(payload):
            print(f"\t/* length says {length} but {len(payload)} bytes follow */")
        if dt == DELAY_OPCODE:
            if vc:
                print(f"\tmipi_dsi_msleep(&dsi_ctx, {vc});\t/* vendor delay */")
            emit(payload, f"opcode 0x13, delay {vc}ms")
        else:
            emit_packet(dt, vc, payload, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", action="store_true",
                    help="read a flat hex byte stream instead of a dtsi array")
    args = ap.parse_args()

    if args.stream:
        lines = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
        if len(lines) > 1:
            sys.exit(f"--stream expected 1 line, got {len(lines)} (did dtb-dump match multiple panel nodes?)")
        tokens = [int(t, 16) for t in (lines[0].split() if lines else [])]
        do_stream(tokens)
    else:
        do_lines()


if __name__ == "__main__":
    main()
