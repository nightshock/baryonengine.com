#!/usr/bin/env python3
"""The site's gate. Fails on anything that would break the page's rules.

    python3 -I tools/check.py            # a draft may carry DRAFT marks
    python3 -I tools/check.py --publish  # nothing marked DRAFT may remain, and history is clean

Checks:
 1. the Content-Security-Policy is exactly CSP below; every tag and attribute is parsed
    (any quoting), nothing is loaded from another origin, links out go only to LINKS_OUT,
    and neither the script nor the stylesheet names another origin or a network API;
 2. no private name appears in any file (compared as sha256 digests of lowercased words,
    so this file does not publish them), and no local path;
 3. every local reference exists;
 4. every receipt on the page equals its file in receipts/;
 5. every media file is in receipts/manifest.json with its sha256, and in a receipt;
 6. no published image or video carries EXIF, XMP, IPTC or QuickTime metadata;
 7. the map marks sit where receipts/relief.json puts them;
 8. the relief redraws to the same pixels from the sealed tiles, when the tiles are here;
 9. weight budgets;
10. at most 3 flashes per second in any video (WCAG 2.3.1), via tools/flashes.py.
"""
import hashlib, html, json, os, re, shutil, subprocess, sys, tempfile
from html.parser import HTMLParser

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PUBLISH = "--publish" in sys.argv
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; "
       "font-src 'self'; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'")
LINKS_OUT = ("https://creativecommons.org/licenses/by-nc-nd/4.0/", "https://opensource.org/license/mit",
             "https://github.com/nightshock/baryonengine.com")
URL_ATTRS = {"src", "srcset", "href", "action", "formaction", "poster", "data", "background", "cite",
             "manifest", "icon", "ping", "xlink:href", "imagesrcset"}
# sha256 of lowercased private words: people, hosts, the private repository, local folders.
PRIVATE = {
    "e2d279cba45ada22aa30991a04f8fcc7280c7250dcf6454a41e348de6d4627b1",
    "a3cdbe89034efbb167d3be3b5df0411a7b25cdf01d64119e2b422bb264d52801",
    "0bd4b96774868437f3e5efe58bb2b4d1e07307995b641ac0ec92b295260af437",
    "09d0611a8d1abb89e13c07cc79e5659c6318335d8f4d2c602ca708ea4cd4958d",
    "edb090ac874871dafe8c3724471e832c322d0ed7ebd0662b0589dd82eb2b2995",
    "be4b542241be62fed7a02ca672b1b1901678df0194b9a265fcc01a7b8f34c045",
    "d863fd51eb0d5ae2e4767165442c7c76a0f05f671c71bfdcef6fe4cf8f47ec77",
}
LOCAL = re.compile(r"(/Users/|/home/|~/|\blocalhost\b|127\.0\.0\.1|\.local\b|\[::1\])", re.I)
BUDGET_FIRST_KB = 24      # index.html + site.css + site.js + stage.js, gzip-compressed as served
BUDGET_HERO_KB = 250      # the frame behind the first screen, desktop WebP
BUDGET_MEDIA_MB = 8
failures = []


def fail(message):
    failures.append(message)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def private_words(text):
    """Every lowercased word, its parts split at - and ., and adjacent pairs of parts."""
    found = set()
    for word in re.findall(r"[\w.-]+", text.lower()):
        parts = [p for p in re.split(r"[-.]", word) if p]
        candidates = {word.strip(".-")} | set(parts) | {f"{a}-{b}" for a, b in zip(parts, parts[1:])} \
            | {f"{a}.{b}" for a, b in zip(parts, parts[1:])}
        found |= {c for c in candidates if hashlib.sha256(c.encode()).hexdigest() in PRIVATE}
    return found


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, [(k.lower(), v or "") for k, v in attrs]))

    handle_startendtag = handle_starttag


PAGES = ["index.html", "ru/index.html"]
css = open("assets/site.css").read()
js = open("assets/site.js").read() + "\n" + open("assets/stage.js").read()
page = "".join(open(p).read() for p in PAGES)  # for the checks that look across both pages
refs = set()

