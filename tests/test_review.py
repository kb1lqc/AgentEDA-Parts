"""lib.review_status (checked / needs check / reference), the README Checked column and tools/review.py (page, server,
one-button stamp + PR with injected runners; no real git, gh or network)."""
import contextlib
import datetime
import io
import json
import os
import shutil
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import review as RV  # noqa: E402
import stamp as S  # noqa: E402
from lib import readme  # noqa: E402
from lib import review_status as RS  # noqa: E402
from test_ds_review import COMP, Base  # noqa: E402
from test_stamp import DAY, no_agent  # noqa: E402


class Stamped(Base):
    """A real ds_review record with X:iq human-stamped by alice and re-pinned (HUMAN_VERIFIED)."""

    def setUp(self):
        no_agent(self)
        super().setUp()
        self.assertEqual(self.run_r()[0], 0)
        rc, out = S.stamp(self.root, "alice", ["X:iq"], today=DAY)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.run_r()[0], 0)
        self.d = self.root / COMP


class Status(Stamped):
    def test_three_states_and_summary(self):
        st = RS.statuses(self.d, {"iq", "vos"})
        self.assertEqual((st["iq"], st["vos"], st["aol"]), (RS.CHECKED, RS.NEEDS, RS.REFERENCE))
        self.assertEqual(RS.summary("X", st), ("X: 1 of 2 used rows checked", False))
        self.assertEqual(RS.summary("X", RS.statuses(self.d, {"iq"})), ("X: 1 of 1 used rows checked", True))
        every = RS.statuses(self.d)  # use unknown: no reference rows
        self.assertNotIn(RS.REFERENCE, every.values())
        self.assertEqual(RS.summary("X", every, used_known=False), ("X: 1 of 7 rows checked", False))
        self.assertEqual(RS.summary("X", RS.statuses(self.d, set())), ("X: 0 of 0 used rows checked", False))

    def test_used_row_outside_the_toml_needs_check(self):
        st = RS.statuses(self.d, {"iq", "capacitance", "variant.V.iq"})
        self.assertEqual((st["capacitance"], st["variant.V.iq"]), (RS.NEEDS, RS.NEEDS))

    def test_checked_only_with_a_bound_stamp_and_human_verified(self):
        self.assertEqual(RS.checked_rows(self.d), {"iq": ("alice", "2026-11-20")})
        self.edit("typ = 1.2\nmax = 2", "typ = 1.2\nmax = 3")  # row changed after the stamp
        self.assertEqual(RS.checked_rows(self.d), {})
        self.edit("typ = 1.2\nmax = 3", "typ = 1.2\nmax = 2")
        led = self.rdir / "review.toml"
        text = led.read_text()
        led.write_text(text.replace('state = "HUMAN_VERIFIED"', 'state = "NEW"'))
        self.assertEqual(RS.checked_rows(self.d), {}, "ledger not HUMAN_VERIFIED: not checked")
        led.write_text(text)
        pdf = self.root / "docs/datasheets/x.pdf"
        pdf.write_bytes(pdf.read_bytes() + b"\n% changed\n")
        self.assertEqual(RS.checked_rows(self.d), {})  # local PDF differs
        self.assertEqual(RS.checked_rows(self.d, local_pdf=False), {"iq": ("alice", "2026-11-20")})  # ledger only

    def test_used_rows_and_component_dir(self):
        fam = self.root / "components/Acme/FAM"
        fam.mkdir(parents=True)
        (fam / "component.toml").write_text("")
        (fam / "variants.toml").write_text('[variant.FAM-1]\nmpn = "a"\n[variant.FAM-1.param.vth]\nmax = 1\n')
        got = RS.used_rows(self.root, ["X:iq", "X[sel]:vos", "FAM-1:vth", "FAM-1:abs",
                                       {"value": "X", "key": "aol", "input": "X:aol", "dir": COMP}])
        self.assertEqual(got, {self.d: {"iq", "vos", "aol"}, fam: {"variant.FAM-1.vth", "abs"}})
        self.assertEqual(RS.component_dir(self.root, "FAM-1"), (fam, "FAM-1"))
        with self.assertRaises(ValueError):
            RS.used_rows(self.root, ["Gone:x"])


