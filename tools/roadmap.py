#!/usr/bin/env python3
"""The roadmap picture: one row per track, 3-5 milestone chips each, kept current from GitHub.

    ROADMAP_SOURCE_REPO=<owner/repo> python3 -I tools/roadmap.py fetch   # read each epic's blocks, render
    python3 -I tools/roadmap.py render                                   # render roadmap/*.json into index.html

Rules, as the architect and RED-2 set them (2026-10-23):
- One source per track: the blocks an owner writes in the BODY of its epic issue. Comments are
  never read.
    <!-- roadmap-milestones:begin -->   1-5 lines "in work: <label>" or "next: <label>",
    <!-- roadmap-milestones:end -->     each label at most 5 words
    <!-- public-summary:begin -->       optional plain text, at most 600 characters,
    <!-- public-summary:end -->         shown only behind "More"
- Synced text never claims: an owner's chip is "in work" or "next". A "passes today" chip comes
  only from roadmap/passes.json, written by hand, and names a receipt in receipts/.
- Issue text is untrusted: plain text, escaped, no URLs, markup, ids, hosts, private names or
  claiming words. A block that breaks a rule is left out and logged.
- A pure function of roadmap/*.json: the same data gives the same bytes. No dates, only the order
  of roadmap/tracks.json.
- Until an owner writes its own milestones, roadmap/milestones-draft.json may hold chips the
  website owner drafted from that owner's text; such a row is marked DRAFT, and --publish fails.
- Kill switch: roadmap/STOP, or ROADMAP_SYNC_STOP set in the environment, stops everything.
"""
import hashlib, html, json, os, re, subprocess, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MAX_CHARS, MAX_WORDS, MAX_LABEL, MAX_CHIPS = 600, 5, 40, 5
SUMMARY = ("<!-- public-summary:begin -->", "<!-- public-summary:end -->")
MILESTONES = ("<!-- roadmap-milestones:begin -->", "<!-- roadmap-milestones:end -->")
PAGE_BEGIN, PAGE_END = "<!-- roadmap:begin -->", "<!-- roadmap:end -->"
STATES = {"in work": "work", "next": "next"}
# One id rule for every public text: agent-..., msg_..., sess_/hnd_..., or a bare 6-hex token
# with a digit and a letter (agent ids); colours (#0b0d0c) and longer hashes are not ids.
ID = re.compile(r"\bagent-[0-9a-f]{6}\b|\bmsg_[0-9a-f]{8,}\b|\b(?:sess|hnd)_[0-9a-f-]{8,}"
                r"|(?<![#0-9A-Fa-f])\b(?=[0-9a-f]{0,5}[0-9])(?=[0-9a-f]{0,5}[a-f])[0-9a-f]{6}\b(?![0-9A-Fa-f])", re.I)


def gate_digests():
    """The gate's sha256 digests of private words (tools/check.py, PRIVATE)."""
    src = open(os.path.join(ROOT, "tools", "check.py")).read()
    return set(re.findall(r'"([0-9a-f]{64})"', src[src.index("PRIVATE = {"):src.index("}", src.index("PRIVATE = {"))]))


def private_hits(text, digests=None):
    """Private names via digests (case-insensitive words and their parts); the gate's by default."""
    digests = gate_digests() if digests is None else digests
    found = set()
    for word in re.findall(r"[\w.-]+", text.lower()):
        parts = [p for p in re.split(r"[-.]", word) if p]
        for c in {word.strip(".-")} | set(parts) | {f"{a}-{b}" for a, b in zip(parts, parts[1:])}:
            if hashlib.sha256(c.encode()).hexdigest() in digests:
                found.add(c)
    return found


def problems(text, digests=None, limit=MAX_CHARS):
    """Why a text may not be published; empty when it may."""
    out = []
    if not text.strip():
        out.append("empty")
    if len(text) > limit:
        out.append(f"longer than {limit} characters")
    if re.search(r"https?:|www\.|\]\(|\bmailto:", text, re.I):
        out.append("a URL or link")
    if re.search(r"[<>`]|&[a-z]+;|\*\*|__", text):
        out.append("markup")
    if ID.search(text):
        out.append("an agent, message or session id")
    if re.search(r"\.local\b|/Users/|/home/|~/|localhost|127\.0\.0\.1", text):
        out.append("a host or local path")
    if re.search(r"\b(passes|passed|proven|verified|guaranteed|done|shipped|complete[ds]?)\b", text, re.I):
        out.append("a word that claims (passes, verified, done...): the roadmap only says what is in work or next")
    if private_hits(text, digests):
        out.append("a private name")
    return out


def between(body, marks):
    """The text between one pair of markers, or None. Exactly one pair is allowed."""
    begin, end = marks
    if body is None or body.count(begin) != 1 or body.count(end) != 1 or body.index(begin) > body.index(end):
        return None
    return body[body.index(begin) + len(begin):body.index(end)]


def block_of(body):
    """The owner's summary, whitespace-joined, or None."""
    text = between(body, SUMMARY)
    return None if text is None else " ".join(text.split())


def milestones_of(body, digests=None):
    """The owner's milestones as [[state, label]], or (None, why)."""
    text = between(body, MILESTONES)
    if text is None:
        return None, "no single milestones block"
    chips = []
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        state, _, label = line.partition(":")
        state, label = state.strip().lower(), " ".join(label.split())
        if state not in STATES:
            return None, f"a line that is not 'in work:' or 'next:' ({line[:30]})"
        if len(label.split()) > MAX_WORDS or len(label) > MAX_LABEL:
            return None, f"a label over {MAX_WORDS} words or {MAX_LABEL} characters ({label[:30]})"
        why = problems(label, digests, MAX_LABEL)
        if why:
            return None, f"a label refused ({'; '.join(why)})"
        chips.append([state, label])
    if not 1 <= len(chips) <= MAX_CHIPS:
        return None, f"{len(chips)} milestones; 1 to {MAX_CHIPS} are allowed"
    return chips, None


