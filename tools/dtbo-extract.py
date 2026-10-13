#!/usr/bin/env python3
"""
Split an Android dtbo.img partition image into its individual device trees.

The container format (AOSP "dt_table_header") is:

    u32 magic; u32 total_size; u32 header_size; u32 dt_entry_size;
    u32 dt_entry_count; u32 dt_entries_offset; u32 page_size; u32 version;

followed by dt_entry_count entries of dt_entry_size bytes each, where the
first four u32s of an entry are dt_size, dt_offset, id, rev.

Usage:
    python3 -I dtbo-extract.py <dtbo.img> [-o outdir]     # writes every entry
    python3 -I dtbo-extract.py <dtbo.img> -l              # just list them
    python3 -I dtbo-extract.py <dtbo.img> -n 18 -o x.dtb  # extract one entry

The `id` field is what the bootloader matches against androidboot.dtbo_idx,
so the listing tells you which entry a given device boots with.
"""
import argparse
import os
import struct
import sys

MAGIC = 0xD7B7AB1E
HEADER = struct.Struct(">8I")
ENTRY = struct.Struct(">8I")


def parse(path):
    with open(path, "rb") as f:
        blob = f.read()
    if len(blob) < HEADER.size:
        sys.exit("file is smaller than a dt_table_header")
    magic, total, hdr_size, entry_size, count, entries_off, page_size, version = \
        HEADER.unpack_from(blob, 0)
    if magic != MAGIC:
        sys.exit(f"bad magic 0x{magic:08x} (expected 0x{MAGIC:08x}) - not a dtbo image")
    print(f"total={total} header={hdr_size} entry_size={entry_size} "
          f"entries={count} page_size={page_size} version={version}")
    if entry_size < ENTRY.size:
        sys.exit(f"entry_size {entry_size} is too small for 4 u32 fields")
    out = []
    for i in range(count):
        base = entries_off + i * entry_size
        if base + ENTRY.size > len(blob):
            sys.exit(f"entry {i} runs past the end of the file")
        dt_size, dt_off, dt_id, dt_rev = ENTRY.unpack_from(blob, base)[:4]
        out.append((i, dt_size, dt_off, dt_id, dt_rev))
    return blob, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("-o", "--outdir", default=None)
    ap.add_argument("-l", "--list", action="store_true")
    ap.add_argument("-n", "--index", type=int, default=None,
                    help="extract only this entry index (as one file)")
    ap.add_argument("-x", "--output", default=None,
                    help="path for -n output")
    args = ap.parse_args()

    blob, entries = parse(args.image)
    for i, size, off, dt_id, rev in entries:
        print(f"  [{i:2}] offset=0x{off:08x} size={size:8} id=0x{dt_id:08x} rev=0x{rev:08x}")
    if args.list:
        return
    if args.index is not None:
        if not 0 <= args.index < len(entries):
            sys.exit(f"index {args.index} out of range (0..{len(entries) - 1})")
        _, size, off, dt_id, _ = entries[args.index]
        dest = args.output or f"dtbo-entry-{args.index}-id{dt_id:08x}.dtb"
        with open(dest, "wb") as f:
            f.write(blob[off:off + size])
        print(f"wrote {dest} ({size} bytes)")
        return
    if args.outdir:
        os.makedirs(args.outdir, exist_ok=True)
        for i, size, off, dt_id, _ in entries:
            dest = os.path.join(args.outdir, f"dtbo-entry-{i:02}-id{dt_id:08x}.dtb")
            with open(dest, "wb") as f:
                f.write(blob[off:off + size])
        print(f"wrote {len(entries)} device trees to {args.outdir}")


if __name__ == "__main__":
    main()