class Readme(Stamped):
    def test_checked_column_and_summary_line(self):
        text = readme.build(self.d)
        self.assertIn("\nChecked by a person: 1 of 7 rows (docs/spec/review.md).\n", text)
        self.assertIn("| Cite | Checked |", text)
        iq = next(ln for ln in text.splitlines() if ln.startswith("| n iq |"))
        self.assertTrue(iq.endswith("| checked (alice, 2026-11-20) |"), iq)
        vos = next(ln for ln in text.splitlines() if ln.startswith("| n vos |"))
        self.assertTrue(vos.endswith("|  |"), vos)  # machine stamp: blank

    def test_same_without_pdf_and_cache(self):
        before = readme.build(self.d)
        (self.root / "docs/datasheets/x.pdf").write_bytes(b"other")
        self.assertEqual(readme.build(self.d), before)
        (self.root / "docs/datasheets/x.pdf").unlink()
        shutil.rmtree(self.root / ".review-cache")
        self.assertEqual(readme.build(self.d), before)


class Page(Stamped):
    def model(self, used=frozenset({"iq", "vos", "vos_bad", "nocite", "wrap", "absr", "capacitance"})):
        return RV.build_model(self.root, {self.d: set(used) if used is not None else None})

    def test_rows_tiers_and_tick_rules(self):
        (part,) = self.model()
        self.assertEqual(part["line"], "X: 1 of 7 used rows checked")
        tiers = {i["key"]: i["tier"] for i in part["items"]}
        self.assertEqual(tiers, {"vos": "tier 1", "wrap": "tier 2", "absr": "tier 3", "vos_bad": "fix", "nocite": "fix",
                                 "capacitance": "none"})
        self.assertEqual([i["key"] for i in part["items"]], ["vos", "wrap", "absr", "nocite", "vos_bad", "capacitance"])
        self.assertEqual(part["checked"], [("iq", "alice", "2026-11-20")])
        self.assertEqual(part["reference"], ["aol"])
        self.assertEqual(part["items"][2]["images"], [("evidence/table_p1_y67.png", "table or page")])
        vos = part["items"][0]
        self.assertIn("[param.vos]", vos["toml"])
        self.assertNotIn("verified", vos["toml"])
        self.assertEqual(vos["page"][1], "https://example.com/x.pdf#page=2")
        self.assertIn("status DISAGREE", next(i for i in part["items"] if i["key"] == "vos_bad")["why"])

    def test_render_plain_words_one_button(self):
        page = RV.render("Rows to check: B", self.model(), "TOK", self.root, block="B")
        self.assertIn('<div id="summary"><p><b>1 of 7 used rows checked</b></p>\n<p><a href="#part-X">X: 1 of 7 used rows '
                      'checked; 2 quick (row image), 1 need the page, 3 cannot be ticked yet</a></p></div>', page)
        self.assertLess(page.index('id="summary"'), page.index('class="item"'))  # the summary is the first screen
        self.assertIn('<h3 id="part-X">X: 1 of 7 used rows checked</h3>', page)
        self.assertIn("<p><b>Check: typ 10, max 35 uV (n vos); DS p.2, 6.5 Electrical Characteristics, x</b></p>", page)
        self.assertIn("<details><summary>Full TOML</summary><pre>[param.vos]", page)
        self.assertIn('rel="noreferrer noopener"', page)
        self.assertNotIn('rel="noopener"', page)
        self.assertIn("<img class=big ", page)  # table image: height capped
        self.assertNotIn("printed page n/a", page)
        self.assertIn('<button id="go" disabled>Stamp 0 rows and open PR</button>', page)
        self.assertIn("<details><summary>Already checked: 1 rows; not used by this block: 1 rows</summary>", page)
        self.assertEqual(page.count('class="ok"'), 3)  # vos, wrap, absr; fix and catalog rows have no tick box
        self.assertIn("data:image/png;base64,", page)
        for word in ("HUMAN_VERIFIED", "MACHINE_CHECKED", "PDF_CHANGED", "NOT_COVERED", "UNVERIFIED", "STALE"):
            self.assertNotIn(word, page)
        self.assertNotIn("verified =", page)

    def test_order_is_easiest_first_across_parts_and_released_line(self):
        import copy
        (x,) = self.model()
        a = copy.deepcopy(x)
        a.update(value="A", line="A: 0 of 1 used rows checked", k=0, n=1, items=[i for i in a["items"] if i["tier"] == "tier 3"])
        for i in a["items"]:
            i.update(part="A", ref="A:" + i["key"])
        r = copy.deepcopy(x)
        r.update(value="R", line="R: 2 of 2 used rows checked", released=True, items=[], k=2, n=2)
        page = RV.render("t", [a, x, r], "TOK", self.root, block="B")
        order = [page.index(f'id="row-{s}"') for s in ("X:vos", "X:wrap", "A:absr", "X:absr", "X:nocite", "X:capacitance")]
        self.assertEqual(order, sorted(order))
        self.assertIn('<a href="#part-R">R: 2 of 2 used rows checked. Released for B.</a>', page)
        self.assertIn("<b>3 of 10 used rows checked</b>", page)

    def test_value_mode_lists_every_unchecked_row(self):
        (part,) = self.model(used=None)
        self.assertEqual(part["line"], "X: 1 of 7 rows checked")
        self.assertEqual(part["reference"], [])
        self.assertEqual(len(part["items"]), 6)

    def test_ensure_cache_runs_ds_review_only_when_missing(self):
        calls = []
        run = lambda cmd, **kw: calls.append(cmd) or mock.Mock(stdout="ok\n", stderr="")  # noqa: E731
        self.assertEqual(RV.ensure_cache(self.root, [self.d], run), [])
        shutil.rmtree(self.root / ".review-cache")
        out = RV.ensure_cache(self.root, [self.d], run)
        self.assertEqual(calls, [[sys.executable, "tools/ds_review.py", COMP]])
        self.assertEqual(out[-1], "ok")

    def test_ensure_cache_dry_run_spawns_nothing(self):
        shutil.rmtree(self.root / ".review-cache")
        calls = []
        out = RV.ensure_cache(self.root, [self.d], lambda *a, **k: calls.append(a), dry_run=True)
        self.assertEqual(calls, [])
        self.assertEqual(out, [f"would run (dry run): {sys.executable} tools/ds_review.py {COMP}"])


