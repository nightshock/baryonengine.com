# baryonengine.com

The website of Baryon Engine: one static page, its pictures and the receipts behind
every claim on it.

## Rules of this repository

- **Pixels:** only the engine's own renders, plus the relief drawn here from its
  terrain tiles. No person in any frame, and no third-party, stock or generated
  imagery. A frame is only cropped, resized and encoded: no grade, retouch or
  sharpening.
- **Claims:** only what passes its exam today, each with a receipt in `receipts/`
  that quotes the exam's output, commit, date and machine.
- **Nothing leaves the page:** no analytics, cookies, third-party scripts, fonts or
  embeds. The Content-Security-Policy forbids every other origin, and the page works
  without JavaScript.

## Layout

```
index.html, ru/index.html   the page in English and Russian, both built by tools/build.py
templates/page.html          the structure; content/copy.json holds every visible word, by id
assets/                      site.css, site.js (copy buttons), stage.js (the lit relief), icon.svg
media/<name>/                published images, from tools/encode.sh; heightmaps from tools/relief.py
receipts/<id>.txt            each receipt, copied verbatim (English) into both pages
receipts/manifest.json       sha256 of every published file
receipts/relief.json         the relief's inputs, method, pixel hash and map marks
roadmap/                     tracks.json (rows), blocks.json (owners' milestones), passes.json (receipted chips)
tools/                       build, check, relief, encode, frame-receipt, roadmap, marks, flashes
```

## Making a change

```sh
python3 -I tools/build.py                                     # both pages, marks, roadmap, manifest
python3 -I tools/check.py                                     # the gate; --publish before release
ROADMAP_SOURCE_REPO=<owner/repo> python3 -I tools/roadmap.py fetch   # owners' milestones, read-only
tools/encode.sh <master.png> <name> <crop|none> <widths...>   # a new frame; then tools/frame-receipt.py
```

`tools/relief.py <GeoData/quinault-v2> <out>` redraws the relief and heightmaps from the sealed
terrain tiles; `check.py` redraws them when `BARYON_GEODATA_V2` names that folder, and
`--publish` requires it.

## Licences

Code: MIT (`LICENSE`). Pictures and text: CC BY-NC-ND 4.0 (`LICENSE-media.md`).
Terrain: USGS 3D Elevation Program and National Hydrography Dataset, public domain.