# 1. Origins, parsed, on every page.
for path in PAGES:
    here = os.path.dirname(path)
    parser = Tags()
    parser.feed(open(path).read())
    csp = [dict(a).get("content") for t, a in parser.tags if t == "meta" and dict(a).get("http-equiv", "").lower() == "content-security-policy"]
    if csp != [CSP]:
        fail(f"{path}: the Content-Security-Policy is not exactly the one in tools/check.py: {csp}")
    order = [t if not (t == "meta" and dict(a).get("http-equiv", "").lower() == "content-security-policy") else "csp"
             for t, a in parser.tags]
    if "csp" in order and any(t in ("link", "script", "img", "source", "video", "style") for t in order[:order.index("csp")]):
        fail(f"{path}: a resource is named before the Content-Security-Policy")
    for tag, attrs in parser.tags:
        if tag in ("iframe", "embed", "object", "form", "frame", "base", "applet", "portal"):
            fail(f"{path}: <{tag}> on the page")
        if tag == "meta" and dict(attrs).get("http-equiv", "").lower() == "refresh":
            fail(f"{path}: <meta http-equiv=refresh>")
        if tag == "script" and os.path.normpath(os.path.join(here, dict(attrs).get("src", "-"))).split(os.sep)[0] != "assets":
            fail(f"{path}: a script that is not one of ours in assets/")
        if tag == "style":
            fail(f"{path}: an inline <style> (the CSP forbids it)")
        for name, value in attrs:
            if name == "style":
                fail(f"{path}: a style attribute on <{tag}>")
            if name.startswith("on"):
                fail(f"{path}: an event handler {name} on <{tag}>")
            if name not in URL_ATTRS:
                continue
            for part in (value.split(",") if name.endswith("srcset") else [value]):
                url = part.strip().split(" ")[0]
                if not url or url.startswith("#"):
                    continue
                if re.match(r"^([a-z][a-z0-9+.-]*:|//)", url, re.I):
                    if tag == "a" and name == "href" and url.startswith(LINKS_OUT):
                        continue
                    fail(f"{path}: origin: <{tag} {name}={url}>")
                else:
                    refs.add(os.path.normpath(os.path.join(here, url.split("#")[0].split("?")[0])))
for label, body in (("site.css", css), ("site.js and stage.js", js)):
    for url in re.findall(r"(?:[a-z][a-z0-9+.-]*:)?//[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", body):
        fail(f"origin in {label}: {url}")
if re.search(r"@import|url\(\s*['\"]?(?![a-z0-9_./-]+['\"]?\s*\))", css, re.I):
    fail("@import or a non-local url() in site.css")
if re.search(r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|Worker|"
             r"localStorage|sessionStorage|indexedDB|cookie)\b|\bimport\s*\(", js):
    fail("site.js uses a network or storage API")

# 2. Private names, ids and local paths, in every file that would be published.
sys.path.insert(0, "tools")
from roadmap import ID  # noqa: E402  (one id rule for every public text)
listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                        capture_output=True, text=True).stdout.split()
for path in sorted(set(listed)):
    if not os.path.isfile(path) or path.startswith("media/"):
        continue
    body = open(path, errors="replace").read()
    words = private_words(body + " " + path)
    if words:
        fail(f"private name in {path} ({len(words)} word(s); digests in tools/check.py)")
    ids = ID.search(body)
    if ids and path != "tools/roadmap.py":  # roadmap.py defines the id rule
        fail(f"an agent, message or session id in {path}: {ids.group(0)}")
    if path not in ("tools/check.py", "tools/roadmap.py") and LOCAL.search(body):  # these two define the guards
        fail(f"a local path or host in {path}: {LOCAL.search(body).group(0)}")
if PUBLISH:
    history = subprocess.run(["git", "log", "--all", "-p", "--format=%an %ae%n%B"], capture_output=True, text=True).stdout
    if private_words(history):
        fail("the git history holds a private name: publish a clean single commit, not this history")

# Files our scripts load (images only: the CSP forbids any fetch).
for ref in re.findall(r'"(media/[A-Za-z0-9_./-]+)"', js):
    refs.add(ref)

# 3. Local references.
for ref in sorted(refs):
    if not os.path.exists(ref):
        fail(f"missing file: {ref}")

