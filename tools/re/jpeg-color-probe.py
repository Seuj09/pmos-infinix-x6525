#!/usr/bin/env python3
"""Colour (4:2:0, format code 0) decode probe for the sprd-jpg register lab.

Usage: jpeg-color-probe.py libjpeg_hw_sprd.so OUTDIR
Writes OUTDIR/probe.sh (run as root on the phone, redirect output to a file) and OUTDIR/expected.npz with the
exact Y, Cb, Cr planes of a small 32x32 4:2:0 JPEG, computed here from its own coefficients (no libjpeg
upsampling in between), for tools/re/jpeg-color-check.py.
"""
import base64, io, os, struct, sys
import numpy as np
from PIL import Image

so, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
W = int(sys.argv[3]) if len(sys.argv) > 3 else 32
H = int(sys.argv[4]) if len(sys.argv) > 4 else 32
NOISE = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0   # noise makes long Huffman codes (16-bit) appear
rng = np.random.default_rng(1)
g = np.zeros((H, W, 3))
for y in range(H):
    for x in range(W):
        g[y, x] = (x * 255 / W, y * 255 / H, 128 + 100 * np.sin(x / 7.0) * np.cos(y / 5.0))
g += rng.normal(0, NOISE, g.shape)
im = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), "RGB")
b = io.BytesIO(); im.save(b, "JPEG", quality=90, subsampling=2); j = b.getvalue()

qt, ht, scan = {}, {}, b""
pos = 2
while pos < len(j):
    m = j[pos + 1]; L = struct.unpack(">H", j[pos + 2:pos + 4])[0]; seg = j[pos + 4:pos + 2 + L]
    if m == 0xDB:
        p = 0
        while p < len(seg):
            qt[seg[p] & 15] = list(seg[p + 1:p + 65]); p += 65
    if m == 0xC4:
        p = 0
        while p < len(seg):
            tc = seg[p]; cnt = list(seg[p + 1:p + 17]); n = sum(cnt); ht[tc] = (cnt, list(seg[p + 17:p + 17 + n])); p += 17 + n
    if m == 0xDA:
        scan = j[pos + 2 + L:-2]; break
    pos += 2 + L

def codes(cnt, sy):
    c = k = 0; d = {}
    for l in range(1, 17):
        for _ in range(cnt[l - 1]): d[(l, c)] = sy[k]; k += 1; c += 1
        c <<= 1
    return d
dcl, dcc, acl, acc = (codes(*ht[t]) for t in (0x00, 0x01, 0x10, 0x11))
ub = bytearray(); i = 0
while i < len(scan):
    ub.append(scan[i]); i += 2 if scan[i] == 0xFF and i + 1 < len(scan) and scan[i + 1] == 0 else 1
bits = "".join(format(x, "08b") for x in ub); bp = 0
def get(d):
    global bp
    c = 0
    for l in range(1, 17):
        c = (c << 1) | int(bits[bp]); bp += 1
        if (l, c) in d: return d[(l, c)]
    raise ValueError("bad code")
def rd(n):
    global bp
    if n == 0: return 0
    v = int(bits[bp:bp + n], 2); bp += n
    return v if v >= 1 << (n - 1) else v - (1 << n) + 1
ZZ = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
      35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]
