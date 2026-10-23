#!/usr/bin/env python3
"""Write receipts/relief.txt from build/relief/relief.json and the encoder's transform.

    python3 -I tools/relief-receipt.py <relief.json> <transform.txt>
"""
import json, os, shutil, sys

relief_json, transform_path = sys.argv[1:3]
r = json.load(open(relief_json))
transform = open(transform_path).read().splitlines()
master = [line.split()[-1] for line in transform if line.startswith("master")][0]
lines = []


def f(key, *values):
    lines.append(f"{key:<10}{values[0]}")
    lines.extend(" " * 10 + v for v in values[1:])


e, px = r["extent_m"], r["pixels"]
f("picture", "The valley's relief, drawn from the engine's terrain tiles (USGS",
  "lidar). Not a game frame.")
f("manifest", f"{r['manifest']['id']}, sha256", r["manifest"]["sha256"])
f("tiles", f"{r['tilesUsed']} fine tiles at 2 m, each checked against the manifest;",
  f"their hashes in order hash to {r['tilesSHA256'][:16]}")
f("extent", f"{(e['east'] - e['west']) / 1000:g} x {(e['north'] - e['south']) / 1000:g} km, north up, "
  f"{px['metresPerPixel']:g} m per pixel")
f("method", "2 x 2 block mean of the 2 m nodes; Horn (1981) hillshade, light",
  "from azimuth 315 deg at 45 deg altitude; land grey 24 + 231 x",
  "max(0, cos), so black is water only: lake and river nodes, which",
  "the survey flattens and whose bed is unknown; no colour,",
  "atmosphere or grade")
f("check", f"{px['blackCells']} black cells = {px['waterCells']} water + {px['noDataCells']} no-data cells")
f("tool", "tools/relief.py in this repository, Python standard library only")
f("master", f"PNG {px['width']} x {px['height']} grey, sha256", master,
  f"pixel data sha256 {px['greySHA256']}")
for line in transform:
    if line.startswith("published"):
        _, path, size, _, _, _, sha = line.split()
        if os.path.exists(path):
            f("published", f"{os.path.basename(path)} {size} sha256", sha)
hm = r["heightmap"]
f("heights", f"{hm['file']} {hm['width']} x {hm['height']}, {hm['metresPerPixel']:g} m; {hm['phone']['file']} "
  f"{hm['phone']['width']} x {hm['phone']['height']}, {hm['phone']['metresPerPixel']:g} m (phones)",
  "R x 256 + G = height above NAVD88 0 in 5 cm steps; B = 255 for water;",
  "means of the cells above; lit live in your browser by the same",
  "method (Horn's 3 x 3 kernel, grey 24 + 231 x max(0, cos)) from",
  "these heights, with a lamp moved as you scroll (not the sun)",
  f"rgb sha256 {hm['rgbSHA256']}", f"           {hm['phone']['rgbSHA256']}")
for name in (hm["file"], hm["phone"]["file"]):
    path = os.path.join("media/relief", name)
    if os.path.exists(path):
        import hashlib
        f("published", f"{name} sha256", hashlib.sha256(open(path, "rb").read()).hexdigest())
f("marks", "camera positions and fields of view copied from each frame's receipt")
open("receipts/relief.txt", "w").write("\n".join(lines) + "\n")
shutil.copy(relief_json, "receipts/relief.json")
print("\n".join(lines))
