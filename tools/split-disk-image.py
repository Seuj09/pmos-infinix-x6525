#!/usr/bin/env python3
"""
Cut a pmbootstrap disk image into the two filesystems it holds, for flashing
them into separate eMMC partitions instead of writing the disk to a microSD card.

    python3 -I tools/split-disk-image.py infinix-x6525.img boot-fs.img root-fs.img

Why: the port boots Android's boot_a -> U-Boot -> extlinux, and U-Boot reads only
the eMMC's own partition table. A whole-disk image flashed into one partition has
its inner table invisible to it; two bare filesystems flashed into two eMMC
partitions are visible. The filesystems are copied byte for byte, so their UUIDs
(which the extlinux command line names) and labels survive.

Reads an MBR or GPT table directly - no root, no loop device, no sfdisk - and
picks the partitions by the ext2/3/4 label inside them (pmOS_boot, pmOS_root).
"""
import struct
import sys

SECTOR = 512


def partitions(f):
    f.seek(0)
    mbr = f.read(512)
    if mbr[510:512] != b"\x55\xaa":
        sys.exit("no MBR/GPT signature: not a disk image")
    out = []
    ents = [struct.unpack("<8xII", mbr[446 + 16 * i:446 + 16 * i + 16]) for i in range(4)]
    types = [mbr[446 + 16 * i + 4] for i in range(4)]
    if 0xEE in types:                                   # protective MBR -> GPT
        f.seek(SECTOR)
        h = f.read(92)
        if h[:8] != b"EFI PART":
            sys.exit("protective MBR but no GPT header")
        entlba = struct.unpack("<Q", h[72:80])[0]
        n, esz = struct.unpack("<II", h[80:88])
        f.seek(entlba * SECTOR)
        for i in range(n):
            e = f.read(esz)
            if len(e) < 128 or e[:16] == b"\0" * 16:
                continue
            first, last = struct.unpack("<QQ", e[32:48])
            out.append((first, last - first + 1))
    else:
        for (start, size), t in zip(ents, types):
            if t and size and t not in (0x05, 0x0F, 0x85):
                out.append((start, size))
    return out


def ext_label(f, off):
    f.seek(off + 1024)
    sb = f.read(256)
    if len(sb) < 256 or struct.unpack("<H", sb[56:58])[0] != 0xEF53:
        return None
    return sb[120:136].split(b"\0")[0].decode(errors="replace")


def copy(f, start, size, dst):
    f.seek(start * SECTOR)
    left = size * SECTOR
    with open(dst, "wb") as o:
        while left:
            b = f.read(min(left, 8 << 20))
            if not b:
                sys.exit("image ends before the partition does")
            if b.count(0) == len(b):                    # keep holes sparse
                o.seek(len(b), 1)
            else:
                o.write(b)
            left -= len(b)
        o.truncate(size * SECTOR)


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    img, boot_out, root_out = sys.argv[1:]
    with open(img, "rb") as f:
        found = {}
        for start, size in partitions(f):
            lab = ext_label(f, start * SECTOR)
            print(f"partition start={start} size={size * SECTOR // (1 << 20)} MiB label={lab!r}")
            if lab in ("pmOS_boot", "pmOS_root"):
                found[lab] = (start, size)
        for need in ("pmOS_boot", "pmOS_root"):
            if need not in found:
                sys.exit(f"no ext filesystem labelled {need} in {img} "
                         "(a boot partition that is not ext2/3/4 is not handled)")
        copy(f, *found["pmOS_boot"], boot_out)
        copy(f, *found["pmOS_root"], root_out)
    print(f"wrote {boot_out} and {root_out}")


if __name__ == "__main__":
    main()
