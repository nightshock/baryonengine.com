#!/usr/bin/env python3
"""Write a frame's receipt from the engine's own capture records, so nothing is retyped.

    python3 -I tools/frame-receipt.py <name> <frame.png> <transform.txt> "<picture line>" "<checked line>" ["<note line>"]

Reads <frame>.receipt.txt (build, binary sha256, time, exit) and
<frame>.reference-receipt.json (camera, world) beside the master PNG, plus the
transform printed by tools/encode.sh, and writes receipts/frame-<name>.txt.
Receipts name the machine class, never a host, user or path.
"""
import json, os, sys, textwrap

name, png, transform_path, picture, checked = sys.argv[1:6]
note = sys.argv[6] if len(sys.argv) > 6 else None
stem = png[:-4]
run = dict(line.split("=", 1) for line in open(stem + ".receipt.txt").read().split() if "=" in line)
when = [line for line in open(stem + ".receipt.txt").read().splitlines() if line[:2] == "20"][0]
ref = json.load(open(stem + ".reference-receipt.json"))
pose, world = ref["pose"], ref["world"]
lat, lon = pose["nad83"]
transform = open(transform_path).read().splitlines()


def field(key, text):
    lines = textwrap.wrap(text, 64) or [""]
    return "\n".join([f"{key:<10}{lines[0]}"] + [" " * 10 + line for line in lines[1:]])


def pm(value, unit=""):
    return "" if value is None else f" (+/- {value:g}{unit})"


# Each camera value is printed with the uncertainty its bookmark records, and no finer.
book = ref["bookmark"]["json"]
cam, ori, prov = book["camera"], book["orientation"], book["provenance"]
horizontal = cam.get("horizontalUncertaintyMetres")
azimuth = (pose["gridAzimuthDeg"] + pose["convergenceDeg"]) % 360
if horizontal is not None:
    position = f"{lat:.5f} N, {abs(lon):.5f} W{pm(horizontal, ' m')}"
else:
    position = (f"{lat:.5f} N, {abs(lon):.5f} W: the map location the photographer gave a public "
                f"photograph ({prov['author'].split(' (')[0]}, \"{prov['fileName']}\", Wikimedia Commons); "
                f"no GPS, error unknown")
fitted = "skyline" in ori["azimuthDegrees"]["method"]
camera = (f"{position}; {pose['aboveGround_m']:.1f} m above the ground{pm(cam['height']['uncertainty'], ' m')}; "
          f"azimuth {azimuth:.1f} deg true{pm(ori['azimuthDegrees']['uncertainty'], ' deg')}; "
          f"pitch {pose['pitchDeg']:.1f} deg{pm(ori['pitchDegrees']['uncertainty'], ' deg')}; "
          f"horizontal field of view {pose['hfovDeg']:.1f} deg{pm(book['intrinsics']['horizontalFOVDegrees']['uncertainty'], ' deg')}")
if fitted:
    camera += "; direction and pitch fitted to that photograph's terrain skyline. No pixel of it is used."

out = [
    field("picture", picture),
    field("build", f"{run['sha']}, release build"),
    field("binary", f"sha256 {run['bin_sha256']}"),
    field("rendered", f"{when.replace('T', ' ').replace('Z', ' UTC')}, Mac mini (Apple Silicon), exit {run['exit']}"),
    field("camera", camera),
    field("world", f"{world['geoWorld']}; tick {world['tick']}; world checksum {world['checksum']}"),
]
if note:
    out.append(field("note", note))
master = [line for line in transform if line.startswith("master")][0].split()[-1]
out.append(field("master", f"PNG, sha256 {master}"))
out.append(field("transform", [line for line in transform if line.startswith("transform")][0][len("transform "):]))
for line in transform:
    if line.startswith("published"):
        _, path, size, nbytes, _, _, sha = line.split()
        out.append(field("published", f"{os.path.basename(path)} {size} sha256 {sha}"))
out.append(field("checked", checked))
os.makedirs("receipts", exist_ok=True)
open(f"receipts/frame-{name}.txt", "w").write("\n".join(out) + "\n")
print(open(f"receipts/frame-{name}.txt").read())
