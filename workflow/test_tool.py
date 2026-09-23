#!/usr/bin/env python3
"""Tests for the workflow itself: runs the whole cycle in a throwaway copy of this project.

  python workflow/test_tool.py

Run it after any change in workflow/. It never touches the project; everything happens in a temporary folder.
"""
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
results = []


def ok(name, cond, detail=""):
    results.append((name, bool(cond), detail))


def run(root, *args):
    r = subprocess.run([sys.executable, "workflow/tool.py", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8")
    return r.returncode, r.stdout + r.stderr


def git(root, *args):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root,
                          capture_output=True, text=True).returncode


def read(root, f):
    return (root / f).read_text(encoding="utf-8")


def write(root, f, text):
    (root / f).parent.mkdir(parents=True, exist_ok=True)
    (root / f).write_text(text, encoding="utf-8")


def entries(root, draft, text):
    t = read(root, draft)
    write(root, draft, t.replace("---\n\n## Pushed objectives", text.strip("\n") + "\n\n---\n\n## Pushed objectives", 1))


def mapdata(root, f):
    m = re.search(r"var DATA=(\{.*?\n\});", read(root, f), re.S)
    return json.loads(m.group(1))


def nodes(root, f):
    return {n.get("ref") or n["id"]: n for n in mapdata(root, f)["nodes"]}


def fill_review(root, f, version, accepted="", not_accepted=""):
    t = read(root, f)
    t = re.sub(r"^- Version:.*$", f"- Version: {version}", t, flags=re.M)
    t = re.sub(r"^- Date:.*$", "- Date: 2026-01-01", t, flags=re.M)
    t = re.sub(r"^- Reviewed by:.*$", "- Reviewed by: Test Reviewer", t, flags=re.M)
    t = re.sub(r"^- Accepted:.*$", f"- Accepted: {accepted}", t, flags=re.M)
    t = re.sub(r"^- Not accepted:.*$", f"- Not accepted: {not_accepted}", t, flags=re.M)
    write(root, f, t)


def commit(root, msg, tag=None):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)
    if tag:
        git(root, "tag", tag)


BACKLOG = """# Backlog

**Status:** Backlog
**Map:** [backlog-map.html](backlog-map.html)

## Overview

<!-- BEGIN GENERATED: tree -->
<!-- END GENERATED: tree -->

## Inbox

Nothing yet.

## Entries

---

## Bugs

## Dropped

Nothing yet.

## Pushed objectives and problems

<!-- BEGIN GENERATED: copied -->
<!-- END GENERATED: copied -->
"""


def blank_project(root):
    """A new, empty project that uses this workflow: its own workflow/ files and nothing of the real project's."""
    shutil.copytree(SRC / "workflow", root / "workflow", ignore=shutil.ignore_patterns("__pycache__"))
    if (SRC / "prototype" / "trace").exists():
        shutil.copytree(SRC / "prototype" / "trace", root / "prototype" / "trace")
    for doc, title in (("objectives", "Objectives"), ("problems", "Problems"), ("solutions", "Solutions")):
        write(root, f"plan/{doc}.md", f"# {title}\n\n---\n")
    write(root, "plan/prototype.md", "# Prototype\n")
    write(root, "plan/constraints.md", "# Constraints\n")
    write(root, "drafts/backlog.md", BACKLOG)
    write(root, "versions/log.md", "# Version log\n\n---\n")
    write(root, "product/README.md", "# Product\n")
    write(root, "prototype/REVIEW.md", read(root, "workflow/review-template.md"))
    run(root, "new-draft", "v0.1")


