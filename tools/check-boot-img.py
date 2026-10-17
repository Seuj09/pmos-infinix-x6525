#!/usr/bin/env python3
"""Sanity-check the Android boot image that gets flashed into boot_a.

    python3 -I tools/check-boot-img.py <boot.img> [max-size-MiB]

boot_a holds U-Boot, and the stock bootloader is picky about what it will start,
so check the things that can be checked offline: the ANDROID! magic, header
version 4 (so the bootloader does not look for a device tree in the payload), a
payload whose size matches the header, the 4 KiB dummy ramdisk, and that the
whole image fits the partition (64 MiB on this phone). Exit status 1 on any
failure. It reads the file only.
"""
import struct
import sys

PAGE = 4096


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    path = argv[1]
    limit = int(argv[2]) * 1048576 if len(argv) == 3 else 64 * 1048576
    data = open(path, "rb").read()
    bad = []

    if data[:8] != b"ANDROID!":
        bad.append("magic is %r, not b'ANDROID!'" % data[:8])
        return report(path, data, bad)
    kernel_size, ramdisk_size, _os, hdr_size, = struct.unpack_from("<IIII", data, 8)
    version = struct.unpack_from("<I", data, 40)[0]

    if version != 4:
        bad.append("header version %d, expected 4" % version)
    # v3/v4 headers occupy the first 4 KiB page; header_size is the struct's
    # own size (1580 for v3, 1584 for v4), not the page
    if hdr_size not in (1580, 1584, PAGE):
        print("note: unusual header_size %d" % hdr_size)
    k_pages = -(-kernel_size // PAGE)
    r_pages = -(-ramdisk_size // PAGE)
    expect = PAGE + (k_pages + r_pages) * PAGE
    # v4 may append a boot signature page(s); the file must not be shorter
    if len(data) < expect:
        bad.append("file is %d bytes, header implies at least %d" % (len(data), expect))
    if kernel_size < 100 * 1024:
        bad.append("payload is only %d bytes - that is not a U-Boot" % kernel_size)
    if ramdisk_size == 0:
        bad.append("no ramdisk (the dummy 4 KiB one is missing)")
    if len(data) > limit:
        bad.append("image is %d bytes, over the %d-byte partition" % (len(data), limit))
    cmdline = data[44:44 + 1536].split(b"\0", 1)[0]
    print("kernel (U-Boot) %d bytes, ramdisk %d bytes, cmdline %r" % (kernel_size, ramdisk_size, cmdline))
    return report(path, data, bad)


def report(path, data, bad):
    if bad:
        for b in bad:
            print("FAIL:", b)
        return 1
    print("ok: %s (%d bytes)" % (path, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
