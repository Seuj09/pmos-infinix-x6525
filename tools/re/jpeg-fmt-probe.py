#!/usr/bin/env python3
"""Decode probe for several sampling formats / sizes in one run.

Usage: jpeg-fmt-probe.py libjpeg_hw_sprd.so OUTDIR SET      SET = A (4:4:4 and 4:2:2, 32x32) or B (grey 48x24, 4:2:0 50x38)
Writes OUTDIR/probe.sh (run as root on the phone:  sudo sh probe.sh > out.txt) and OUTDIR/cases.json with the
expected planes; tools/re/jpeg-fmt-check.py compares.  Every case dumps the three output buffers in full
because the layout of the chroma planes for the other formats is not known yet.
"""
import base64, io, json, os, struct, sys
import numpy as np
from PIL import Image

so, out, which = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
CASES = {"A": [("444", 32, 32), ("422", 32, 32)], "C": [("422", 32, 32)], "E": [("422", 32, 32), ("422r1", 32, 32), ("422r2", 32, 32), ("422c", 32, 32)], "D": [("422", 32, 32), ("422b", 32, 32), ("444", 32, 32), ("444b", 32, 32)], "B": [("gray", 48, 24), ("420odd", 50, 38)]}[which]
RESET = {"422r1": "rst", "422r2": "rst+tabs", "422c": "cycle+tabs", "422b": "none", "444": "none", "444b": "tabs"}  # set D: what to do before the case
FMT = {"422r1": (3, 16, 8, 1), "422r2": (3, 16, 8, 1), "422c": (3, 16, 8, 1), "422b": (3, 16, 8, 1), "444b": (2, 8, 8, 0), "444": (2, 8, 8, 0), "422": (3, 16, 8, 1), "420odd": (0, 16, 16, 2), "gray": (4, 8, 8, None)}  # code, mcu w, h, PIL subsampling
ZZ = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
      35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]
C = np.array([[(np.sqrt(.125) if u == 0 else .5) * np.cos((2 * x + 1) * u * np.pi / 16) for x in range(8)] for u in range(8)])
rev3 = lambda x: ((x & 1) << 2) | (x & 2) | ((x >> 2) & 1)