def main():
    tmp = Path(tempfile.mkdtemp())
    root = tmp / "proj"
    blank_project(root)
    git(root, "init", "-q", "-b", "main")
    commit(root, "start")
    try:
        cycle(root)
    except Exception as e:  # a crash is a failure too, but the results so far are still shown
        import traceback
        ok("the whole cycle ran to the end", False, traceback.format_exc(limit=3) + str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for name, good, detail in results:
        if not good:
            errs = [l.strip() for l in detail.split("\n") if "ERROR" in l]
            detail = " | ".join(errs) if errs else detail.replace("\n", " | ")[-600:]
        print(("PASS " if good else "FAIL ") + name + ("" if good else "  <<" + detail))
    failed = sum(not g for _, g, _ in results)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


def cycle(root):
    src = read(root, "workflow/tool.py")
    try:
        ast.parse(src, feature_version=(3, 8))
        ok("the tool parses as Python 3.8", True)
    except SyntaxError as e:
        ok("the tool parses as Python 3.8", False, str(e))
    code, out = run(root, "check")
    ok("a fresh project checks clean", code == 0 and "0 errors, 0 to do, 0 warnings" in out, out)

    # ------------------------------------------------------------------ v0.1: first draft, apply-draft, push
    entries(root, "drafts/draft-v0.1.md", '''
### Goal A
- Type: Objective
- Description: First objective.

### Pain 1
- Type: Problem
- Description: A problem.
- Serves: "Goal A"
- Open questions: Who feels it most?

### Pain 2
- Type: Problem
- Description: Another problem.
- Serves: "Goal A"

### Fix 1
- Type: Solution
- Description: A solution.
- Serves: "Pain 1"
- Also serves: "Pain 2"

### Part 1
- Type: Sub-solution
- Description: A part.
- Serves: "Fix 1"

### Button
- Type: Feature
- Description: A button.
- Serves: "Part 1"
- Done when: Pressing it saves the form.
- Design location: form page

### List
- Type: Feature
- Description: A list.
- Serves: "Fix 1"
- Needs: "Button"
- Done when: Saved forms appear in the list.
- Design location: home page

### Maybe later
- Type: Feature
- Description: Not approved this time.
- Serves: "Fix 1"
- Done when: Something.
''')
    run(root, "build")
    t = read(root, "drafts/draft-v0.1.md")
    write(root, "drafts/draft-v0.1.md", t.replace("- Done when: Pressing it saves the form.\n", ""))
    run(root, "build")
    code, out = run(root, "check", "--push", "v0.1")
    ok('check --push requires "Done when"', code != 0 and 'has no "Done when"' in out, out)
    write(root, "drafts/draft-v0.1.md", t)
    run(root, "build")
    code, out = run(root, "check", "--push", "v0.1")
    ok("the complete draft passes check --push", code == 0, out)

    code, out = run(root, "apply-draft", "--skip", "Maybe later", "--dry-run")
    ok("apply-draft --dry-run shows the new IDs and writes nothing", code == 0 and "O-001 Goal A" in out
       and "## O-001: Goal A" not in read(root, "plan/objectives.md"), out)
    code, out = run(root, "apply-draft", "--skip", "Maybe later")
    ok("apply-draft runs", code == 0, out)
    sol = read(root, "plan/solutions.md")
    ok("apply-draft: IDs and links written as IDs", "## S-001: Fix 1" in sol and "- Serves: P-001" in sol
       and "- Also serves: P-002" in sol and "### S-002: Part 1" in sol and "#### F-001: Button" in sol, sol)
    ok("apply-draft: Needs and Done when carried over", "- Needs: F-001" in sol
       and "- Done when: Saved forms appear in the list." in sol, sol)
    ok("apply-draft: a feature sits under its home parent",
       sol.index("### S-002: Part 1") < sol.index("#### F-001: Button") < sol.index("#### F-002: List"), sol)
    ok("apply-draft: open questions stay in the plan", "- Open questions: Who feels it most?" in read(root, "plan/problems.md"))
    ok("apply-draft: the entry not approved went back to the backlog", "### Maybe later" in read(root, "drafts/backlog.md")
       and "### Maybe later" not in read(root, "drafts/draft-v0.1.md"))
    code, out = run(root, "check")
    ok("the plan checks clean after apply-draft", code == 0, out)

    code, out = run(root, "record-push", "v0.1")
    ok("record-push needs --approved-by", code != 0 and "approved-by" in out, out)
    code, out = run(root, "record-push", "v0.1", "--approved-by", "Head of Department")
    ok("record-push v0.1", code == 0, out)
    log = read(root, "versions/log.md")
    ok("the log records who approved", "- Approved by: Head of Department on" in log, log)
    ok("the version keeps a copy of the constraints", (root / "versions/v0.1/constraints.md").exists())
    commit(root, "v0.1", "v0.1")
    code, out = run(root, "check")
    ok("clean after v0.1", code == 0 and "0 errors, 0 to do, 0 warnings" in out, out)
    v01 = nodes(root, "versions/v0.1/mindmap.html")
    ok("version maps carry version chips", all(n.get("since") == "v0.1" for n in v01.values()), str(v01))
    saved_maps = {f: read(root, f) for f in ("versions/v0.1/mindmap.html", "versions/v0.1/draft-v0.1-map.html")}

    # ------------------------------------------------------------------ the prototype: built ticks, review, save
    write(root, "prototype/index.html", '<button data-trace="F-001">Save</button>\n')
    code, out = run(root, "check")
    ok("a new marker makes the plan map stale", code != 0 and "plan/map.html" in out, out)
    run(root, "build")
    built = {n.get("ref") for n in mapdata(root, "plan/map.html")["nodes"] if n.get("built")}
    ok("the plan map ticks built features", built == {"F-001"}, str(built))
    code, out = run(root, "status")
    ok("status lists what is not built yet", "Features not built yet (1)" in out and "F-002 List" in out, out)
    ok("status shows a feature waiting for what it needs", "Features waiting" not in out or "F-002" in out, out)
    ok("status says v1.0 is not ready", "Ready for v1.0: no" in out, out)
    write(root, "prototype/index.html", '<button data-trace="F-001">Save</button>\n<ul data-trace="F-002"></ul>\n')
    run(root, "build")
    code, out = run(root, "save-prototype", "v0.1")
    ok("save-prototype refuses without a review", code != 0 and "Review first" in out, out)
    fill_review(root, "prototype/REVIEW.md", "v0.1", accepted="F-001")
    b = read(root, "drafts/backlog.md").replace(
        "## Dropped", "- [ ] F-009: names an ID that does not exist\n\n## Dropped")
    write(root, "drafts/backlog.md", b)
    code, out = run(root, "check")
    ok("a bug must name a pushed feature", code != 0 and "F-009, which is not pushed" in out, out)
    write(root, "drafts/backlog.md", b.replace("- [ ] F-009: names an ID that does not exist",
                                               "- [x] F-002: list is empty after saving (found 2026-01-01)\n"
                                               "- [ ] F-001: button too small (found 2026-01-01)"))
    code, out = run(root, "save-prototype", "v0.1")
    ok("save-prototype after the review", code == 0, out)
    ok("the saved prototype keeps its review", "Test Reviewer" in read(root, "versions/v0.1/prototype/REVIEW.md"))
    ok("the live review starts again empty", "Test Reviewer" not in read(root, "prototype/REVIEW.md"))
    log = read(root, "versions/log.md")
    ok("fixed bugs move into the log", "- Fixed: F-002: list is empty after saving" in log, log)
    bl = read(root, "drafts/backlog.md")
    ok("fixed bugs leave the backlog, open ones stay", "list is empty" not in bl and "button too small" in bl, bl)
    commit(root, "save prototype v0.1")
    code, out = run(root, "status")
    ok("status shows accepted features", "F-001 (v0.1)" in out, out)
    code, out = run(root, "check")
    ok("clean after saving the prototype", code == 0, out)

    # ------------------------------------------------------------------ v0.2: every kind of amendment
    code, out = run(root, "new-draft", "v0.2")
    ok("new-draft v0.2", code == 0, out)
    entries(root, "drafts/draft-v0.2.md", '''
### Pain 1 is solved
- Type: Amendment
- Amends: P-001
- Description: The button fixed it.
- Status: Solved

### Fix 1 no longer covers pain 2
- Type: Amendment
- Amends: S-001
- Description: Pain 2 needs its own solution.
- Remove links: P-002
- New text: A solution for pain 1 only.

### Move the list
- Type: Amendment
- Amends: F-002
- Description: The list belongs to part 1.
- Serves: S-002
- Done when: Saved forms appear in the list within a second.

### Retire the button
- Type: Amendment
- Amends: F-001
- Description: Replaced.
- Retire: yes

### Fix 2
- Type: Solution
- Description: A solution for pain 2.
- Serves: P-002

### Form
- Type: Feature
- Description: A form.
- Serves: "Fix 2"
- Done when: The form can be filled in.
- Design location: form page
''')
    run(root, "build")
    saved = read(root, "drafts/draft-v0.2.md")
    entries(root, "drafts/draft-v0.2.md", '''
### Only a reason
- Type: Amendment
- Amends: S-002
- Description: The wording of the part should change, but no New text is given.
''')
    run(root, "build")
    code, out = run(root, "check", "--push", "v0.2")
    ok("an amendment that changes nothing is caught before the push", code != 0 and "changes nothing in the plan" in out, out)
    write(root, "drafts/draft-v0.2.md", saved)
    run(root, "build")
    code, out = run(root, "apply-draft")
    ok("apply-draft with amendments", code == 0, out)
    ok("apply-draft reports the amended items", "Amended: P-001; S-001; F-002; F-001" in out, out)
    pr, sol = read(root, "plan/problems.md"), read(root, "plan/solutions.md")
    ok("amendment: Status Solved", re.search(r"## P-001: Pain 1[\s\S]*?- Status: Solved", pr) is not None, pr)
    ok("amendment: link removed and new text",
       re.search(r"## S-001: Fix 1\n- Description: A solution for pain 1 only.\n- Serves: P-001\n- Also serves: none", sol)
       is not None, sol)
    ok("amendment: the moved feature sits under its new parent",
       sol.index("### S-002: Part 1") < sol.index("#### F-002: List") < sol.index("## S-003: Fix 2")
       and "- Done when: Saved forms appear in the list within a second." in sol, sol)
    ok("amendment: retire", re.search(r"#### F-001: Button[\s\S]*?- Status: Retired", sol) is not None, sol)
    ok("new solution and feature get the next IDs", "## S-003: Fix 2" in sol and "#### F-003: Form" in sol, sol)
    code, out = run(root, "check")
    ok("the retired feature's marker is caught", code != 0 and "F-001, which is retired" in out, out)
    write(root, "prototype/index.html", '<ul data-trace="F-002"></ul>\n<form data-trace="F-003"></form>\n')
    run(root, "build")
    code, out = run(root, "record-push", "v0.2", "--approved-by", "Head of Department")
    ok("record-push v0.2", code == 0, out)
    log = read(root, "versions/log.md")
    ok("the log lists amended and retired items", "- Amended: P-001" in log and "F-002" in log
       and "- Retired: F-001 Button" in log, log)
    fill_review(root, "prototype/REVIEW.md", "v0.2", accepted="F-002 F-003")
    code, out = run(root, "save-prototype", "v0.2")
    ok("save-prototype v0.2", code == 0, out)
    commit(root, "v0.2", "v0.2")
    code, out = run(root, "check")
    ok("clean after v0.2", code == 0, out)
    dm = nodes(root, "versions/v0.2/draft-v0.2-map.html")
    ok("a draft map shows every pushed item", set(v01) <= set(dm), str(sorted(set(v01) - set(dm))))
    ok("a draft map marks its own entries and hides nothing else",
       dm["F-002"].get("mark") == "amended" and not dm["O-001"].get("mark")
       and any(n.get("hist") == "Not pushed yet: new in this draft" for n in dm.values()), str(dm))
    ok("a draft map has the Show only changes switch", "Show only changes" in read(root, "versions/v0.2/draft-v0.2-map.html"))
    pm = nodes(root, "plan/map.html")
    ok("the plan map marks nothing", not any(n.get("mark") for n in pm.values()), str(pm))
    ok("chips show the version each item was first pushed",
       pm["F-002"].get("since") == "v0.1" and pm["F-003"].get("since") == "v0.2", str(pm))
    ok("history lists pushed, amended and built",
       pm["F-002"].get("hist", "").startswith("Pushed in v0.1 · Amended in v0.2")
       and "Built in the v0.1 prototype" in pm["F-002"]["hist"], pm["F-002"].get("hist"))
    ok("history lists the review that accepted it", "Accepted in the v0.2 review" in pm["F-003"].get("hist", ""),
       pm["F-003"].get("hist"))
    v02 = nodes(root, "versions/v0.2/mindmap.html")
    ok("a version map shows history as of that version",
       v02["F-002"].get("since") == "v0.1" and "Amended in v0.2" in v02["F-002"].get("hist", ""), str(v02["F-002"]))

    # ------------------------------------------------------------------ abandoning a draft still works
    run(root, "new-draft", "v0.3")
    entries(root, "drafts/draft-v0.3.md", '''
### Idea to park
- Type: Feature
- Description: Parked.
- Serves: S-003
- Done when: Parked.
''')
    code, out = run(root, "abandon-draft")
    ok("abandon-draft sends entries back to the backlog", code == 0
       and "### Idea to park" in read(root, "drafts/backlog.md"), out)
    commit(root, "abandon v0.3")

    # ------------------------------------------------------------------ v1.0: the gate
    run(root, "new-draft", "v1.0")
    entries(root, "drafts/draft-v1.0.md", '''
### Report
- Type: Feature
- Description: A report, not built in the prototype.
- Serves: S-003
- Done when: The report opens.
- Design location: report page
''')
    run(root, "build")
    run(root, "apply-draft")
    code, out = run(root, "record-push", "v1.0", "--approved-by", "Decision Maker")
    ok("v1.0 is refused while the prototype has gaps", code != 0 and "does not cover the whole scope" in out, out)
    code, out = run(root, "record-push", "v1.0", "--approved-by", "Decision Maker",
                    "--accept-gaps", "The report is simple enough to build directly")
    ok("v1.0 with the gaps accepted in writing", code == 0, out)
    log = read(root, "versions/log.md")
    ok("the log records the accepted gaps and waits for a release",
       "- Gaps accepted: The report is simple" in log and "- Released: not yet" in log, log)
    ok("v1.0 adds product/design.md and product/REVIEW.md",
       (root / "product/design.md").exists() and (root / "product/REVIEW.md").exists())
    commit(root, "v1.0", "v1.0")

    # ------------------------------------------------------------------ the product: traceable code, release
    write(root, "product/src/app.py", "# F-004: the report\ndef report():\n    return 'report'\n")
    write(root, "product/tests/test_report.py", "# F-004 opens\n# F-777 does not exist\n")
    code, out = run(root, "check")
    ok("code naming an unknown ID is caught", code != 0 and "F-777, which is not pushed" in out, out)
    write(root, "product/tests/test_report.py", "# F-004: the report opens\n")
    run(root, "build")
    built = {n.get("ref") for n in mapdata(root, "plan/map.html")["nodes"] if n.get("built")}
    ok("code in product/ counts as built", "F-004" in built, str(built))
    code, out = run(root, "record-release", "v1.0", "--approved-by", "Decision Maker")
    ok("record-release refuses without a review", code != 0 and "Review first" in out, out)
    fill_review(root, "product/REVIEW.md", "v1.0", accepted="F-004")
    code, out = run(root, "record-release", "v1.0", "--approved-by", "Decision Maker")
    ok("record-release v1.0", code == 0, out)
    log = read(root, "versions/log.md")
    ok("the log records the release", re.search(r"- Released: \d{4}-\d\d-\d\d, approved by Decision Maker", log)
       is not None, log)
    ok("the release review is saved with the version", "Test Reviewer" in read(root, "versions/v1.0/review.md"))
    ok("the log lists what the release built", re.search(r"^- Built: F-004$", log, re.M) is not None, log)
    ok("history shows the release", "Released in v1.0" in nodes(root, "plan/map.html")["F-004"].get("hist", ""))
    ok("saved maps never change", all(read(root, f) == s for f, s in saved_maps.items()))
    commit(root, "release v1.0", "v1.0-release")
    code, out = run(root, "check")
    ok("clean after the release (a review added after the tag is fine)", code == 0, out)
    code, out = run(root, "record-release", "v1.0", "--approved-by", "X")
    ok("a version is released only once", code != 0 and "already released" in out, out)

    # ------------------------------------------------------------------ tampering is caught
    write(root, "versions/v1.0/review.md", "changed")
    write(root, "versions/v0.1/prototype/index.html", "changed")
    write(root, "versions/v0.2/objectives.md", "changed")
    code, out = run(root, "check")
    ok("an edited release review is caught", "a saved release review was changed" in out, out)
    ok("an edited saved prototype is caught", "a saved prototype was changed" in out, out)
    ok("an edited saved version is caught", "a saved version was changed after tag v0.2" in out, out)
    ok("check fails when something is broken", code != 0)


if __name__ == "__main__":
    sys.exit(main())