class Fake:
    """Scripted runner: answers by command prefix, records every command."""

    def __init__(self, **over):
        self.calls = []
        self.status = iter([(0, "?? scratch.txt\n"),
                            (0, " M components/Acme/X/component.toml\n M components/Acme/X/review/review.toml\n"
                                " M components/Acme/X/README.md\n")])
        self.over = over

    def __call__(self, cmd):
        self.calls.append(cmd)
        name = {("git", "status"): "status", ("git", "rev-parse"): "rev", ("gh", "api"): "login",
                ("git", "fetch"): "fetch", ("git", "for-each-ref"): "refs", ("git", "switch"): "switch",
                ("git", "branch"): "branch", ("git", "add"): "add", ("git", "commit"): "commit",
                ("git", "push"): "push", ("gh", "pr"): "pr"}.get(tuple(cmd[:2]))
        if name is None:
            name = "stamp" if cmd[1].endswith("stamp.py") else "verify"
        if name == "switch" and cmd[2] != "-c":
            name = "switch_back"
        if name in self.over:
            r = self.over[name]
            return r(cmd) if callable(r) else r
        if name == "status":
            return next(self.status)
        return {"rev": (0, "main\n"), "login": (0, "alice\n"),
                "refs": (0, "refs/heads/review/x-alice-20261120\nrefs/remotes/origin/review/other\n"),
                "stamp": (0, "X:iq: (no stamp) -> human:alice ...\nnext: ...\n"), "verify": (0, "PASS\n"),
                "pr": (0, "Creating pull request\nhttps://github.com/o/r/pull/7\n")}.get(name, (0, ""))


