#!/usr/bin/env python3
"""
Print a device tree that the kernel has already expanded under /proc/device-tree.

These are the properties the *running* kernel was handed, so they beat anything
read out of a dtbo: no overlay guessing, no stale entries for other hardware
revisions. Handy when writing mainline nodes for a device whose vendor tree you
only have as binaries.

    python3 -I tools/dtdir-dump.py /proc/device-tree/soc/ap-apb/i2c@0x20100000/aw32257@6a

Properties are shown as strings when they look like strings, as u32 cells when
they divide by four, and as a hex dump otherwise. Pass -R to walk a subtree
instead of one node.
"""
import os
import sys


def show(name, data):
    printable = data.rstrip(b"\0")
    if printable and all(32 <= c < 127 for c in printable):
        print(f"    {name} = {printable.decode()!r}")
        return
    if data and len(data) % 4 == 0:
        cells = [int.from_bytes(data[i:i + 4], "big") for i in range(0, len(data), 4)]
        hint = ""
        if len(cells) == 1:
            hint = f"  ({cells[0]})"
        elif all(32 <= c < 127 for c in cells):
            hint = "  = " + "".join(chr(c) for c in cells)
        print(f"    {name} = <" + " ".join(f"0x{c:x}" for c in cells) + f">{hint}")
        return
    print(f"    {name} = [{len(data)} bytes] {data.hex()}")


def walk(path, recurse):
    print(path)
    try:
        entries = sorted(os.listdir(path))
    except OSError as e:
        print(f"  {e}")
        return
    for e in entries:
        p = os.path.join(path, e)
        if os.path.isdir(p):
            if recurse:
                walk(p, recurse)
            else:
                print(f"    [{e}/]")
            continue
        try:
            with open(p, "rb") as f:
                show(e, f.read())
        except OSError as e:
            print(f"    {e}: {e}")


def main():
    args = [a for a in sys.argv[1:] if a != "-R"]
    recurse = "-R" in sys.argv
    if len(args) != 1:
        sys.exit("usage: dtdir-dump.py [-R] /proc/device-tree/<node>")
    walk(args[0], recurse)


if __name__ == "__main__":
    main()