def make(name, W, H):
    code, mw, mh, sub = FMT[name]
    rng = np.random.default_rng(7)
    g = np.zeros((H, W, 3))
    for y in range(H):
        for x in range(W):
            g[y, x] = (x * 255 / W, y * 255 / H, 128 + 100 * np.sin(x / 7.0) * np.cos(y / 5.0))
    g += rng.normal(0, 4, g.shape)
    im = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), "RGB")
    if sub is None: im = im.convert("L")
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90, **({} if sub is None else {"subsampling": sub}))
    j = b.getvalue()
    qt, ht, comps, scan = {}, {}, [], b""
    pos = 2
    while pos < len(j):
        m = j[pos + 1]; L = struct.unpack(">H", j[pos + 2:pos + 4])[0]; seg = j[pos + 4:pos + 2 + L]
        if m == 0xDB:
            p = 0
            while p < len(seg): qt[seg[p] & 15] = list(seg[p + 1:p + 65]); p += 65
        if m == 0xC4:
            p = 0
            while p < len(seg):
                tc = seg[p]; cnt = list(seg[p + 1:p + 17]); n = sum(cnt); ht[tc] = (cnt, list(seg[p + 17:p + 17 + n])); p += 17 + n
        if m == 0xC0:
            comps = [(seg[6 + 3 * i], seg[7 + 3 * i] >> 4, seg[7 + 3 * i] & 15, seg[8 + 3 * i]) for i in range(seg[5])]
        if m == 0xDA:
            scan = j[pos + 2 + L:-2]; break
        pos += 2 + L
    def codes(cnt, sy):
        c = k = 0; d = {}
        for l in range(1, 17):
            for _ in range(cnt[l - 1]): d[(l, c)] = sy[k]; k += 1; c += 1
            c <<= 1
        return d
    tabs = {t: codes(*ht[t]) for t in ht}
    ub = bytearray(); i = 0
    while i < len(scan):
        ub.append(scan[i]); i += 2 if scan[i] == 0xFF and i + 1 < len(scan) and scan[i + 1] == 0 else 1
    bits = "".join(format(x, "08b") for x in ub); st = {"bp": 0}
    def get(d):
        c = 0
        for l in range(1, 17):
            c = (c << 1) | int(bits[st["bp"]]); st["bp"] += 1
            if (l, c) in d: return d[(l, c)]
        raise ValueError
    def rd(n):
        if n == 0: return 0
        v = int(bits[st["bp"]:st["bp"] + n], 2); st["bp"] += n
        return v if v >= 1 << (n - 1) else v - (1 << n) + 1
    def block(dc, ac, pred, q):
        z = [0] * 64
        pred += rd(get(dc)); z[0] = pred; k = 1
        while k < 64:
            rs = get(ac); r, s = rs >> 4, rs & 15
            if rs == 0: break
            if rs == 0xF0: k += 16; continue
            k += r; z[k] = rd(s); k += 1
        m = np.zeros((8, 8))
        for k in range(64): m[ZZ[k] // 8][ZZ[k] % 8] = z[k] * q[k]
        return np.clip(np.round(C.T @ m @ C) + 128, 0, 255).astype(np.uint8), pred
    nx, ny = -(-W // mw), -(-H // mh)
    planes = [np.zeros((ny * mh * v // comps[0][2], nx * mw * h // comps[0][1]), np.uint8) for (_, h, v, _) in comps]
    pred = [0] * len(comps)
    for my in range(ny):
        for mx in range(nx):
            for ci, (cid, h, v, tq) in enumerate(comps):
                dcT, acT = (0x00, 0x10) if ci == 0 else (0x01, 0x11)
                for by in range(v):
                    for bx in range(h):
                        blk, pred[ci] = block(tabs[dcT], tabs[acT], pred[ci], qt[tq])
                        y0 = (my * v + by) * 8; x0 = (mx * h + bx) * 8
                        planes[ci][y0:y0 + 8, x0:x0 + 8] = blk
    return j, scan, qt, planes, (code, mw, mh, nx, ny)

d = open(so, "rb").read()
maxc = struct.unpack("<66I", d[0x8208:0x8208 + 264]); sym = struct.unpack("<162I", d[0x8310:0x8310 + 648])
tab = ["w 0x48 0x%x" % maxc[0], "w 0x4c 0x%x" % maxc[1]]
tab += ["w 0x%x 0x%x" % (0x50 + 4 * i, maxc[2 + i]) for i in range(64)]
tab += ["w 0x%x 0x%x" % (0x2000 + 4 * i, v) for i, v in enumerate(sym)]
e = lambda x: base64.b64encode(x).decode()
sh = ["#!/bin/sh", "# run as root with nothing unsaved:  sudo sh probe.sh > out.txt", "D=/sys/kernel/debug/sprd-jpg",
      "feed() { while IFS= read -r l; do [ -n \"$l\" ] && printf '%s\\n' \"$l\" > $D/lab_cmd; done; }",
      "echo off > $D/lab_cmd; sleep 1; echo on > $D/lab_cmd",
      "echo %s | base64 -d | feed" % e(("\n".join(tab) + "\n").encode())]
meta = {}
for name, W, H in CASES:
    j, scan, qt, planes, (code, mw, mh, nx, ny) = make(name, W, H)
    stream = scan + b"\xff\xd9" + bytes(254)
    ql = []
    for t in range(len(qt)):
        slots = [0] * 64
        for k in range(64): slots[rev3(ZZ[k] % 8) * 8 + rev3(ZZ[k] // 8)] = qt[t][k]
        ql += ["w 0x%x 0x%x" % (0x1000 + 0x80 * t + 4 * w, slots[2 * w] | slots[2 * w + 1] << 16) for w in range(32)]
    AW, AH = nx * mw, ny * mh
    r14 = {0: (((W >> 1) + 15) & ~15) & 0xfff8, 3: (W + 7) & 0xfff8}.get(code, 0)
    L = ["clear", "echo ==== case %s %dx%d fmt %d" % (name, W, H, code), "buf 1 16384", "buf 2 16384", "buf 3 16384",
         "w 0x154 0x0", "w 0x0c 0x%x" % ((((W + 15) >> 4) << 20) + W), "w 0x10 0x%x" % ((code << 29) | (ny << 13) | nx),
         "w 0x14 0x%x" % r14, "w 0x04 0x10140080", "w 0x18 0x%x" % len(stream),
         "wb 0x1c 1", "wb 0x20 2", "wb 0x24 3", "w 0x28 0x0", "wb 0x28 0", "w 0x30 0x960711", "w 0x34 0x1"]
    for _ in range(ny): L += ["w 0x04 0x10140281", "irq 50", "poll 0x15c 0x1 0x1 50", "r 0x15c 1"]
    ysz = AW * AH
    L += ["bufdump 1 0 %d" % ysz, "bufdump 2 0 %d" % (2 * ysz if code in (2,) else ysz), "bufdump 3 0 %d" % (ysz if code in (2, 3) else 64)]
    L = [l for l in L if not l.startswith("echo ====")]
    sh += ["echo '==== case %s %dx%d fmt %d'" % (name, W, H, code)]
    mode = RESET.get(name, "full") if which in "DE" else "full"
    tabcmd = "echo %s | base64 -d | feed" % e(("\n".join(tab) + "\n").encode())
    if mode == "full" and len(meta): sh += ["echo off > $D/lab_cmd; sleep 1; echo on > $D/lab_cmd", tabcmd]
    if mode == "tabs": sh += [tabcmd]
    if mode.startswith(("rst", "cycle")): sh += ["echo clear > $D/lab_cmd"]
    if mode.startswith("rst"): sh += ["echo rst > $D/lab_cmd"]
    if mode.startswith("cycle"): sh += ["echo cycle > $D/lab_cmd"]
    if mode.endswith("+tabs"): sh += [tabcmd]
    sh += ([] if mode.startswith(("rst", "cycle")) else ["echo clear > $D/lab_cmd"]) + [
           "echo \"buf 0 %d\" > $D/lab_cmd" % (len(stream) + 4096),
           "echo %s | base64 -d | dd of=$D/lab_buf0 conv=notrunc 2>/dev/null" % e(stream),
           "echo %s | base64 -d | feed" % e(("\n".join(ql) + "\n").encode()),
           "echo %s | base64 -d | feed" % e(("\n".join(L) + "\n").encode()),
           "cat $D/lab_out"]
    meta[name] = {"W": W, "H": H, "code": code, "AW": AW, "AH": AH, "ysz": ysz,
                  "dumps": [ysz, 2 * ysz if code == 2 else ysz, ysz if code in (2, 3) else 64]}
    np.savez("%s/%s.npz" % (out, name), *planes)
    open("%s/%s.jpg" % (out, name), "wb").write(j)
open(out + "/probe.sh", "w").write("\n".join(sh) + "\n")
json.dump(meta, open(out + "/cases.json", "w"))
print({k: (v["W"], v["H"], v["code"]) for k, v in meta.items()})