class Publish(unittest.TestCase):
    root = Path("/lib")
    dirs = [Path("/lib/components/Acme/X"), Path("/lib/components/Acme/Y")]

    def go(self, fake, refs=("X:iq", "X:vos")):
        lines = []
        rc = RV.publish(self.root, self.dirs, list(refs), fake, lambda *ln: lines.extend(ln),
                        today=datetime.date(2026, 11, 20), python="py")
        return rc, lines, [c[:3] for c in fake.calls]

    def test_success_sequence(self):
        f = Fake(refs=(0, "refs/heads/review/x-alice-20261120\nrefs/remotes/origin/review/x-alice-20261120-2\n"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 0, lines)
        b = "review/x-alice-20261120-3"
        want = [["git", "status", "--porcelain"], ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                ["gh", "api", "user", "--jq", ".login"], ["git", "fetch", "origin"],
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/review/", "refs/remotes/origin/review/"],
                ["git", "switch", "-c", b, "origin/main"]]
        self.assertEqual(f.calls[:6], want)
        self.assertEqual(f.calls[6][:5], ["py", "tools/stamp.py", "--who", "alice", "--from"])
        self.assertFalse(os.path.exists(f.calls[6][5]), "the ref list is removed")
        self.assertEqual(f.calls[7], ["py", "tools/verify.py", "--regen", "components/Acme/X"])  # only stamped parts
        self.assertEqual(f.calls[9], ["git", "add", "--", "components/Acme/X/README.md",
                                      "components/Acme/X/component.toml", "components/Acme/X/review/review.toml"])
        self.assertEqual(f.calls[10][:3], ["git", "commit", "-m"])
        self.assertEqual(f.calls[10][3], "X: human check of 2 rows\n\nRows checked on the datasheet page image "
                                         "(tools/review.py):\n- X:iq\n- X:vos")
        self.assertEqual(f.calls[11], ["git", "push", "-u", "origin", b])
        self.assertEqual(f.calls[12][:7], ["gh", "pr", "create", "--base", "main", "--head", b])
        self.assertIn("- X:iq\n- X:vos", f.calls[12][-1])
        self.assertEqual(lines[-1], "PR: https://github.com/o/r/pull/7")
        self.assertIn("$ git switch -c " + b + " origin/main", lines)  # each command is shown

    def test_dirty_tree_refused(self):
        f = Fake(status=(0, " M lib/x.py\n?? new.txt\n"))
        rc, lines, calls = self.go(f)
        self.assertEqual((rc, calls), (1, [["git", "status", "--porcelain"]]))
        self.assertIn("uncommitted changes (lib/x.py)", lines[-1])
        self.assertIn("Commit or stash them", lines[-1])

    def test_early_failures_change_nothing(self):
        for name, reply, want in (("status", (128, "fatal"), "git status failed"),
                                  ("login", (1, "not logged in"), "gh auth login"),
                                  ("login", (0, "bad name!\n"), "no GitHub login"),
                                  ("fetch", (1, "no network"), "git fetch origin failed"),
                                  ("switch", (128, "exists"), "could not create branch")):
            f = Fake(**{name: reply})
            rc, lines, calls = self.go(f)
            self.assertEqual(rc, 1, name)
            self.assertIn(want, lines[-1])
            self.assertNotIn(["py", "tools/stamp.py", "--who"], calls)

    def test_detached_head_returns_to_the_commit(self):
        f = Fake(rev=lambda c: (0, "HEAD\n") if "--abbrev-ref" in c else (0, "abc123\n"), stamp=(1, "refused X:iq: ...\n"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn(["git", "switch", "abc123"], f.calls)

    def test_stamp_refusal_switches_back_and_deletes_branch(self):
        f = Fake(stamp=(1, "refused X:iq: status DISAGREE\nnothing written\n"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertEqual(f.calls[-2:], [["git", "switch", "main"], ["git", "branch", "-D", "review/x-alice-20261120-2"]])
        self.assertIn("refused X:iq: status DISAGREE", lines)
        self.assertIn("Back on main, branch review/x-alice-20261120-2 deleted. Nothing was stamped.", lines[-1])

    def test_stamp_refusal_with_failed_cleanup_says_so(self):
        f = Fake(stamp=(1, "refused\n"), branch=(1, "error: cannot delete"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn("cleanup failed", lines[-1])
        self.assertIn("delete branch review/x-alice-20261120-2 yourself", lines[-1])

    def test_verify_failure_leaves_branch_uncommitted(self):
        f = Fake(verify=(1, "FAIL components/Acme/X/component.toml:3 bad\nlog: /tmp/zl-verify-1\n"))
        rc, lines, calls = self.go(f)
        self.assertEqual(rc, 1)
        self.assertEqual(calls[-1][:2], ["py", "tools/verify.py"])  # no commit, no switch back
        self.assertIn("log: /tmp/zl-verify-1", lines)
        self.assertIn("not committed", lines[-1])

    def test_unexpected_changes_not_committed(self):
        f = Fake()
        f.status = iter([(0, ""), (0, " M components/Acme/X/component.toml\n M lib/readme.py\n")])
        rc, lines, calls = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn("unexpected changes (lib/readme.py)", lines[-1])
        self.assertNotIn(["git", "add", "--"], calls)

    def test_commit_push_pr_failures(self):
        for name, want in (("commit", "commit failed"), ("push", "push failed"), ("pr", "gh pr create failed")):
            f = Fake(**{name: (1, "boom")})
            rc, lines, _ = self.go(f)
            self.assertEqual(rc, 1, name)
            self.assertIn(want, lines[-1])

    def test_pr_create_failure_with_a_url_is_a_failure(self):
        f = Fake(pr=(1, "https://github.com/o/r/pull/7\nerror: something else failed"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn("gh pr create failed", lines[-1])
        self.assertNotIn("PR: https://github.com/o/r/pull/7", lines)

    def test_dry_runner_shows_every_step(self):
        lines = []
        run = RV.dry_runner()
        rc = RV.publish(self.root, self.dirs, ["X:iq"], run, lambda *ln: lines.extend(ln),
                        today=datetime.date(2026, 11, 20), python="py")
        self.assertEqual(rc, 0, lines)
        cmds = [ln for ln in lines if ln.startswith("$ ")]
        self.assertEqual(len(cmds), 13)
        self.assertEqual(lines[-1], "PR: https://github.com/OWNER/zener-library/pull/0")
        self.assertIn("$ git add -- components/Acme/X/README.md components/Acme/X/component.toml "
                      "components/Acme/X/review/review.toml", lines)  # only the stamped part


class Server(unittest.TestCase):
    def setUp(self):
        self.jobs = []

        def job(refs, emit):
            self.jobs.append(refs)
            emit("$ git fetch origin", "PR: https://github.com/o/r/pull/1")
            return 0
        self.app = RV.App("<p>{TOKEN}</p>", ["X:iq", "X:vos"], job)
        threading.Thread(target=self.app.server.serve_forever, daemon=True).start()
        self.addCleanup(self.app.server.server_close)
        self.addCleanup(self.app.server.shutdown)

    def req(self, path, data=None, headers=None, token=True):
        url = f"{self.app.origin}{path}" + (f"?t={self.app.token}" if token else "")
        r = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def post(self, refs, **headers):
        return self.req("/stamp", json.dumps({"refs": refs}).encode(), {"Content-Type": "application/json", **headers})

    def test_token_host_origin(self):
        self.assertEqual(self.req("/", token=False)[0], 403)
        self.assertEqual(self.req("/")[0:2], (200, f"<p>{self.app.token}</p>"))
        self.assertEqual(self.req("/", headers={"Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.post(["X:iq"], Origin="https://evil.example")[0], 403)
        self.assertEqual(self.req("/stamp", b"{}", {"Content-Type": "application/json"}, token=False)[0], 403)
        self.assertEqual(self.jobs, [])

    def test_body_rules(self):
        self.assertEqual(self.req("/stamp", b'{"refs": ["X:iq"]}', {"Content-Type": "text/plain"})[0], 400)
        for refs in ([], ["X:other"], ["X:iq", "X:iq"], "X:iq", [1]):
            self.assertEqual(self.post(refs)[0], 400, refs)
        self.assertEqual(self.jobs, [])

    def test_one_job_streams_then_finishes(self):
        code, text = self.post(["X:iq"], Origin=self.app.origin)
        self.assertEqual((code, text), (200, "$ git fetch origin\nPR: https://github.com/o/r/pull/1\n"))
        self.assertTrue(self.app.finished.is_set())
        self.assertEqual((self.jobs, self.app.rc), ([["X:iq"]], 0))
        self.assertEqual(self.post(["X:vos"])[0], 409)

    def test_done(self):
        self.assertEqual(self.req("/done", b"")[0], 200)
        self.assertTrue(self.app.finished.is_set())

    def test_done_refused_once_a_job_started(self):
        gate, seen = threading.Event(), []

        def slow(refs, emit):
            emit("$ git fetch origin")
            gate.wait(10)
            return 0
        self.app.job = slow
        t = threading.Thread(target=lambda: seen.append(self.post(["X:iq"])))
        t.start()
        for _ in range(100):
            if self.app.started:
                break
            threading.Event().wait(0.05)
        self.assertEqual(self.req("/done", b"")[0], 409)  # mid-run: the server does not stop
        self.assertFalse(self.app.finished.is_set())
        gate.set()
        t.join(10)
        self.assertEqual(seen[0][0], 200)
        self.assertTrue(self.app.finished.is_set())

    def test_page_disables_done_when_the_run_starts(self):
        self.assertIn("go.disabled=true; done.disabled=true;", RV.JS)


class Main(unittest.TestCase):
    def test_refused_inside_claude_code_unless_dry_run(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), contextlib.redirect_stdout(buf):
            self.assertEqual(RV.main(["X"]), 1)
        self.assertEqual(buf.getvalue().strip(), RV.AGENT)

    def test_block_or_values(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": ""}), contextlib.redirect_stderr(io.StringIO()):
            for argv in ([], ["--block", "B", "X"]):
                with self.assertRaises(SystemExit):
                    RV.main(argv)

    def test_deny_rules_match_stamp(self):
        deny = json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]["deny"]
        stamp = [d for d in deny if "stamp.py" in d]
        self.assertTrue(stamp)
        self.assertEqual(sorted(d.replace("stamp.py", "review.py") for d in stamp), sorted(d for d in deny if "review.py" in d))

    def test_default_blocks_repo(self):
        self.assertIn(RV.default_blocks_repo(ROOT).name, ("ina229", "circuit-blocks"))


if __name__ == "__main__":
    unittest.main()
