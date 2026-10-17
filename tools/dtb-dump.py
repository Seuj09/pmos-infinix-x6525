#!/usr/bin/env python3
"""
Dump a .dtb as device-tree source, so it can be read without dtc.

This is a small, dependency-free FDT reader. It is not a replacement for dtc
(no phandle resolution, no /include handling), but it is enough to read values
out of a board DTB the bootloader hands over - which is the whole point.

Usage:
    python3 -I dtb-dump.py board.dtb > board.dts        # text
    python3 -I dtb-dump.py board.dtb -n lcd_td4160_hx -p sprd,initial-command -r
"""
import argparse
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_NOP, FDT_END = 1, 2, 3, 4, 9


def u32(blob, off):
    return struct.unpack_from(">I", blob, off)[0]


def read_strings(blob, off, size):
    return blob[off:off + size]


def decode(value):
    """Return a printable rendering of a property value."""
    if not value:
        return ""
    # A string property: printable text followed only by NUL padding.
    text, _, rest = value.partition(b"\0")
    if text and all(0x20 <= c < 0x7F for c in text) and not rest.strip(b"\0"):
        return f'"{text.decode()}"'
    # Short aligned values read best as u32 words (timings, flags).
    if len(value) % 4 == 0 and len(value) <= 32:
        words = struct.unpack(f">{len(value) // 4}I", value)
        return "<" + " ".join(f"0x{w:x}" for w in words) + ">"
    # Anything else (command tables) as a hex byte stream.
    return "[" + " ".join(f"{b:02x}" for b in value) + "]"


def iter_props(blob):
    """Yield (path_list, prop_name, value) for every property in the tree."""
    off_struct = u32(blob, 8)
    off_strings = u32(blob, 12)
    size_strings = u32(blob, 32) if len(blob) >= 36 else 0
    strings = read_strings(blob, off_strings, size_strings)
    pos, path = off_struct, []
    while True:
        token = u32(blob, pos)
        pos += 4
        if token == FDT_BEGIN_NODE:
            end = blob.index(b"\0", pos)
            name = blob[pos:end].decode(errors="replace")
            pos = (end + 4) & ~3
            path.append(name)
        elif token == FDT_END_NODE:
            path.pop()
        elif token == FDT_PROP:
            length = u32(blob, pos)
            nameoff = u32(blob, pos + 4)
            pos += 8
            value = blob[pos:pos + length]
            pos = (pos + length + 3) & ~3
            end = strings.index(b"\0", nameoff)
            yield list(path), strings[nameoff:end].decode(), value
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            return
        else:
            sys.exit(f"unknown FDT token {token} at offset {pos - 4}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dtb")
    ap.add_argument("-n", "--node", default=None,
                    help="with -p, match only nodes whose path contains this substring")
    ap.add_argument("-p", "--property", default=None,
                    help="print only this property name, one value per line")
    ap.add_argument("-r", "--raw", action="store_true",
                    help="with -p, print the value as one line of hex bytes")
    args = ap.parse_args()

    with open(args.dtb, "rb") as f:
        blob = f.read()
    if len(blob) < 40 or u32(blob, 0) != FDT_MAGIC:
        sys.exit("not a device tree blob (bad FDT magic)")

    if args.property:
        matches = []
        for path, name, value in iter_props(blob):
            full = "/" + "/".join(path)
            if name == args.property and (not args.node or args.node in full):
                matches.append((full, value))
        if not matches:
            sys.exit(f"no property {args.property!r} in this tree")
        if args.raw and len(matches) > 1:
            nodes = ", ".join(p for p, _ in matches)
            sys.exit(f"{args.property!r} matched {len(matches)} nodes ({nodes}); pass -n <node>")
        for full, value in matches:
            if args.raw:
                print(" ".join(f"{b:02x}" for b in value))
            else:
                print(f"{full}: {decode(value)}")
        return

    last = None
    for path, name, value in iter_props(blob):
        if path != last:
            indent = "\t" * (len(path) - 1)
            print(f"{indent}/{'/'.join(path)} {{")
            last = path
        print(f"\t{'    ' * (len(path) - 1)}{name} = {decode(value)};")


if __name__ == "__main__":
    main()
