#!/usr/bin/env python3
"""Tests for tools/roadmap.py. Offline: no network, no credential.  python3 -I tools/test_roadmap.py"""
import hashlib, os, subprocess, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roadmap as R

# Test-only private words, so that no real one is written here; the gate's list stays hashed.
FAKE = {hashlib.sha256(w.encode()).hexdigest() for w in ("zqprivate", "zq-host")}
HOST = "." + "local"
HOME = "/" + "Users/"
TRACKS = [{"track": "Bodies", "issue": 1489}, {"track": "Forest", "issue": 1208}, {"track": "Engine"}]
GOOD = "Next: cadence from the body's own energy cost, stepping over logs, falls, and hands that grip."
MS = R.MILESTONES


def body(lines):
    return f"intro\n{MS[0]}\n" + "\n".join(lines) + f"\n{MS[1]}\ncomment-like text"


class Blocks(unittest.TestCase):
    def test_summary_reads_only_the_one_delimited_block(self):
        b = f"Intro.\n{R.SUMMARY[0]}\n  {GOOD}\n{R.SUMMARY[1]}\nOther."
        self.assertEqual(R.block_of(b), GOOD)
        self.assertIsNone(R.block_of(f"{R.SUMMARY[0]}a{R.SUMMARY[1]}{R.SUMMARY[0]}b{R.SUMMARY[1]}"))
        self.assertIsNone(R.block_of(None))

    def test_milestones_parse(self):
        chips, why = R.milestones_of(body(["in work: Measured persons walk", "next: Cadence from energy cost"]), FAKE)
        self.assertEqual(chips, [["in work", "Measured persons walk"], ["next", "Cadence from energy cost"]], why)

    def test_milestones_refusals(self):
        for lines, why in [
            (["passes today: Legs"], "not 'in work:'"),
            (["next: one two three four five six"], "over 5 words"),
            (["next: x" * 30], "over 5 words"),
            (["next: Legs pass" + "es"], "claims"),
            (["next: see https://x"], "URL"),
            (["next: ask agent-" + "a1b2" + "c3"], "id"),
            (["next: zqprivate legs"], "private"),
            ([], "0 milestones"),
            ([f"next: {i}" for i in range(6)], "6 milestones"),
        ]:
            with self.subTest(lines=lines[:1]):
                chips, err = R.milestones_of(body(lines), FAKE)
                self.assertIsNone(chips)
                self.assertIn(why, err)


class Problems(unittest.TestCase):
    def test_good_text_passes(self):
        self.assertEqual(R.problems(GOOD, FAKE), [])

    def test_refusals(self):
        for text, why in [
            ("see https://example.com", "URL"), ("<b>bold</b>", "markup"), ("re msg_" + "2a64353e088a", "id"),
            ("bare " + "a1b2" + "c3" + " here", "id"), ("on box" + HOST, "host"), ("in " + HOME + "x", "host"),
            ("x" * (R.MAX_CHARS + 1), "longer"), ("legs are done", "claims"), ("Zqprivate wrote", "private"),
        ]:
            with self.subTest(text=text[:30]):
                self.assertTrue(any(why in p for p in R.problems(text, FAKE)), R.problems(text, FAKE))


class Render(unittest.TestCase):
    blocks = {"Bodies": {"milestones": [["in work", "Spring legs"], ["next", "Falls & grips"]], "summary": "Long text."}}
    passes = {"Engine": [{"label": "Replay to the same checksum", "receipt": "replay"}]}
    drafts = {"Forest": [["next", "Trees grow"]], "Bodies": [["next", "ignored, owner has its own"]]}

    def test_pure_ordered_escaped(self):
        a = R.render(TRACKS, self.blocks, self.passes, self.drafts)
        self.assertEqual(a, R.render(TRACKS, dict(self.blocks), dict(self.passes), dict(self.drafts)))
        self.assertLess(a.index("Bodies"), a.index("Forest"))
        self.assertIn("Falls &amp; grips", a)
        self.assertNotIn("ignored", a)

    def test_only_hand_passes_claim_and_they_link_a_receipt(self):
        a = R.render(TRACKS, self.blocks, self.passes, self.drafts)
        self.assertEqual(a.count("is-pass"), 1)
        self.assertIn('href="#receipt-replay"', a)

    def test_draft_rows_are_marked(self):
        a = R.render(TRACKS, self.blocks, self.passes, self.drafts)
        def row(name):
            end = a.index(f">{name}<")
            return a[a.rindex('<li class="rm-row"', 0, end):end]
        self.assertIn("data-draft", row("Forest"))
        self.assertNotIn("data-draft", row("Bodies"))

    def test_no_data_leaves_markers_only(self):
        self.assertEqual(R.render(TRACKS, {}, {}, {}), f"{R.PAGE_BEGIN}\n{R.PAGE_END}")

    def test_apply_is_idempotent(self):
        page = f"head\n{R.PAGE_BEGIN}\n{R.PAGE_END}\ntail"
        frag = R.render(TRACKS, self.blocks, self.passes, self.drafts)
        once = R.apply(page, frag)
        self.assertEqual(R.apply(once, frag), once)


class KillSwitch(unittest.TestCase):
    def test_env_stops_everything(self):
        env = dict(os.environ, ROADMAP_SYNC_STOP="1")
        out = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(__file__), "roadmap.py"), "render"],
                             capture_output=True, text=True, env=env).stdout
        self.assertIn("STOPPED", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
