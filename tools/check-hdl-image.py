#!/usr/bin/env python3
"""
Validate an OmniVision TCM HDL firmware image the way the driver does.

This mirrors tcm_parse_image() in drivers/ovt-tcm-spi.c: a little-endian header
(magic, area count), an array of area addresses, and for each area a descriptor
with its own magic, id, length and a CRC32 over the payload - the CRC has to
match or the driver rejects the whole image at probe.

    python3 -I tools/check-hdl-image.py hdl_firmware_01.img

The image comes off the device (/vendor/firmware on the stock ROM), so this is
the check that it was copied whole and is the file the driver wants.
"""
import struct
import sys
import zlib

IMAGE_FILE_MAGIC = 0x4818472B
FLASH_AREA_MAGIC = 0x7C05E516
# magic, id, flags, flash_addr_words, length, checksum - all u32 except id
AREA = struct.Struct("<4s16s4s4s4s4s")
# the driver refuses an image without these two
REQUIRED = ("ROMBOOT_APP_CODE", "APP_CONFIG")


def u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[0] + "\nusage: check-hdl-image.py <image>")
    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 8 or u32(data, 0) != IMAGE_FILE_MAGIC:
        sys.exit(f"not an HDL image: header magic 0x{u32(data, 0):08x}, "
                 f"expected 0x{IMAGE_FILE_MAGIC:08x}")

    count = u32(data, 4)
    if count > (len(data) - 8) / 4:
        sys.exit(f"area count {count} does not fit in {len(data)} bytes")
    print(f"{path}: {len(data)} bytes, {count} areas")

    found = {}
    for i in range(count):
        addr = u32(data, 8 + 4 * i)
        if addr > len(data) or len(data) - addr < AREA.size:
            sys.exit(f"area {i}: descriptor at 0x{addr:x} does not fit")
        magic, raw_id, flags, flash_addr, length, checksum = AREA.unpack_from(data, addr)
        # ids are space padded to 16 bytes and the driver matches them with
        # strncmp, so trim rather than requiring an exact match
        area_id = raw_id.split(b"\0")[0].decode(errors="replace").rstrip()
        if u32(magic, 0) != FLASH_AREA_MAGIC:
            # the driver skips these rather than failing
            print(f"  area {i}: magic 0x{u32(magic, 0):08x}, not an area - skipped by the driver")
            continue
        size = u32(length, 0)
        if size > len(data) - addr - AREA.size:
            sys.exit(f"area {i}: length {size} overruns the file")
        payload = data[addr + AREA.size:addr + AREA.size + size]
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        ok = crc == u32(checksum, 0)
        print(f"  area {i}: id={area_id!r} flags=0x{u32(flags, 0):x} "
              f"flash=0x{u32(flash_addr, 0):x} len={size} crc={'ok' if ok else 'MISMATCH'}")
        if not ok:
            sys.exit(f"  checksum mismatch in {area_id!r} "
                     f"(computed 0x{crc:08x}, file says 0x{u32(checksum, 0):08x})")
        found[area_id] = size

    missing = [r for r in REQUIRED if r not in found]
    if missing:
        sys.exit(f"  missing {', '.join(missing)} - the driver requires both")
    print("  valid: the driver will accept this image")


if __name__ == "__main__":
    main()