# 4. Both pages are exactly what tools/build.py makes from the template, the copy, the receipts,
#    the relief marks and the roadmap data.
import build  # noqa: E402
try:
    built = build.pages()
except SystemExit as refusal:
    fail(f"tools/build.py refuses: {refusal}")
    built = {}
for path, text in built.items():
    if not os.path.exists(path) or open(path).read() != text:
        fail(f"{path} differs from what tools/build.py makes (run it)")
copy = json.load(open("content/copy.json"))["copy"]
for key, v in copy.items():
    for lang in ("en", "ru"):
        text = v.get(lang, "")
        if not text.strip():
            fail(f"copy '{key}' has no {lang} text")
        elif ID.search(text) or re.search(r"https?:|www\.|[<>`]", text) or private_words(text):
            fail(f"copy '{key}' ({lang}) holds an id, link, markup or private name")
shown = dict(re.findall(r'<pre data-receipt="([a-z0-9-]+)">(.*?)</pre>', page, flags=re.S))

# 5. Manifest and receipts cover every media file.
manifest = json.load(open("receipts/manifest.json"))["files"]
receipts_text = "".join(open(os.path.join("receipts", n)).read() for n in os.listdir("receipts") if n.endswith(".txt"))
media = []
for root, _, names in os.walk("media"):
    media += [os.path.join(root, n) for n in names if not n.startswith(".")]
for path in sorted(media):
    digest = sha(path)
    if manifest.get(path) != digest:
        fail(f"manifest sha256 differs or is missing: {path}")
    if digest not in receipts_text:
        fail(f"no receipt names {path}")
    if path not in refs and not any(path in r for r in refs):
        fail(f"published but not on the page: {path}")
for path in manifest:
    if path not in media:
        fail(f"manifest names a file that is not here: {path}")

# 5b. Every asset is used: nothing ships that the pages do not load.
for name in sorted(os.listdir("assets")):
    path = os.path.join("assets", name)
    if path not in refs:
        fail(f"an asset the pages do not use: {path}")

# 6. Metadata.
if shutil.which("exiftool"):
    for path in sorted(media):
        out = subprocess.run(["exiftool", "-s", "-s", "-EXIF:all", "-XMP:all", "-IPTC:all", "-QuickTime:all",
                              "-ICC_Profile:all", "-Comment", "-Software", path], capture_output=True, text=True).stdout
        tags = [line for line in out.splitlines() if line.strip() and not line.startswith(("MajorBrand", "MinorVersion",
                "CompatibleBrands", "MovieHeader", "TimeScale", "Duration", "PreferredRate", "PreferredVolume",
                "PreviewTime", "PosterTime", "SelectionTime", "CurrentTime", "NextTrackID", "TrackHeader", "TrackID",
                "TrackDuration", "TrackLayer", "TrackVolume", "ImageWidth", "ImageHeight", "MediaHeader", "MediaTimeScale",
                "MediaDuration", "HandlerType", "HandlerDescription", "GraphicsMode", "OpColor", "CompressorID",
                "SourceImage", "XResolution", "YResolution", "BitDepth", "VideoFrameRate", "MatrixStructure",
                "MediaDataSize", "MediaDataOffset", "AudioFormat", "Balance", "SampleRate", "AudioChannels",
                "AudioBitsPerSample", "PixelAspectRatio", "ColorRepresentation", "Rotation", "AvgBitrate",
                "TrackCreateDate", "TrackModifyDate", "MediaCreateDate", "MediaModifyDate", "CreateDate",
                "ModifyDate", "MediaLanguageCode", "Encoder", "CompatibleBrands"))]
        if tags:
            fail(f"metadata in {path}: {tags[:4]}")
else:
    fail("exiftool is not installed, so metadata cannot be checked")

relief = json.load(open("receipts/relief.json"))

