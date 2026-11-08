#!/usr/bin/env python3
"""Check what the V4L2 JPEG decoder wrote.
Usage: jpeg-v4l2-check.py CASE.npz WIDTH HEIGHT PIXFMT RAW
  PIXFMT is NV12, NV16 or GREY; RAW is the capture buffer as dumped by v4l2-ctl (--stream-to).
  The capture format is bytesperline = align16(WIDTH), height = align16(HEIGHT)."""
import sys
import numpy as np
npz, W, H, fmt, raw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
a16 = lambda x: (x + 15) & ~15
bpl, ah = a16(W), a16(H)
e = np.load(npz); P = [e["arr_%d" % i].astype(int) for i in range(len(e.files))]
d = np.fromfile(raw, np.uint8)
need = {"NV12": bpl * ah * 3 // 2, "NV16": bpl * ah * 2, "GREY": bpl * ah}[fmt]
print("file %d bytes, need %d" % (d.size, need))
Y = d[:bpl * ah].reshape(ah, bpl).astype(int)
def rep(name, got, exp):
    h, w = min(got.shape[0], exp.shape[0]), min(got.shape[1], exp.shape[1])
    x = abs(got[:h, :w] - exp[:h, :w]); print("%s: max %d mean %.3f over %dx%d" % (name, x.max(), x.mean(), w, h))
    return x.max() <= 1
ok = rep("Y", Y[:H, :min(W, 8 * (W // 8))], P[0][:H, :min(W, 8 * (W // 8))])
if fmt != "GREY":
    uv = d[bpl * ah:bpl * ah + bpl * (ah // 2 if fmt == "NV12" else ah)].reshape(-1, bpl).astype(int)
    cw = (W + 1) // 2; ch = (H + 1) // 2 if fmt == "NV12" else H
    pcw = min(P[1].shape[1], cw)
    ok &= rep("Cb", uv[:ch, 0:2 * pcw:2], P[1][:ch, :pcw] if fmt != "NV16" or P[1].shape[1] == bpl // 2 else P[1][:ch, ::2][:, :pcw])
    ok &= rep("Cr", uv[:ch, 1:2 * pcw:2], P[2][:ch, :pcw] if fmt != "NV16" or P[2].shape[1] == bpl // 2 else P[2][:ch, ::2][:, :pcw])
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