C = np.array([[(np.sqrt(.125) if u == 0 else .5) * np.cos((2 * x + 1) * u * np.pi / 16) for x in range(8)] for u in range(8)])
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
Y = np.zeros((H, W), np.uint8); Cb = np.zeros((H // 2, W // 2), np.uint8); Cr = Cb.copy()
assert W % 16 == 0 and H % 16 == 0
pr = [0, 0, 0]
for my in range(H // 16):
    for mx in range(W // 16):
        for by in range(2):
            for bx in range(2):
                blk, pr[0] = block(dcl, acl, pr[0], qt[0])
                Y[my * 16 + by * 8:my * 16 + by * 8 + 8, mx * 16 + bx * 8:mx * 16 + bx * 8 + 8] = blk
        blk, pr[1] = block(dcc, acc, pr[1], qt[1]); Cb[my * 8:my * 8 + 8, mx * 8:mx * 8 + 8] = blk
        blk, pr[2] = block(dcc, acc, pr[2], qt[1]); Cr[my * 8:my * 8 + 8, mx * 8:mx * 8 + 8] = blk
np.savez(out + "/expected.npz", Y=Y, Cb=Cb, Cr=Cr)
open(out + "/image.jpg", "wb").write(j)

stream = scan.replace(b"", b"")            # entropy data exactly as in the file (already byte-stuffed)
PAD = int(sys.argv[6]) if len(sys.argv) > 6 else 30
stream += b"\xff\xd9" + bytes(PAD)           # the engine reads ahead of the last symbol

d = open(so, "rb").read()
maxc = struct.unpack("<66I", d[0x8208:0x8208 + 264]); sym = struct.unpack("<162I", d[0x8310:0x8310 + 648])
rev3 = lambda x: ((x & 1) << 2) | (x & 2) | ((x >> 2) & 1)
t = ["w 0x48 0x%x" % maxc[0], "w 0x4c 0x%x" % maxc[1]]
t += ["w 0x%x 0x%x" % (0x50 + 4 * i, maxc[2 + i]) for i in range(64)]
t += ["w 0x%x 0x%x" % (0x2000 + 4 * i, v) for i, v in enumerate(sym)]
for tab in (0, 1):                          # table 0 (luma) at 0x1000, table 1 (chroma) at 0x1080
    slots = [0] * 64
    for k in range(64):
        slots[rev3(ZZ[k] % 8) * 8 + rev3(ZZ[k] // 8)] = qt[tab][k]
    t += ["w 0x%x 0x%x" % (0x1000 + 0x80 * tab + 4 * w, slots[2 * w] | slots[2 * w + 1] << 16) for w in range(32)]
tab_lab = "\n".join(t) + "\n"
L = ["clear", "buf 1 %d" % (W * H), "buf 2 %d" % (W * H // 2), "buf 3 4096",
     "w 0x154 0x0",
     "w 0x0c 0x%x" % ((((W + 15) >> 4) << 20) + W),
     "w 0x10 0x%x" % ((0 << 29) | ((H // 16) << 13) | (W // 16)),   # format 0 (4:2:0); counts in MCUs (checked at 32x32)
     "w 0x14 0x%x" % ((((W >> 1) + 15) & ~15) & 0xfff8),         # chroma stride
     "w 0x04 0x10140080", "w 0x18 0x%x" % len(stream),
     "wb 0x1c 1", "wb 0x20 2", "wb 0x24 3", "w 0x28 0x0", "wb 0x28 0",
     "w 0x30 0x960711", "w 0x34 0x1",
     "r 0x04 1", "r 0x38 4",
     ]
for _ in range(H // 16):
    L += ["w 0x04 0x10140281", "irq 50", "poll 0x15c 0x5 0x1 50", "r 0x15c 1", "r 0x38 4"]
L += [     "bufdump 1 0 %d" % (W * H), "bufdump 2 0 %d" % (W * H // 2)]
lab = "\n".join(L) + "\n"
e = lambda x: base64.b64encode(x).decode()
open(out + "/probe.sh", "w").write("""#!/bin/sh
# run as root with nothing unsaved:  sudo sh probe.sh > out.txt
D=/sys/kernel/debug/sprd-jpg
feed() { while IFS= read -r l; do [ -n "$l" ] && printf '%%s\\n' "$l" > $D/lab_cmd; done; }
echo off > $D/lab_cmd; sleep 1; echo on > $D/lab_cmd
echo "buf 0 %d" > $D/lab_cmd
echo %s | base64 -d | dd of=$D/lab_buf0 conv=notrunc 2>/dev/null
echo %s | base64 -d | feed
echo clear > $D/lab_cmd
echo %s | base64 -d | feed
cat $D/lab_out
""" % (len(stream) + 4096, e(stream), e(tab_lab.encode()), e(lab.encode())))
print("stream bytes", len(stream), "MCUs", (W // 16) * (H // 16))
