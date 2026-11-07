#!/usr/bin/env python3
"""Compare the planes dumped by jpeg-color-probe.py's probe.sh with the expected ones.
Usage: jpeg-color-check.py OUTDIR W H < out.txt
The chroma comes as one interleaved Cb,Cr plane (NV12 layout) at the second address, stride = W bytes."""
import re, struct, sys
import numpy as np
W, H = int(sys.argv[2]), int(sys.argv[3])
words = []
for line in sys.stdin:
    m = re.match(r"^([0-9a-f]{6}): ((?:[0-9a-f]{8} ?){4})\s*$", line.strip())
    if m:
        words.append([int(x, 16) for x in m.group(2).split()])
n = (W * H + W * H // 2) // 16
raw = b"".join(struct.pack("<I", w) for line in words[-n:] for w in line)
exp = np.load(sys.argv[1] + "/expected.npz")
Y = np.frombuffer(raw[:W * H], np.uint8).reshape(H, W).astype(int)
uv = np.frombuffer(raw[W * H:], np.uint8).reshape(H // 2, W).astype(int)
for name, got, e in (("Y", Y, exp["Y"]), ("Cb", uv[:, 0::2], exp["Cb"]), ("Cr", uv[:, 1::2], exp["Cr"])):
    d = got - e.astype(int)
    print(name, "max abs error", abs(d).max(), "mean %.3f" % abs(d).mean(), "pixels off by more than 1:", int((abs(d) > 1).sum()), "of", d.size)
    bad = [(by, bx) for by in range(d.shape[0] // 8) for bx in range(d.shape[1] // 8) if abs(d[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]).max() > 1]
    print("  8x8 blocks off by more than 1 (row, col):", bad[:20], "..." if len(bad) > 20 else "")
