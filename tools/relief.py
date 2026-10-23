#!/usr/bin/env python3
"""Draw the valley's relief from the engine's sealed terrain tiles (quinault-geo-v2).

Standard library only, so that anyone can re-run it and get the same pixels:

    python3 -I tools/relief.py <GeoData/quinault-v2> media/relief

It refuses to draw unless the manifest is the one the page names, and unless every
tile it reads matches the manifest's sha256. It writes:

    relief.png   8-bit grey hillshade of the fine (2 m) layer, 4 m per pixel
    relief.json  the inputs' hashes, the method, the pixel sha256 and the camera pins

Method, and nothing else: each 2 x 2 block of 2 m nodes is averaged into one 4 m cell;
the hillshade is Horn's (1981) slope and aspect, with the conventional light from
azimuth 315 deg at 45 deg altitude. Land is grey 24 + 231 * max(0, cos), so that only
lake and river nodes, whose lidar surface is hydro-flattened and whose bed is unknown,
are black (0). No colour, no atmosphere and no grade.
"""
import array, hashlib, json, math, os, struct, sys, zlib

MANIFEST_SHA256 = "14b0a41d853490763d1ba814067538353f445e2618f448d52c9e6b13de00e71c"
NODATA = -2**31
AZIMUTH_DEG, ALTITUDE_DEG = 315.0, 45.0
BLOCK = 2  # 2 m nodes per 4 m cell side
LAND_FLOOR = 24  # the darkest land grey; 0 is water only

