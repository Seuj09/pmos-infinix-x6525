#!/usr/bin/env python3
"""Compare jpeg-fmt-probe.py output.  Usage: jpeg-fmt-check.py OUTDIR < out.txt
Splits each case into its three bufdumps (address restarts at 0), then tries layouts and reports the best match."""
import json, re, struct, sys
import numpy as np
d = sys.argv[1]
meta = json.load(open(d + "/cases.json"))
cases, cur = {}, None
for line in sys.stdin:
    s = line.strip()
    m = re.match(r"^==== case (\S+)", s)
    if m: cur = cases.setdefault(m.group(1), []); continue
    m = re.match(r"^([0-9a-f]{6}): ((?:[0-9a-f]{8} ?){4})\s*$", s)
    if m and cur is not None:
        a = int(m.group(1), 16)
        if a == 0 or not cur: cur.append(bytearray())
        cur[-1] += b"".join(struct.pack("<I", int(x, 16)) for x in m.group(2).split())

def err(got, e):
    h, w = min(got.shape[0], e.shape[0]), min(got.shape[1], e.shape[1])
    x = abs(got[:h, :w].astype(int) - e[:h, :w].astype(int))
    return x.max(), x.mean()

for name, m in meta.items():
    exp = np.load("%s/%s.npz" % (d, name)); P = [exp["arr_%d" % i] for i in range(len(exp.files))]
    bufs = cases.get(name, [])
    print("== %s %dx%d fmt %d aligned %dx%d, %d dumps" % (name, m["W"], m["H"], m["code"], m["AW"], m["AH"], len(bufs)))
    if len(bufs) < 3: print("  missing dumps"); continue
    AW, AH, W = m["AW"], m["AH"], m["W"]
    b = [np.frombuffer(bytes(x), np.uint8) for x in bufs]
    for stride in sorted({W, AW}):
        n = len(b[0]) // stride
        print("  Y stride %d: max %d mean %.3f" % ((stride,) + err(b[0][:n * stride].reshape(n, stride), P[0])))
    for k in range(1, len(P)):
        ph, pw = P[k].shape
        found = False
        for bi in (1, 2):
            for stride in sorted({pw, W, AW, W // 2, AW // 2, ((W >> 1) + 15) & ~15, 2 * pw}):
                if stride <= 0 or len(b[bi]) < stride * ph: continue
                g = b[bi][:len(b[bi]) // stride * stride].reshape(-1, stride)
                for nm, cand in (("plain", g[:, :pw] if stride >= pw else None), ("even", g[:, 0::2]), ("odd", g[:, 1::2])):
                    if cand is None or cand.shape[1] < pw: continue
                    mx, mn = err(cand[:, :pw], P[k])
                    if mn < 1.5: print("  comp %d: buf%d stride %d %s: max %d mean %.3f" % (k, bi + 1, stride, nm, mx, mn)); found = True
        if not found: print("  comp %d: no layout matched" % k)
