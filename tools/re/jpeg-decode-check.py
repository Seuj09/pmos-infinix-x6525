#!/usr/bin/env python3
"""Compare the Y plane dumped by jpeg-decode-probe.sh with the expected decode.
Usage: jpeg-decode-check.py OUTDIR < paste-of-probe-output   (uses the last 'bufdump 1' of 16 lines)"""
import re, struct, sys
import numpy as np
words = []
for line in sys.stdin:
    m = re.match(r"^([0-9a-f]{6}): ((?:[0-9a-f]{8} ?){4})\s*$", line.strip())
    if m:
        words.append([int(x, 16) for x in m.group(2).split()])
# the probe prints three dumps (buf 1 after the second start, 16/4/4 lines): take the first of the last group
ws = [w for line in words[-24:-8] for w in line]
got = np.array(list(b"".join(struct.pack("<I", w) for w in ws))).reshape(16, 16)
exp = np.array(list(open(sys.argv[1] + "/expected.bin", "rb").read())).reshape(16, 16)
print("max abs error", np.abs(got - exp).max(), " mean", np.abs(got - exp).mean())
print(got - exp)
