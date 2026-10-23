#!/usr/bin/env python3
"""Build both pages, English and Russian, from one template and one copy file.

    python3 -I tools/build.py

- templates/page.html holds the structure; content/copy.json every visible word, by id, in
  both languages. The Russian says no more than the English; RED-2 checks parity by id.
- Receipts are copied in verbatim, in English, on both pages.
- The map marks are drawn from receipts/relief.json; the roadmap from roadmap/*.json.
- receipts/manifest.json gets the sha256 of every file under media/.
A pure function of those files: the same inputs give the same bytes. tools/check.py rebuilds
in memory and fails if a page on disk differs.
"""
import hashlib, html, json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
from marks import marks  # noqa: E402
import roadmap  # noqa: E402

PAGES = [  # language, path, root of assets, the other page
    ("en", "index.html", "", ("ru", "ru/")),
    ("ru", "ru/index.html", "../", ("en", "../")),
]


def read(path):
    return open(os.path.join(ROOT, path), encoding="utf-8").read()


def page(lang, root, other):
    copy = json.load(open(os.path.join(ROOT, "content", "copy.json"), encoding="utf-8"))["copy"]
    t = read("templates/page.html")
    words = {k: v[lang] for k, v in copy.items()}
    fixed = {"root": root, "lang": lang, "lang_other": other[0], "lang_href": other[1],
             "href_en": "./" if lang == "en" else "../", "href_ru": "ru/" if lang == "en" else "./"}

    def fill(m):
        key = m.group(1)
        if key in fixed:
            return fixed[key]
        if key not in words:
            raise SystemExit(f"BUILD REFUSED: no copy for {{{{{key}}}}}")
        return html.escape(words[key], quote=True)
    t = re.sub(r"{{([a-z_0-9]+)}}", fill, t)

    def receipt(m):
        text = read(f"receipts/{m.group(1)}.txt").rstrip("\n")
        return f'<pre data-receipt="{m.group(1)}">{html.escape(text, quote=False)}</pre>'
    t = re.sub(r'<pre data-receipt="([a-z0-9-]+)"></pre>', receipt, t)

    relief = json.load(open(os.path.join(ROOT, "receipts", "relief.json")))
    labels = {"frame": words["frame_word"], "lake": words["pin_lake"], "clearing": words["pin_clearing"],
              "canopy": words["pin_canopy"]}
    t = t.replace("<!-- marks:begin -->\n", "<!-- marks:begin -->\n" + marks(relief, labels) + "\n", 1)

    load = roadmap.load
    rm = roadmap.render(load("tracks.json", {})["tracks"], load("blocks.json", {"blocks": {}})["blocks"],
                        load("passes.json", {"passes": {}})["passes"], load("milestones-draft.json", {"drafts": {}})["drafts"],
                        {"pass": words["state_pass"], "work": words["state_work"], "next": words["state_next"],
                         "more": words["more"], "epic": words["epic"], "draft_row": words["draft_row"],
                         "receipt": words["receipt"], "note": words["roadmap_note"] if lang != "en" else "", "lang": lang})
    return roadmap.apply(t, rm)


def pages():
    return {path: page(lang, root, other) for lang, path, root, other in PAGES}


def main():
    built = pages()
    for path, text in built.items():
        os.makedirs(os.path.dirname(os.path.join(ROOT, path)) or ROOT, exist_ok=True)
        open(os.path.join(ROOT, path), "w", encoding="utf-8").write(text)
    files = {}
    for base, _, names in os.walk(os.path.join(ROOT, "media")):
        for name in sorted(names):
            if not name.startswith("."):
                full = os.path.join(base, name)
                files[os.path.relpath(full, ROOT)] = hashlib.sha256(open(full, "rb").read()).hexdigest()
    with open(os.path.join(ROOT, "receipts", "manifest.json"), "w") as f:
        json.dump({"format": "baryon-site-manifest", "files": dict(sorted(files.items()))}, f, indent=1)
        f.write("\n")
    print(f"BUILD {', '.join(built)}; manifest of {len(files)} media files")


if __name__ == "__main__":
    main()
