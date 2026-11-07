#!/usr/bin/env python3
"""Compare the planes dumped by jpeg-color-probe.sh with the expected ones.
Usage: jpeg-color-check.py OUTDIR < out.txt"""
import re, struct, sys
import numpy as np
words = []
for line in sys.stdin:
    m = re.match(r"^([0-9a-f]{6}): ((?:[0-9a-f]{8} ?){4})\s*$", line.strip())
    if m:
        words.append([int(x, 16) for x in m.group(2).split()])
raw = b"".join(struct.pack("<I", w) for line in words[-96:] for w in line)
exp = np.load(sys.argv[1] + "/expected.npz")
planes = {"Y": (raw[:1024], (32, 32)), "Cb": (raw[1024:1280], (16, 16)), "Cr": (raw[1280:1536], (16, 16))}
for name, (b, shape) in planes.items():
    got = np.frombuffer(b, np.uint8).reshape(shape).astype(int)
    d = got - exp[name].astype(int)
    print(name, "max abs error", abs(d).max(), "mean %.3f" % abs(d).mean(), "pixels off by more than 1:", int((abs(d) > 1).sum()))
    for by in range(shape[0] // 8):
        print("  8x8 block row", by, "errors:", [int(abs(d[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]).max()) for bx in range(shape[1] // 8)])