# 7b. The roadmap: owners' accepted blocks, hand-written passes with receipts, marked drafts.
import roadmap  # noqa: E402
tracks = roadmap.load("tracks.json", {})["tracks"]
blocks = roadmap.load("blocks.json", {"blocks": {}})["blocks"]
passes = roadmap.load("passes.json", {"passes": {}})["passes"]
drafts = roadmap.load("milestones-draft.json", {"drafts": {}})["drafts"]
for track, b in blocks.items():
    for state, _ in b.get("milestones", []):
        if state not in roadmap.STATES:
            fail(f"roadmap milestone for {track} has an unknown state: {state!r}")
    for text in [b.get("summary", "")] * bool(b.get("summary")) + [l for _, l in b.get("milestones", [])]:
        if roadmap.problems(text, limit=roadmap.MAX_CHARS):
            fail(f"roadmap text for {track} breaks a rule: {roadmap.problems(text)}")
for track, chips in drafts.items():
    for _, label in chips:
        if roadmap.problems(label, limit=roadmap.MAX_LABEL) or len(label.split()) > roadmap.MAX_WORDS:
            fail(f"drafted milestone for {track} breaks a rule: {label}")
for track, chips in passes.items():
    for p in chips:
        if not os.path.exists(f"receipts/{p['receipt']}.txt") or "DRAFT" in open(f"receipts/{p['receipt']}.txt").read():
            fail(f"a passes-today chip for {track} has no final receipt: {p['receipt']}")
        for path in PAGES:
            if f'id="receipt-{p["receipt"]}"' not in open(path).read():
                fail(f"{path}: a passes-today chip for {track} links a receipt that is not on the page: {p['receipt']}")
tests = subprocess.run([sys.executable, "-I", "-B", "tools/test_roadmap.py"], capture_output=True, text=True)
if tests.returncode != 0:
    fail("tools/test_roadmap.py failed")

# 8. Relief redraw.
geo = os.environ.get("BARYON_GEODATA_V2", "")  # the quinault-v2 terrain folder
if geo and os.path.exists(os.path.join(geo, "manifest.json")):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, "-I", "tools/relief.py", geo, tmp], check=True, capture_output=True)
        again = json.load(open(os.path.join(tmp, "relief.json")))
        if again != relief:
            fail("the relief redrawn from the tiles differs from receipts/relief.json")
        if sha(os.path.join(tmp, "relief.png")) not in open("receipts/relief.txt").read():
            fail("the redrawn relief.png sha256 is not the one in receipts/relief.txt")
elif PUBLISH:
    fail("--publish needs the relief redrawn from the tiles: set BARYON_GEODATA_V2")
else:
    print("note: BARYON_GEODATA_V2 not set to the terrain tiles, relief redraw skipped")

# 9. Budgets.
import gzip  # noqa: E402
first = sum(len(gzip.compress(open(p, "rb").read(), 9)) for p in ("index.html", "assets/site.css", "assets/site.js", "assets/stage.js")) / 1024
if first > BUDGET_FIRST_KB:
    fail(f"first-paint text {first:.0f} KB gzip > {BUDGET_FIRST_KB} KB")
hero = os.path.getsize("media/canopy/canopy-1440.webp") / 1024
if hero > BUDGET_HERO_KB:
    fail(f"first frame {hero:.0f} KB > {BUDGET_HERO_KB} KB")
total = sum(os.path.getsize(p) for p in media) / 2**20
if total > BUDGET_MEDIA_MB:
    fail(f"media {total:.1f} MB > {BUDGET_MEDIA_MB} MB")

# 10. Flashes.
videos = [p for p in media if p.endswith((".mp4", ".webm", ".mov"))]
for path in videos:
    run = subprocess.run([sys.executable, "-I", "tools/flashes.py", path], capture_output=True, text=True)
    if run.returncode != 0:
        fail(f"flashes: {path}: {run.stdout.strip() or run.stderr.strip()}")

# Draft marks.
if PUBLISH:
    if "data-draft" in page or "DRAFT" in receipts_text or 'name="robots" content="noindex"' in page:
        fail("draft marks remain (data-draft, DRAFT in a receipt, or noindex)")

print(f"CHECK first paint {first:.1f} KB gzip, first frame {hero:.0f} KB, media {total:.2f} MB in {len(media)} files, "
      f"{len(shown)} receipts, {len(videos)} videos")
if failures:
    print("CHECK FAILED")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("CHECK PASSED" + (" (publish)" if PUBLISH else " (draft)"))