# Cameras of the frames on the page, in the world frame (metres, +X east, +Z north),
# copied from each frame's reference receipt (pose.world_m).
PINS = [
    {"id": "lake", "label": "Lake Quinault, east end", "x_m": 2489.056195208711, "z_m": 20.296632949262857, "azimuth_deg": 265.41, "hfov_deg": 71.3},
    {"id": "clearing", "label": "The camp clearing", "x_m": 1798.0029992399755, "z_m": -524.00489179417491, "azimuth_deg": 180.0, "hfov_deg": 71.3},
    {"id": "canopy", "label": "The canopy from below", "x_m": 1800.0505985024522, "z_m": -416.3708773050457, "azimuth_deg": 0.0, "hfov_deg": 63.0},
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_tile(path):
    raw = open(path, "rb").read()
    if raw[:4] != b"BGT1":
        raise SystemExit(f"not a BGT1 tile: {path}")
    version, layer, ti, tj, spacing_mm, n, size = struct.unpack("<IiiiqII", raw[4:36])
    payload = zlib.decompress(raw[36:36 + size], -15)
    heights = array.array("i")
    heights.frombytes(payload[:4 * n * n])
    if sys.byteorder != "little":
        heights.byteswap()
    klass = payload[5 * n * n:6 * n * n]
    return n, spacing_mm, heights, klass


def png_grey(path, width, height, rows):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def png_rgb_up(path, width, height, rows):
    """8-bit RGB PNG, every row with filter 2 (Up)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    prev, raw = bytes(3 * width), bytearray()
    for r in rows:
        raw += b"\x02" + bytes((a - b) & 0xFF for a, b in zip(r, prev))
        prev = bytes(r)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


HEIGHT_UNIT_M = 0.05  # heightmap: R * 256 + G = height above NAVD88 0 in 5 cm steps; B = 255 for water


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    geo, out = sys.argv[1], sys.argv[2]
    manifest_path = os.path.join(geo, "manifest.json")
    if sha256_file(manifest_path) != MANIFEST_SHA256:
        raise SystemExit("REFUSED: manifest.json is not quinault-geo-v2 " + MANIFEST_SHA256[:12])
    manifest = json.load(open(manifest_path))
    fine = manifest["layers"]["fine"]
    n, side_mm = fine["nodesPerSide"], fine["tileSideMM"]
    step = n - 1
    i0, i1, j0, j1 = fine["tileMinI"], fine["tileMaxI"], fine["tileMinJ"], fine["tileMaxJ"]
    cols, rows_n = (i1 - i0 + 1) * step + 1, (j1 - j0 + 1) * step + 1

    # Stitch the 2 m lattice; tiles share their edge nodes. Row 0 is the south edge.
    grid = [None] * rows_n
    water = [None] * rows_n
    for r in range(rows_n):
        grid[r] = array.array("i", [NODATA]) * cols
        water[r] = bytearray(cols)
    used = []
    for t in sorted(fine["tiles"], key=lambda t: (t["j"], t["i"])):
        path = os.path.join(geo, t["file"])
        if sha256_file(path) != t["sha256"]:
            raise SystemExit("REFUSED: tile hash differs from the manifest: " + t["file"])
        used.append({"file": t["file"], "sha256": t["sha256"]})
        tn, spacing_mm, heights, klass = read_tile(path)
        if tn != n or spacing_mm != fine["spacingMM"]:
            raise SystemExit("REFUSED: tile shape differs from the manifest: " + t["file"])
        c0, r0 = (t["i"] - i0) * step, (t["j"] - j0) * step
        for k in range(n):
            g, w = grid[r0 + k], water[r0 + k]
            g[c0:c0 + n] = heights[k * n:(k + 1) * n]
            w[c0:c0 + n] = bytes(1 if c in (1, 2) else 0 for c in klass[k * n:(k + 1) * n])

    # Average 2 x 2 blocks into 4 m cells, north row first (image order).
    W, H = (cols - 1) // BLOCK, (rows_n - 1) // BLOCK
    cell_m = BLOCK * fine["spacingMM"] / 1000.0
    h4, w4 = [], []
    for y in range(H):
        rs = rows_n - 1 - (y * BLOCK)  # northmost row of this block
        a, b = grid[rs], grid[rs - 1]
        wa, wb = water[rs], water[rs - 1]
        hr, wr = array.array("d", bytes(8 * W)), bytearray(W)
        for x in range(W):
            c = x * BLOCK
            vals = [v for v in (a[c], a[c + 1], b[c], b[c + 1]) if v != NODATA]
            hr[x] = sum(vals) / (1000.0 * len(vals)) if vals else math.nan
            wr[x] = 1 if wa[c] + wa[c + 1] + wb[c] + wb[c + 1] >= 2 else 0
        h4.append(hr)
        w4.append(wr)

    # The 8 m heightmap the page lights live: 2 x 2 means of the 4 m cells.
    W8, H8 = W // 2, H // 2
    hm_rows, hm_min, hm_max = [], 1e9, -1e9
    for y in range(H8):
        a, b, wa, wb = h4[2 * y], h4[2 * y + 1], w4[2 * y], w4[2 * y + 1]
        row = bytearray(3 * W8)
        for x in range(W8):
            vals = [v for v in (a[2 * x], a[2 * x + 1], b[2 * x], b[2 * x + 1]) if not math.isnan(v)]
            h = sum(vals) / len(vals) if vals else 0.0
            hm_min, hm_max = min(hm_min, h), max(hm_max, h)
            v = max(0, min(65535, int(round(h / HEIGHT_UNIT_M))))
            row[3 * x], row[3 * x + 1] = v >> 8, v & 0xFF
            row[3 * x + 2] = 255 if wa[2 * x] + wa[2 * x + 1] + wb[2 * x] + wb[2 * x + 1] >= 2 else 0
        hm_rows.append(row)

    zenith = math.radians(90.0 - ALTITUDE_DEG)
    az = math.radians((360.0 - AZIMUTH_DEG + 90.0) % 360.0)
    cz, sz = math.cos(zenith), math.sin(zenith)
    out_rows, nodata_cells, water_cells = [], 0, 0
    for y in range(H):
        up, mid, dn = h4[max(y - 1, 0)], h4[y], h4[min(y + 1, H - 1)]
        row = bytearray(W)
        for x in range(W):
            if w4[y][x]:
                water_cells += 1
                continue
            xl, xr = max(x - 1, 0), min(x + 1, W - 1)
            a, b, c = up[xl], up[x], up[xr]
            d, f = mid[xl], mid[xr]
            g, h, i = dn[xl], dn[x], dn[xr]
            if any(map(math.isnan, (a, b, c, d, f, g, h, i, mid[x]))):
                nodata_cells += 1
                continue
            dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * cell_m)
            dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * cell_m)
            slope = math.atan(math.hypot(dzdx, dzdy))
            aspect = math.atan2(dzdy, -dzdx)
            shade = cz * math.cos(slope) + sz * math.sin(slope) * math.cos(az - aspect)
            row[x] = LAND_FLOOR + int(round((255 - LAND_FLOOR) * max(0.0, min(1.0, shade))))
        out_rows.append(row)

    black = sum(r.count(0) for r in out_rows)
    if black != water_cells + nodata_cells:
        raise SystemExit(f"REFUSED: {black} black cells, but {water_cells} water and {nodata_cells} no-data cells")
    os.makedirs(out, exist_ok=True)
    pixels = hashlib.sha256(b"".join(bytes(r) for r in out_rows)).hexdigest()
    png_grey(os.path.join(out, "relief.png"), W, H, out_rows)
    png_rgb_up(os.path.join(out, "height-8m.png"), W8, H8, hm_rows)
    # A 16 m copy for phones: 2 x 2 means of the 8 m heights, water if 2 of 4 are water.
    W16, H16 = W8 // 2, H8 // 2
    rows16 = []
    for y in range(H16):
        a, b = hm_rows[2 * y], hm_rows[2 * y + 1]
        row = bytearray(3 * W16)
        for x in range(W16):
            cells = [(r[3 * c] << 8 | r[3 * c + 1], r[3 * c + 2]) for r in (a, b) for c in (2 * x, 2 * x + 1)]
            v = int(round(sum(h for h, _ in cells) / 4))
            row[3 * x], row[3 * x + 1] = v >> 8, v & 0xFF
            row[3 * x + 2] = 255 if sum(1 for _, w in cells if w) >= 2 else 0
        rows16.append(row)
    png_rgb_up(os.path.join(out, "height-16m.png"), W16, H16, rows16)
    heightmap = {"file": "height-8m.png", "width": W8, "height": H8, "metresPerPixel": 2 * cell_m,
                 "encoding": f"R*256+G = height above NAVD88 0 in {HEIGHT_UNIT_M} m steps; B = 255 water",
                 "method": "2x2 mean of the 4 m cells; water if 2 of 4 are water",
                 "minHeight_m": round(hm_min, 2), "maxHeight_m": round(hm_max, 2),
                 "rgbSHA256": hashlib.sha256(b"".join(bytes(r) for r in hm_rows)).hexdigest(),
                 "phone": {"file": "height-16m.png", "width": W16, "height": H16, "metresPerPixel": 4 * cell_m,
                           "rgbSHA256": hashlib.sha256(b"".join(bytes(r) for r in rows16)).hexdigest()}}
    x_min_m = i0 * side_mm / 1000.0
    z_max_m = (j1 + 1) * side_mm / 1000.0
    pins = [dict(p, left_pct=round(100 * (p["x_m"] - x_min_m) / (W * cell_m), 2),
                 top_pct=round(100 * (z_max_m - p["z_m"]) / (H * cell_m), 2)) for p in PINS]
    report = {
        "format": "baryon-site-relief", "formatVersion": 1,
        "manifest": {"id": manifest["id"], "sha256": MANIFEST_SHA256},
        "layer": "fine", "tilesUsed": len(used),
        "tilesSHA256": hashlib.sha256("".join(t["sha256"] for t in used).encode()).hexdigest(),
        "extent_m": {"west": x_min_m, "east": x_min_m + W * cell_m, "south": z_max_m - H * cell_m, "north": z_max_m},
        "frame": manifest["frame"]["projection"],
        "pixels": {"width": W, "height": H, "metresPerPixel": cell_m, "greySHA256": pixels,
                   "waterCells": water_cells, "noDataCells": nodata_cells,
                   "blackCells": black, "landFloorGrey": LAND_FLOOR},
        "method": "2x2 block mean of the 2 m lattice; Horn (1981) hillshade, light azimuth 315 deg, altitude 45 deg; "
                  "land grey 24 + 231 * max(0, cos); lake and river nodes (hydro-flattened, bed unknown) black (0); "
                  "no colour, atmosphere or grade",
        "pins": pins,
        "heightmap": heightmap,
    }
    with open(os.path.join(out, "relief.json"), "w") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    print(f"RELIEF {W}x{H} at {cell_m} m, grey sha256 {pixels}, water {water_cells}, nodata {nodata_cells}")


if __name__ == "__main__":
    main()
