#!/bin/bash
# Encode one master image for the page: crop, resize, encode. Nothing else.
#
#   tools/encode.sh <master.png> <name> <crop w:h:x:y | none> <width>...
#
# Writes media/<name>/<name>-<w>.webp and .jpg for each width no larger than the
# cropped master (never upscaled), with all metadata stripped, and prints the transform
# for the receipt. No colour grade, retouch or sharpening is applied.
set -euo pipefail
master=$1; name=$2; crop=$3; shift 3
cd "$(dirname "$0")/.."
out=media/$name
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$out"

filter=""
[ "$crop" != none ] && filter="crop=$crop,"
ffmpeg -v error -nostdin -y -i "$master" -vf "${filter}format=rgb24" -frames:v 1 "$tmp/full.png"
full_w=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$tmp/full.png")
grey=$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 "$master")

echo "master    sha256 $(shasum -a 256 "$master" | cut -d' ' -f1)"
echo "transform crop ${crop}; resize lanczos; webp cwebp -q 82 -m 6 -metadata none; jpeg ffmpeg mjpeg q 3; no grade"
for w in "$@"; do
  [ "$w" -gt "$full_w" ] && { echo "skip ${w}: master is ${full_w} wide"; continue; }
  ffmpeg -v error -nostdin -y -i "$tmp/full.png" -vf "scale=${w}:-2:flags=lanczos" "$tmp/$w.png"
  cwebp -quiet -q 82 -m 6 -metadata none "$tmp/$w.png" -o "$out/$name-$w.webp"
  pix=yuvj420p; [[ "$grey" == gray* ]] && pix=gray
  ffmpeg -v error -nostdin -y -i "$tmp/$w.png" -map_metadata -1 -bitexact -pix_fmt "$pix" -q:v 3 "$out/$name-$w.jpg"
  h=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$tmp/$w.png")
  for f in "$out/$name-$w.webp" "$out/$name-$w.jpg"; do
    printf 'published %s %sx%s %s bytes sha256 %s\n' "$f" "$w" "$h" "$(stat -f %z "$f")" "$(shasum -a 256 "$f" | cut -d' ' -f1)"
  done
done
