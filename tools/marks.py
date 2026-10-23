"""The map marks: each frame's camera and the field it sees, drawn from receipts/relief.json."""
import html, math


def marks(relief, names=None):
    """SVG marks in map metres: x east from the west edge, y south from the north edge."""
    west, north = relief["extent_m"]["west"], relief["extent_m"]["north"]
    frames = {"lake": (1, "ne"), "clearing": (2, "sw"), "canopy": (3, "nw")}
    labels = {"ne": (10, -10, "start"), "nw": (-10, -10, "end"), "sw": (-10, 20, "end")}
    names = names or {"frame": "Frame"}
    out, reach = [], 700.0
    for pin in relief["pins"]:
        n, corner = frames[pin["id"]]
        x, y = pin["x_m"] - west, north - pin["z_m"]
        a1, a2 = (math.radians(pin["azimuth_deg"] + d * pin["hfov_deg"] / 2) for d in (-1, 1))
        x1, y1 = x + reach * math.sin(a1), y - reach * math.cos(a1)
        x2, y2 = x + reach * math.sin(a2), y - reach * math.cos(a2)
        lx, ly, anchor = labels[corner]
        out.append(
            f'<a class="mark" href="#frame-{n}" aria-label="{html.escape(names["frame"])} {n}: {html.escape(names.get(pin["id"], pin["label"]))}">'
            f'<path class="cone" pathLength="1" d="M{x:.1f} {y:.1f}L{x1:.1f} {y1:.1f}A{reach:.0f} {reach:.0f} 0 0 1 {x2:.1f} {y2:.1f}Z"/>'
            f'<g transform="translate({x:.1f} {y:.1f})"><g class="mark-scale"><circle r="5.5"/>'
            f'<text x="{lx}" y="{ly}" text-anchor="{anchor}">{n}</text></g></g></a>')
    return "\n".join(out)
