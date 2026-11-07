#!/usr/bin/env python3
"""Build a first JPEG decode probe for the sprd-jpg register lab.

Usage: jpeg-decode-probe.py libjpeg_hw_sprd.so OUTDIR
Writes OUTDIR/scan.bin (entropy data of a 16x16 grey baseline JPEG), OUTDIR/expected.bin
(what a correct decode should give for the Y plane) and OUTDIR/probe.sh (run as root on the phone).

Register values come from the stock library (JpegDec_HwTopRegCfg / START_HW_DECODE). Fields whose
meaning is not settled yet (the 0x38..0x44 words, 0x18, mode flags) are guesses and are marked
GUESS: the probe only reports what moved, it does not claim a decode works.
"""
import io, os, struct, sys
from PIL import Image

so, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
W = H = 16
im = Image.new("L", (W, H))
im.putdata([(x * 16 + y * 4) & 0xff for y in range(H) for x in range(W)])
b = io.BytesIO()
im.save(b, "JPEG", quality=90, subsampling=0)
j = b.getvalue()
sos = j.rfind(b"\xff\xda")
hl = struct.unpack(">H", j[sos + 2:sos + 4])[0]
scan = j[sos + 2 + hl:-2]
scan += b"\xff\xd9" + bytes(30)      # EOI and zero padding: the engine reads ahead of the last symbol
open(out + "/scan.bin", "wb").write(scan)
dec = Image.open(io.BytesIO(j)).convert("L")
open(out + "/expected.bin", "wb").write(bytes(dec.tobytes()))
open(out + "/image.jpg", "wb").write(j)

d = open(so, "rb").read()
def words(v, n): return struct.unpack("<%dI" % n, d[v:v + 4 * n])
maxc = words(0x8208, 66)
sym = words(0x8310, 162)

tables = []
t = tables.append
t("w 0x48 0x%x" % maxc[0]); t("w 0x4c 0x%x" % maxc[1])
for i in range(64): t("w 0x%x 0x%x" % (0x50 + 4 * i, maxc[2 + i]))
for i, v in enumerate(sym): t("w 0x%x 0x%x" % (0x2000 + 4 * i, v))
# quantisation window, measured on the phone (tools/re/jpeg-window-probe.py): 64 16-bit slots, word w holds
# slot 2w (low) and 2w+1 (high); the coefficient at raster row v, column u uses slot rev3(u)*8 + rev3(v)
# (the IDCT works in bit-reversed order). One table per 0x80 bytes.
ZZ = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
      35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]
rev3 = lambda x: ((x & 1) << 2) | (x & 2) | ((x >> 2) & 1)
dqt = j.find(b"\xff\xdb")
qzz = list(j[dqt + 5:dqt + 5 + 64])              # DQT is in zigzag order
slots = [0] * 64
for k in range(64):
    v, u = ZZ[k] // 8, ZZ[k] % 8
    slots[rev3(u) * 8 + rev3(v)] = qzz[k]
for w in range(32): t("w 0x%x 0x%x" % (0x1000 + 4 * w, slots[2 * w] | slots[2 * w + 1] << 16))
qt = qzz
L = []
a = L.append
a("clear")
a("r 0x48 2"); a("r 0x2000 4"); a("r 0x1000 4")
a("r 0x04 1"); a("r 0x38 4"); a("r 0x2c 1"); a("r 0x15c 1"); a("r 0x168 1")
a("buf 1 4096"); a("buf 2 4096"); a("buf 3 4096")
# JpegDec_HwTopRegCfg, in the stock order (W=H=16 grey, format 0)
a("r 0x154 1")
a("w 0x158 0xff0005")                                  # stock: (read 0x154) | 0xff0000 | 5
a("w 0x154 0x0")
a("w 0x0c 0x%x" % ((((W + 15) >> 4) << 20) + W))
a("w 0x10 0x%x" % ((4 << 29) | (2 << 13) | 2))        # format 4 = grey, 2x2 MCUs of 8x8 (JPEGFW_UpdateMiscFields)
a("w 0x14 0x0")                                         # stock: 0 for formats other than 0 and 3
a("w 0x04 0x10140080")                                  # HwTopRegCfg mode word (flags 0)
a("w 0x18 0x%x" % len(scan))                            # GUESS: stock ctx[0x54]-0x21f
a("wb 0x1c 1"); a("wb 0x20 2"); a("wb 0x24 2")
a("w 0x28 0x0"); a("wb 0x28 0")
a("w 0x30 0x960711"); a("w 0x34 0x1")
# START_HW_DECODE would now write 0x38/0x3c/0x40/0x44 (meaning unknown, left alone), then the mode word
a("r 0x04 1"); a("r 0x18 1"); a("r 0x38 4")
a("w 0x04 0x10140281")                                   # start (bit 0), plain case
a("irq 200"); a("poll 0x15c 0x5 0x1 50")
a("r 0x04 1"); a("r 0x2c 1"); a("r 0x15c 1"); a("r 0x168 1"); a("r 0x38 4")
a("bufdump 1 0 256")
# second start: does the engine continue with the next MCU row?
a("w 0x04 0x10140281"); a("irq 200")
a("r 0x04 1"); a("r 0x2c 1"); a("r 0x15c 1"); a("r 0x38 4")
a("bufdump 1 0 256"); a("bufdump 2 0 64"); a("bufdump 3 0 64")
lab = "\n".join(L) + "\n"
open(out + "/probe.lab", "w").write(lab)
import base64
tab = "\n".join(tables) + "\n"
open(out + "/tables.lab", "w").write(tab)
open(out + "/probe.sh", "w").write("""#!/bin/sh
# self-contained: run as root with nothing unsaved; a wrong guess may hang the codec
D=/sys/kernel/debug/sprd-jpg
feed() { while IFS= read -r l; do [ -n "$l" ] && printf '%%s\\n' "$l" > $D/lab_cmd; done; }
echo off > $D/lab_cmd; sleep 1; echo on > $D/lab_cmd
echo "buf 0 4096" > $D/lab_cmd
echo %s | base64 -d | dd of=$D/lab_buf0 conv=notrunc 2>/dev/null
echo %s | base64 -d | feed
echo clear > $D/lab_cmd
echo %s | base64 -d | feed
cat $D/lab_out
""" % (base64.b64encode(scan).decode(), base64.b64encode(tab.encode()).decode(), base64.b64encode(lab.encode()).decode()))
print("scan bytes:", len(scan), "quant[0:4]:", qt[:4])
