#!/usr/bin/env python3
"""
Check that the boot filesystem of a build holds what U-Boot's extlinux will ask for.

    python3 -I tools/check-boot-fs.py pmos-boot-fs.img [sprd/ums9230-infinix-x6525.dtb]

U-Boot (bootstd, extlinux) reads /extlinux/extlinux.conf and then loads the kernel,
initramfs and device tree it names. A mismatch - a dtb that is not where `fdtdir` and
U-Boot's default fdtfile point, a missing initramfs - ends at the prompt with a message
on a screen nobody is looking at. This reads the filesystem with debugfs (no root, no
loop device) and fails if any named file is missing. The second argument is U-Boot's
CONFIG_DEFAULT_FDT_FILE, used when the config says `fdtdir` instead of `fdt`.
"""
import re
import subprocess
import sys


def dbg(img, cmd):
    r = subprocess.run(["debugfs", "-R", cmd, img], capture_output=True, text=True)
    return r.stdout


def exists(img, path):
    return "Inode:" in dbg(img, f"stat {path}")


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    img = sys.argv[1]
    fdtfile = sys.argv[2] if len(sys.argv) == 3 else "sprd/ums9230-infinix-x6525.dtb"
    conf = dbg(img, "cat /extlinux/extlinux.conf")
    if "label" not in conf.lower() and "linux" not in conf.lower() and "kernel" not in conf.lower():
        print(f"FAIL: no usable /extlinux/extlinux.conf in {img}")
        return 1
    print("extlinux.conf:")
    for line in conf.splitlines():
        if line.strip():
            print("   " + line)
    kernel = initrd = fdt = fdtdir = None
    for line in conf.splitlines():
        w = line.strip().split(None, 1)
        if len(w) != 2:
            continue
        k, v = w[0].lower(), w[1].strip()
        if k in ("kernel", "linux"):
            kernel = v
        elif k == "initrd":
            initrd = v
        elif k == "fdt":
            fdt = v
        elif k == "fdtdir":
            fdtdir = v
    bad = 0

    def need(what, path):
        nonlocal bad
        p = path if path.startswith("/") else "/" + path
        ok = exists(img, p)
        print(f"{'ok  ' if ok else 'FAIL'}: {what} {p}")
        bad += not ok

    if not kernel:
        print("FAIL: extlinux.conf names no kernel")
        return 1
    need("kernel", kernel)
    if initrd:
        need("initrd", initrd)
    else:
        print("WARN: no initrd line")
    if fdt:
        need("fdt", fdt)
    elif fdtdir:
        need("fdtdir + default fdtfile", fdtdir.rstrip("/") + "/" + fdtfile)
    else:
        print("FAIL: neither fdt nor fdtdir: U-Boot would hand the kernel its own device tree")
        bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
