#!/usr/bin/env python3
"""Count flashes in a video (WCAG 2.3.1, general flash threshold). Exit 1 if any one-second
window holds more than 3.

    python3 -I tools/flashes.py <video>

Each frame is reduced by ffmpeg to an 8 x 8 grid of mean sRGB values; every cell is about
1.6 % of the frame, smaller than the 25 % of a 10-degree field WCAG allows at any viewing
distance, so a flash in any cell counts. A flash is a pair of opposing changes in relative
luminance of 10 % or more of the brighter value, while the darker state is below 0.80.
"""
import subprocess, sys

GRID = 8


def luminance(r, g, b):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def main(path):
    fps_text = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=avg_frame_rate", "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    num, den = (fps_text.split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={GRID}:{GRID}:flags=area,format=rgb24",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    size = GRID * GRID * 3
    frames = [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]
    worst, worst_at = 0, 0.0
    for cell in range(GRID * GRID):
        series = [luminance(*f[cell * 3:cell * 3 + 3]) for f in frames]
        # Find transitions: from the last extreme, a change of >= 10 % of the brighter value.
        events, anchor, direction = [], series[0] if series else 0, 0
        for t, y in enumerate(series):
            hi, lo = max(anchor, y), min(anchor, y)
            if hi - lo >= 0.10 * hi and lo < 0.80:
                d = 1 if y > anchor else -1
                if d != direction:
                    events.append(t)
                    direction = d
                anchor = y
            elif (direction == 1 and y > anchor) or (direction == -1 and y < anchor):
                anchor = y
        flashes = [events[i + 1] for i in range(0, len(events) - 1, 2)]
        window = max(1, int(round(fps)))
        for i, t in enumerate(flashes):
            count = sum(1 for u in flashes[i:] if u - t < window)
            if count > worst:
                worst, worst_at = count, t / fps
    print(f"FLASHES {path}: at most {worst} per second (at {worst_at:.2f} s), {len(frames)} frames at {fps:.2f} fps")
    return 0 if worst <= 3 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