EN = {"pass": "passes today", "work": "in work", "next": "next", "more": "More", "epic": "epic", "receipt": "receipt",
      "draft_row": "Milestones drafted by the website owner from the track owner's text; the owner's own list replaces them",
      "note": ""}


def render(tracks, blocks, passes, drafts, words=EN):
    """Pure: the roadmap picture for the accepted data, in the order of tracks.json."""
    rows = []
    for t in tracks:
        name, b = t["track"], blocks.get(t["track"], {})
        owned = b.get("milestones")
        chips = [["pass", p.get("label_" + words.get("lang", "en"), p["label"]), p["receipt"]] for p in passes.get(name, [])]
        for s, label in (owned or drafts.get(name, [])):
            if s not in STATES:
                raise SystemExit(f"ROADMAP REFUSED: {name} has a milestone state that is not 'in work' or 'next': {s!r}")
            chips.append([STATES[s], label, None])
        if not chips or t.get("hold"):
            continue
        draft = not owned and name in drafts
        cells = []
        for state, label, receipt in chips[:MAX_CHIPS]:
            word = words[state]
            link = f' <a class="chip-receipt" href="#receipt-{html.escape(receipt)}">{html.escape(words["receipt"])}</a>' if receipt else ""
            cells.append(f'<li class="chip is-{state}"><span class="chip-state">{word}: </span>{html.escape(label)}{link}</li>')
        more = []
        if b.get("summary"):
            more.append(f"<p>{html.escape(b['summary'])}</p>")
        if t.get("issue"):
            more.append(f'<p class="issue">{html.escape(words["epic"])} #{int(t["issue"])}</p>')
        detail = f'<details class="rm-more"><summary>{html.escape(words["more"])}</summary>{"".join(more)}</details>' if more else ""
        flag = f' data-draft title="{html.escape(words["draft_row"], quote=True)}"' if draft else ""
        rows.append(f'      <li class="rm-row"{flag}><span class="rm-track">{html.escape(name)}</span>'
                    f'<ol class="rm-chips">{"".join(cells)}</ol>{detail}</li>')
    if not rows:
        return f"{PAGE_BEGIN}\n{PAGE_END}"
    note = f'\n    <p class="roadmap-note">{html.escape(words["note"])}</p>' if words.get("note") else ""
    return f'{PAGE_BEGIN}\n    <ol class="roadmap">\n' + "\n".join(rows) + f"\n    </ol>{note}\n    {PAGE_END}"


def apply(page, fragment):
    i, j = page.index(PAGE_BEGIN), page.index(PAGE_END) + len(PAGE_END)
    return page[:i] + fragment + page[j:]


def load(name, default):
    path = os.path.join(ROOT, "roadmap", name)
    return json.load(open(path)) if os.path.exists(path) else default


def fetch(tracks, log):
    """Read each epic's body with gh (read-only). Comments are never requested."""
    repo = os.environ["ROADMAP_SOURCE_REPO"]  # the private game repository; never written into this one
    blocks = {}
    for t in tracks:
        if not t.get("issue"):
            continue
        r = subprocess.run(["gh", "api", f"repos/{repo}/issues/{int(t['issue'])}", "--jq", ".body"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            log.append(f"{t['track']}: epic #{t['issue']} unreadable; left out")
            continue
        entry = {}
        chips, why = milestones_of(r.stdout)
        if chips:
            entry["milestones"] = chips
        else:
            log.append(f"{t['track']}: epic #{t['issue']} milestones left out ({why})")
        text = block_of(r.stdout)
        if text is not None:
            bad = problems(text)
            if bad:
                log.append(f"{t['track']}: epic #{t['issue']} summary refused ({'; '.join(bad)}); left out")
            else:
                entry["summary"] = text
        if entry:
            blocks[t["track"]] = entry
    return blocks


def main(argv):
    if os.path.exists(os.path.join(ROOT, "roadmap", "STOP")) or os.environ.get("ROADMAP_SYNC_STOP"):
        print("ROADMAP STOPPED by the kill switch; nothing changed")
        return 0
    tracks = load("tracks.json", {})["tracks"]
    log = []
    if argv[1:2] == ["fetch"]:
        blocks = fetch(tracks, log)
        with open(os.path.join(ROOT, "roadmap", "blocks.json"), "w") as f:
            json.dump({"format": "baryon-site-roadmap", "blocks": blocks}, f, indent=1, sort_keys=True, ensure_ascii=False)
            f.write("\n")
    else:
        blocks = load("blocks.json", {"blocks": {}})["blocks"]
    for line in log:
        print("ROADMAP", line)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build  # both pages are rendered from one template; see tools/build.py
    before = {p: open(os.path.join(ROOT, p)).read() if os.path.exists(os.path.join(ROOT, p)) else "" for _, p, _, _ in build.PAGES}
    build.main()
    after = {p: open(os.path.join(ROOT, p)).read() for _, p, _, _ in build.PAGES}
    owned = sum(1 for b in blocks.values() if b.get("milestones"))
    state = "no change" if before == after else "changed; review the diff before it merges"
    print(f"ROADMAP {state} ({owned} of {len(tracks)} tracks with their owners' milestones)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
