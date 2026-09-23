#!/usr/bin/env python3
"""Checks and generates everything derived in this workflow.

Run from the project root (or anywhere; paths are relative to the folder above workflow/):

  python workflow/tool.py check [--push DRAFT]     report problems; changes nothing
  python workflow/tool.py build [--dry-run]        regenerate back-links, maps, draft overviews and copies,
                                                   and the prototype's trace data
  python workflow/tool.py next-ids                 next free ID of each kind
  python workflow/tool.py new-draft VERSION        start the next draft (only when no draft is open)
  python workflow/tool.py record-push VERSION --approved-by NAME [--note TEXT]
                                                   save versions/VERSION/, add the log entry, and move the
                                                   pushed draft into that folder
  python workflow/tool.py status                   what is covered, built, accepted, open, and still missing
  python workflow/tool.py apply-draft [--skip TITLE] [--dry-run]
                                                   write the open draft's entries into plan/ with new IDs
                                                   (entries not approved go back to the backlog)
  python workflow/tool.py save-prototype VERSION   save the reviewed prototype into versions/VERSION/prototype/
  python workflow/tool.py record-release VERSION --approved-by NAME
                                                   from v1.0: release the reviewed product for that version
  python workflow/tool.py abandon-draft            give up the open draft: its entries go back to the backlog,
                                                   and the draft is kept, frozen, in versions/abandoned/

DRAFT is a path (drafts/draft-v0.2.md) or a version (v0.2).
Standard library only. Files keep their encoding and line endings. Frozen files are never written.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "plan"
MAIN_DOCS = ["objectives.md", "problems.md", "solutions.md"]
PLAN_MAP = PLAN / "map.html"
PROTOTYPE_BRIEF = PLAN / "prototype.md"
CONSTRAINTS = PLAN / "constraints.md"
DRAFTS = ROOT / "drafts"
BACKLOG = DRAFTS / "backlog.md"
VERSIONS = ROOT / "versions"
LOG = VERSIONS / "log.md"
ABANDONED = VERSIONS / "abandoned"
HISTORY = ROOT / "history"
WORKFLOW = ROOT / "workflow"
TEMPLATE_MAP = WORKFLOW / "map-template.html"
TEMPLATE_DRAFT = WORKFLOW / "draft-template.md"
PROTOTYPE = ROOT / "prototype"
TRACE = PROTOTYPE / "trace"
CHAIN_JS = TRACE / "chain.js"
PROTO_REVIEW = PROTOTYPE / "REVIEW.md"
PRODUCT = ROOT / "product"
PRODUCT_REVIEW = PRODUCT / "REVIEW.md"
PRODUCT_DESIGN = PRODUCT / "design.md"
TEMPLATE_REVIEW = WORKFLOW / "review-template.md"
TEMPLATE_DESIGN = WORKFLOW / "design-template.md"
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv", ".next", "target"}
TOOL = "workflow/tool.py"

TYPE_NAME = {"objective": "Objective", "problem": "Problem", "solution": "Solution",
             "sub-solution": "Sub-solution", "feature": "Feature"}
LAYERS = [("o", "Objectives", "t1", "objective"), ("p", "Problems", "t2", "problem"),
          ("s", "Solutions", "t3", "solution"), ("u", "Sub-solutions", "t4", "sub-solution"),
          ("f", "Features", "t5", "feature")]
LAYER_OF = {t: k for k, _, _, t in LAYERS}
ALLOWED = {"problem": {"objective"}, "solution": {"problem"},
           "sub-solution": {"solution"}, "feature": {"solution", "sub-solution"}}
PREFIX_DOC = {"O": "objectives.md", "P": "problems.md", "S": "solutions.md", "F": "solutions.md"}
DRAFT_TYPES = {"objective": "objective", "problem": "problem", "solution": "solution",
               "sub-solution": "sub-solution", "subsolution": "sub-solution",
               "sub solution": "sub-solution", "feature": "feature", "amendment": "amendment"}

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
GEN_BEGIN = re.compile(r"^\s*<!--\s*BEGIN GENERATED:\s*([\w-]+)\s*-->\s*$")
GEN_END = re.compile(r"^\s*<!--\s*END GENERATED:\s*([\w-]+)\s*-->\s*$")
RULE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
FIELD = re.compile(r"^-\s+([A-Za-z][A-Za-z -]*?)\s*(?:\([^)]*\))?\s*:\s?(.*)$")
# Back-link lines written by hand in older versions of this workflow; "Served by" replaces them.
LEGACY_BACKLINKS = {"problems", "also served by", "solutions", "also solved by"}
FIELDS = {"type", "description", "idea", "serves", "home parent", "also serves", "amends",
          "retire", "label", "design location", "open questions", "status", "served by",
          "done when", "needs", "priority", "remove links", "new text"} | LEGACY_BACKLINKS
PRIORITIES = ("now", "next", "later")
BUG_LINE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.*?)\s*$")
REVIEW_KEYS = ("version", "date", "reviewed by", "accepted", "not accepted", "findings")
ALIAS = {"idea": "description", "home parent": "serves"}
# IDs are flat (S-004). Older dotted IDs (S-002.1) are read as they are and never renamed.
ID_HEAD = re.compile(r"^([OPSF])-(\d{3,}(?:\.\d+)*)\b\s*[:.\u2014\u2013-]?\s*(.*)$")
ID_RE = re.compile(r"\b([OPSF])-(\d{3,}(?:\.\d+)*)\b")
QUOTED = re.compile(r'"([^"\n]+)"|\u201c([^\u201d\n]+)\u201d')
SEP = re.compile(r"\s+(?:\u2014|\u2013|--|-)\s+")
FILLER = re.compile(r"\b(?:objectives?|problems?|solutions?|sub-?solutions?|features?|and|or|none|yet|n/a)\b", re.I)
STATUS_LINE = re.compile(r"^\*\*Status:\*\*\s*(.*?)\s*$")
VERSION_RE = re.compile(r"^v\d+(?:\.\d+)+$")
DATA_BLOCK = re.compile(r"/\* BEGIN DATA.*?\*/.*?/\* END DATA \*/", re.S)
TRACE_ATTR = re.compile(r"""data-trace\s*=\s*["']([^"']*)["']""")
TRACE_JS = re.compile(r"""dataset\.trace\s*=\s*([^;\n]+)""")


# --------------------------------------------------------------------------- text files

def rel(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


class TextFile:
    """A UTF-8 text file read with its newline style and BOM remembered."""

    def __init__(self, path, text=None):
        self.path = Path(path)
        if text is not None:
            self.text, self.nl, self.bom = text, "\n", False
            return
        raw = self.path.read_bytes()
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        self.nl = "\r\n" if "\r\n" in text else "\n"
        self.text = text.replace("\r\n", "\n")


def norm_text(s):
    return s.replace("\r\n", "\n").lstrip("\ufeff")


class Writer:
    """Writes only when the content changes, keeps line endings, refuses frozen files."""

    def __init__(self, dry=False, frozen=()):
        self.dry, self.frozen, self.changed = dry, [Path(p).resolve() for p in frozen], []

    def is_frozen(self, path):
        p = Path(path).resolve()
        return any(p == f or f in p.parents for f in self.frozen)

    def note(self, path):
        if rel(path) not in self.changed:
            self.changed.append(rel(path))

    def write(self, path, text, allow_frozen=False):
        path = Path(path)
        if not allow_frozen and self.is_frozen(path):
            raise SystemExit(f"Refusing to write a frozen file: {rel(path)}")
        nl, bom = "\n", False
        if path.exists():
            old = TextFile(path)
            nl, bom = old.nl, old.bom
            if old.text == text:
                return False
        data = (text.replace("\n", nl) if nl != "\n" else text).encode("utf-8")
        if bom:
            data = b"\xef\xbb\xbf" + data
        self.note(path)
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return True

    def copy(self, src, dst, allow_frozen=False):
        if not allow_frozen and self.is_frozen(dst):
            raise SystemExit(f"Refusing to write a frozen file: {rel(dst)}")
        self.note(dst)
        if not self.dry:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            Path(dst).write_bytes(Path(src).read_bytes())

    def remove(self, path):
        if self.is_frozen(path):
            raise SystemExit(f"Refusing to remove a frozen file: {rel(path)}")
        self.note(path)
        if not self.dry:
            Path(path).unlink()


# --------------------------------------------------------------------------- markdown

def mask(lines):
    """True for lines inside code fences or generated blocks (never parsed as entries)."""
    out, fence, gen = [], False, False
    for ln in lines:
        if gen:
            out.append(True)
            if GEN_END.match(ln):
                gen = False
            continue
        if not fence and GEN_BEGIN.match(ln):
            gen = True
            out.append(True)
            continue
        if FENCE.match(ln):
            fence = not fence
            out.append(True)
            continue
        out.append(fence)
    return out


class Block:
    def __init__(self, level, text, start, end, fields, section):
        self.level, self.text, self.start, self.end = level, text, start, end
        self.fields, self.section = fields, section

    def get(self, name, default=""):
        return self.fields.get(name, (default, None))[0]

    def line(self, name=None):
        if name and name in self.fields:
            return self.fields[name][1] + 1
        return self.start + 1


def field_name(raw):
    n = " ".join(raw.lower().split())
    return ALIAS.get(n, n) if n in FIELDS else None


def parse_blocks(lines, masked):
    heads, section = [], None
    for i, ln in enumerate(lines):
        if masked[i]:
            continue
        m = HEADING.match(ln)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level <= 2:
                section = text if level == 2 else None
            heads.append((i, level, text, section))
    blocks = []
    for j, (i, level, text, section) in enumerate(heads):
        end = heads[j + 1][0] if j + 1 < len(heads) else len(lines)
        fields, cur = {}, None
        for k in range(i + 1, end):
            if masked[k] or RULE.match(lines[k]):
                cur = None
                continue
            fm = FIELD.match(lines[k])
            name = field_name(fm.group(1)) if fm else None
            if name:
                fields[name] = [fm.group(2).strip(), k]
                cur = name
            elif cur and lines[k].strip():
                fields[cur][0] = (fields[cur][0] + "\n" + lines[k].strip()).strip()
        blocks.append(Block(level, text, i, end, fields, section))
    return blocks


def norm_title(t):
    t = t.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(t.split()).casefold()


def parse_refs(value):
    """IDs and "quoted titles" before the first ' — '. Returns (refs, stray text)."""
    v = " ".join((value or "").split())
    if not v:
        return [], ""
    spans = [(m.start(), m.end(), (m.group(1) or m.group(2)).strip()) for m in QUOTED.finditer(v)]
    cut = len(v)
    for m in SEP.finditer(v):
        if not any(s <= m.start() < e for s, e, _ in spans):
            cut = m.start()
            break
    head, events = v[:cut], []
    for s, e, t in spans:
        if e <= cut:
            events.append((s, ("title", t)))
            head = head[:s] + " " * (e - s) + head[e:]
    for m in ID_RE.finditer(head):
        events.append((m.start(), ("id", f"{m.group(1)}-{m.group(2)}")))
    events.sort(key=lambda x: x[0])
    stray = FILLER.sub(" ", ID_RE.sub(" ", head))
    stray = re.sub(r"[\W_]+", " ", stray).strip()
    return [r for _, r in events], stray


def short_label(title, label=""):
    if label:
        return label
    t = " ".join(title.split())
    if len(t) <= 28:
        return t
    cut = t[:27]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:\u2014\u2013-") + "\u2026"


def replace_generated(text, name, content):
    lines = text.split("\n")
    b = e = None
    for i, ln in enumerate(lines):
        m = GEN_BEGIN.match(ln)
        if m and m.group(1) == name and b is None:
            b = i
            continue
        m = GEN_END.match(ln)
        if m and m.group(1) == name and b is not None:
            e = i
            break
    if b is None or e is None:
        return None
    return "\n".join(lines[:b + 1] + content.split("\n") + lines[e:])


def version_key(v):
    return tuple(int(x) for x in v[1:].split("."))


# --------------------------------------------------------------------------- issues

class Issues:
    def __init__(self):
        self.items = []

    def add(self, level, where, line, msg):
        self.items.append((level, where, line or 0, msg))

    def error(self, where, line, msg):
        self.add("error", where, line, msg)

    def todo(self, where, line, msg):
        self.add("todo", where, line, msg)

    def warn(self, where, line, msg):
        self.add("warn", where, line, msg)


# --------------------------------------------------------------------------- the plan (main documents)

class Item:
    def __init__(self, iid, title, doc, where, block, seq):
        self.id, self.prefix = iid, iid[0]
        self.num = int(iid[2:].split(".")[0])
        self.title, self.doc, self.where, self.block, self.seq = title, doc, where, block, seq
        self.type = {"O": "objective", "P": "problem", "S": "solution", "F": "feature"}[self.prefix]
        self.serves, self.also, self.status = None, [], ""
        self.label = block.get("label")
        self.retired = False
        self.needs, self.done_when = [], block.get("done when").strip()
        self.questions = open_questions(block.get("open questions"))


def open_questions(value):
    v = " ".join((value or "").split())
    return "" if v.lower() in ("", "none", "none yet", "-", "n/a") else value.strip()


class Main:
    """The three main documents: the live plan/ or a saved version of them."""

    def __init__(self, folder, issues=None, texts=None):
        self.folder, self.items, self.files, self.lines = Path(folder), {}, {}, {}
        self.by_title = {}
        issues = issues if issues is not None else Issues()
        seq = 0
        for doc in MAIN_DOCS:
            path = self.folder / doc
            where = rel(path)
            if texts is not None and doc in texts:
                tf = TextFile(path, texts[doc])
            elif path.exists():
                tf = TextFile(path)
            else:
                issues.error(where, 0, "file is missing")
                continue
            self.files[doc] = tf
            lines = tf.text.split("\n")
            self.lines[doc] = lines
            for b in parse_blocks(lines, mask(lines)):
                m = ID_HEAD.match(b.text)
                if not m:
                    if b.level >= 2 and b.fields:
                        issues.warn(where, b.line(), f'heading "{b.text}" has fields but no ID')
                    continue
                iid = f"{m.group(1)}-{m.group(2)}"
                if PREFIX_DOC[m.group(1)] != doc:
                    issues.error(where, b.line(), f"{iid} belongs in {PREFIX_DOC[m.group(1)]}")
                if iid in self.items:
                    issues.error(where, b.line(), f"{iid} is used twice")
                    continue
                seq += 1
                it = Item(iid, m.group(3).strip(), doc, where, b, seq)
                self.items[iid] = it
                self.by_title.setdefault(norm_title(it.title), it)
        for it in self.items.values():
            refs, _ = parse_refs(it.block.get("serves"))
            ids = [r[1] for r in refs if r[0] == "id"]
            it.serves = ids[0] if ids else None
            arefs, _ = parse_refs(it.block.get("also serves"))
            it.also = [r[1] for r in arefs if r[0] == "id"]
            it.needs = [r[1] for r in parse_refs(it.block.get("needs"))[0] if r[0] == "id"]
            it.status = " ".join(it.block.get("status").split()).lower()
            it.retired = it.status == "retired"
        for it in self.items.values():  # a solution that serves a solution is a sub-solution
            if it.prefix == "S" and it.serves and it.serves.startswith("S-"):
                it.type = "sub-solution"

    def active(self):
        return [it for it in self.items.values() if not it.retired]

    def ordered(self, items=None):
        return sorted(items if items is not None else self.items.values(), key=lambda x: x.seq)

    def entry_text(self, it, shift=0, drop_backlinks=False):
        lines = self.lines[it.doc][it.block.start:it.block.end]
        while lines and (not lines[-1].strip() or RULE.match(lines[-1])):
            lines = lines[:-1]
        out = []
        for i, ln in enumerate(lines):
            fm = FIELD.match(ln)
            if drop_backlinks and fm and field_name(fm.group(1)) in LEGACY_BACKLINKS | {"served by"}:
                continue
            if i == 0 and shift:
                m = HEADING.match(ln)
                ln = "#" * min(6, len(m.group(1)) + shift) + " " + m.group(2)
            out.append(ln)
        return out

    def links(self):
        out = set()
        for it in self.active():
            if it.serves:
                out.add((it.id, it.serves, 1))
            for a in it.also:
                out.add((it.id, a, 0))
        return out


def check_main(main, issues):
    for it in main.ordered():
        where, b = it.where, it.block
        if not it.title:
            issues.error(where, b.line(), f"{it.id} has no title")
        if not b.get("description").strip():
            issues.todo(where, b.line(), f"{it.id} has no description")
        for name in sorted(LEGACY_BACKLINKS & set(b.fields)):
            issues.warn(where, b.line(name), f'{it.id}: the old "{name.capitalize()}:" line can go; '
                                             '"Served by" is generated now')
        if it.type == "objective":
            if it.status not in ("open", "done", "retired"):
                issues.error(where, b.line("status"), f"{it.id}: Status must be Open, Done or Retired")
            if b.get("serves").strip() and b.get("serves").strip().lower() != "none":
                issues.warn(where, b.line("serves"), f"{it.id}: objectives have no parent; Serves is ignored")
        else:
            allowed = ALLOWED[it.type]
            refs, stray = parse_refs(b.get("serves"))
            if any(r[0] == "title" for r in refs) or stray:
                issues.error(where, b.line("serves"), f"{it.id}: in the plan, Serves must be an ID")
            if not it.serves:
                issues.error(where, b.line("serves"), f"{it.id} has no home parent (Serves)")
            elif len([r for r in refs if r[0] == "id"]) > 1:
                issues.error(where, b.line("serves"), f"{it.id}: Serves takes one home parent; put the others in Also serves")
            else:
                p = main.items.get(it.serves)
                if not p:
                    issues.error(where, b.line("serves"), f"{it.id} serves {it.serves}, which does not exist")
                elif p.type not in allowed:
                    issues.error(where, b.line("serves"),
                                 f"{it.id} ({TYPE_NAME[it.type]}) cannot serve {p.id} ({TYPE_NAME[p.type]})")
                elif p.retired and not it.retired:
                    issues.warn(where, b.line("serves"), f"{it.id} serves {p.id}, which is retired")
            arefs, astray = parse_refs(b.get("also serves"))
            if any(r[0] == "title" for r in arefs) or astray:
                issues.error(where, b.line("also serves"), f"{it.id}: in the plan, Also serves must list IDs")
            seen = set()
            for a in it.also:
                p = main.items.get(a)
                if a in seen or a == it.serves:
                    issues.warn(where, b.line("also serves"), f"{it.id} lists {a} twice")
                seen.add(a)
                if a == it.id:
                    issues.error(where, b.line("also serves"), f"{it.id} cannot serve itself")
                elif not p:
                    issues.error(where, b.line("also serves"), f"{it.id} also serves {a}, which does not exist")
                elif p.type not in allowed:
                    issues.error(where, b.line("also serves"),
                                 f"{it.id} ({TYPE_NAME[it.type]}) cannot serve {p.id} ({TYPE_NAME[p.type]})")
                elif p.retired and not it.retired:
                    issues.warn(where, b.line("also serves"), f"{it.id} also serves {p.id}, which is retired")
            if it.type == "problem" and it.status not in ("open", "solved", "retired"):
                issues.error(where, b.line("status"), f"{it.id}: Status must be Open, Solved or Retired")
            if it.type in ("solution", "sub-solution", "feature") and it.status not in ("", "active", "retired"):
                issues.error(where, b.line("status"), f"{it.id}: Status is either left out or Retired")
            if it.type == "feature" and not b.get("design location").strip():
                issues.warn(where, b.line(), f"{it.id} has no Design location")
            if it.type == "feature" and not it.done_when and not it.retired:
                issues.warn(where, b.line(), f'{it.id} has no "Done when" (add it with an Amendment)')
        if "needs" in b.fields:
            nrefs, nstray = parse_refs(b.get("needs"))
            if it.type != "feature":
                issues.warn(where, b.line("needs"), f'{it.id}: only features have "Needs"')
            if any(r[0] == "title" for r in nrefs) or nstray:
                issues.error(where, b.line("needs"), f"{it.id}: in the plan, Needs must list IDs")
            for n in it.needs:
                q = main.items.get(n)
                if n == it.id:
                    issues.error(where, b.line("needs"), f"{it.id} cannot need itself")
                elif not q:
                    issues.error(where, b.line("needs"), f"{it.id} needs {n}, which does not exist")
                elif q.type != "feature":
                    issues.error(where, b.line("needs"), f"{it.id} needs {n}, which is not a feature")
                elif q.retired and not it.retired:
                    issues.warn(where, b.line("needs"), f"{it.id} needs {n}, which is retired")
        want = {"objective": 2, "problem": 2, "solution": 2, "sub-solution": 3, "feature": 4}[it.type]
        if b.level != want:
            issues.warn(where, b.line(), f"{it.id} ({TYPE_NAME[it.type]}) is usually a level-{want} heading")
    for it in main.items.values():
        if it.type == "objective" and it.status == "done":
            for p in main.active():
                if p.type == "problem" and (p.serves == it.id or it.id in p.also) and p.status != "solved":
                    issues.warn(it.where, it.block.line("status"), f"{it.id} is Done but {p.id} is not Solved")


def served_by_texts(main):
    """The main documents with every 'Served by' line regenerated."""
    kids = {}
    for it in main.active():
        if it.serves in main.items:
            kids.setdefault(it.serves, [[], []])[0].append(it)
        for a in it.also:
            if a in main.items:
                kids.setdefault(a, [[], []])[1].append(it)
    out = {}
    for doc, lines in main.lines.items():
        lines = list(lines)
        todo = []
        for it in main.items.values():
            if it.doc != doc or it.type == "feature":
                continue
            h, a = kids.get(it.id, [[], []])
            parts = []
            if h:
                parts.append(", ".join(x.id for x in main.ordered(h)))
            if a:
                parts.append("also " + ", ".join(x.id for x in main.ordered(a)))
            text = "- Served by: " + ("; ".join(parts) if parts else "none")
            b = it.block
            if "served by" in b.fields:
                todo.append((b.fields["served by"][1], "replace", text))
            else:
                last = b.start
                for k in range(b.start + 1, b.end):
                    if lines[k].strip() and not RULE.match(lines[k]) and not HEADING.match(lines[k]):
                        last = k
                todo.append((last + 1, "insert", text))
        for idx, how, text in sorted(todo, key=lambda x: x[0], reverse=True):
            if how == "replace":
                lines[idx] = text
            else:
                lines.insert(idx, text)
        out[doc] = "\n".join(lines)
    return out


# --------------------------------------------------------------------------- drafts

class Entry:
    def __init__(self, block, index):
        self.block, self.index, self.key = block, index, f"d{index}"
        self.title = block.text
        self.ntitle = norm_title(block.text)
        raw = " ".join(block.get("type").lower().split())
        self.type = DRAFT_TYPES.get(raw, raw)
        self.label = block.get("label")
        self.amends = None
        self.retire = block.get("retire").strip().lower() in ("yes", "true", "y")
        self.home = None      # resolved ("item", Item) | ("entry", Entry)
        self.also = []
        self.needs = []       # resolved features this one needs first
        self.remove = []      # amendments: pushed links to remove
        self.status = ""      # amendments: a new Status (Solved, Done, Open)
        self.priority = " ".join(block.get("priority").split()).lower()


class Draft:
    """The backlog or the one open draft."""

    def __init__(self, path):
        self.path = Path(path)
        self.rel = rel(path)
        self.tf = TextFile(path)
        self.lines = self.tf.text.split("\n")
        self.is_backlog = self.path.resolve() == BACKLOG.resolve()
        m = re.match(r"^draft-(v\d+(?:\.\d+)+)$", self.path.stem)
        self.version = m.group(1) if m else None
        self.title = next((HEADING.match(l).group(2) for l in self.lines
                           if HEADING.match(l) and len(HEADING.match(l).group(1)) == 1), self.path.stem)
        self.status = ""
        for ln in self.lines:
            m = STATUS_LINE.match(ln)
            if m:
                self.status = m.group(1)
                break
        self.active = self.status.lower() == "active"
        self.map_path = self.path.with_name(self.path.stem + "-map.html")
        masked = mask(self.lines)
        blocks = parse_blocks(self.lines, masked)
        self.has_entries = any(b.level == 2 and b.text.lower().startswith("entries") for b in blocks)
        self.entries = [Entry(b, i + 1) for i, b in
                        enumerate(b for b in blocks if b.level == 3 and (b.section or "").lower().startswith("entries"))]
        self.stray_levels = [b for b in blocks if b.level > 3 and (b.section or "").lower().startswith("entries")]
        self.by_title = {}
        for e in self.entries:
            self.by_title.setdefault(e.ntitle, e)


def find_drafts():
    out = []
    if BACKLOG.exists():
        out.append(Draft(BACKLOG))
    if DRAFTS.exists():
        out += [Draft(f) for f in sorted(DRAFTS.glob("draft-*.md"))]
    return out


def removed_already(iid, target):
    """True when the latest saved version still had this also-serves link (a push is removing it now)."""
    folder = latest_version()
    old = Main(folder, Issues()).items.get(iid) if folder else None
    return bool(old) and target in old.also


def resolve_draft(draft, main, issues, backlog_titles, strict):
    """Resolve every reference in a draft; report problems."""
    where = draft.rel
    todo = issues.error if strict else issues.todo
    seen, same_as_pushed = {}, []
    for e in draft.entries:
        b = e.block
        if e.ntitle in seen:
            issues.error(where, b.line(), f'two entries are called "{e.title}"')
        seen[e.ntitle] = e
        if not b.get("type"):
            todo(where, b.line(), f'"{e.title}" has no Type')
            continue
        if e.type not in TYPE_NAME and e.type != "amendment":
            issues.error(where, b.line("type"), f'"{e.title}": unknown Type "{b.get("type")}"')
            continue
        if e.type != "amendment" and ID_HEAD.match(e.title):
            issues.error(where, b.line(), f'"{e.title}": draft entries have no ID; use an Amendment to change a pushed item')
        if not b.get("description").strip():
            todo(where, b.line(), f'"{e.title}" has no Description')
        if e.type == "amendment":
            ids = [r[1] for r in parse_refs(b.get("amends"))[0] if r[0] == "id"]
            if not ids:
                issues.error(where, b.line("amends") if "amends" in b.fields else b.line(),
                             f'"{e.title}": an Amendment needs "Amends: <ID>"')
                continue
            e.amends = main.items.get(ids[0])
            if not e.amends:
                issues.error(where, b.line("amends"), f'"{e.title}" amends {ids[0]}, which is not pushed')
                continue
            ctype = e.amends.type
        else:
            ctype = e.type
        same = main.by_title.get(e.ntitle) if e.type != "amendment" else None
        if same:
            same_as_pushed.append(same.id)

        def res(ref, field):
            kind, val = ref
            if kind == "id":
                it = main.items.get(val)
                if not it:
                    issues.error(where, b.line(field), f'"{e.title}": {val} is not pushed')
                    return None
                if it.retired:
                    issues.warn(where, b.line(field), f'"{e.title}": {val} is retired')
                return ("item", it)
            t = draft.by_title.get(norm_title(val))
            if t:
                return ("entry", t)
            it = main.by_title.get(norm_title(val))
            if it:
                issues.warn(where, b.line(field), f'"{e.title}": refer to pushed items by ID ("{val}" is {it.id})')
                return ("item", it)
            if not draft.is_backlog and norm_title(val) in backlog_titles:
                issues.error(where, b.line(field), f'"{e.title}": "{val}" is in the backlog; move it into this draft first')
            else:
                issues.error(where, b.line(field), f'"{e.title}": no entry or pushed item is called "{val}"')
            return None

        def rtype(r):
            return r[1].type if r else None

        refs, stray = parse_refs(b.get("serves"))
        if stray:
            issues.warn(where, b.line("serves"), f'"{e.title}": put titles in double quotes and explanations after " \u2014 " '
                                                 f'(could not read "{stray}")')
        if ctype == "objective":
            if refs:
                issues.warn(where, b.line("serves"), f'"{e.title}": objectives have no parent; Serves is ignored')
        elif refs:
            if len(refs) > 1:
                issues.error(where, b.line("serves"), f'"{e.title}": Serves takes one home parent; put the others in Also serves')
            r = res(refs[0], "serves")
            if r and rtype(r) and rtype(r) not in ALLOWED[ctype]:
                issues.error(where, b.line("serves"),
                             f'"{e.title}" ({TYPE_NAME[ctype]}) cannot serve {TYPE_NAME.get(rtype(r), rtype(r))} "{r[1].title}"')
                r = None
            e.home = r
        elif e.type != "amendment":
            todo(where, b.line(), f'"{e.title}" has no home parent (Serves)')
        arefs, astray = parse_refs(b.get("also serves"))
        if astray:
            issues.warn(where, b.line("also serves"), f'"{e.title}": put titles in double quotes and explanations after " \u2014 " '
                                                      f'(could not read "{astray}")')
        if ctype == "objective" and arefs:
            issues.warn(where, b.line("also serves"), f'"{e.title}": objectives have no parent; Also serves is ignored')
            arefs = []
        keys = set()
        for ref in arefs:
            r = res(ref, "also serves")
            if not r:
                continue
            if rtype(r) not in ALLOWED.get(ctype, set()):
                issues.error(where, b.line("also serves"),
                             f'"{e.title}" ({TYPE_NAME[ctype]}) cannot serve {TYPE_NAME.get(rtype(r), rtype(r))} "{r[1].title}"')
                continue
            k = id(r[1])
            if k in keys or (e.home and e.home[1] is r[1]):
                issues.warn(where, b.line("also serves"), f'"{e.title}" lists "{r[1].title}" twice')
                continue
            if r[0] == "entry" and r[1] is e:
                issues.error(where, b.line("also serves"), f'"{e.title}" cannot serve itself')
                continue
            keys.add(k)
            e.also.append(r)
        if e.type == "feature" and strict and not b.get("design location").strip():
            issues.warn(where, b.line(), f'"{e.title}" has no Design location')
        if e.type == "feature" and not b.get("done when").strip():
            todo(where, b.line(), f'"{e.title}" has no "Done when"')
        if e.priority and e.priority not in PRIORITIES:
            issues.warn(where, b.line("priority"), f'"{e.title}": Priority is Now, Next, or Later')
        nrefs, nstray = parse_refs(b.get("needs"))
        if nstray:
            issues.warn(where, b.line("needs"), f'"{e.title}": put titles in double quotes (could not read "{nstray}")')
        if nrefs and ctype != "feature":
            issues.warn(where, b.line("needs"), f'"{e.title}": only features have "Needs"')
        for ref in nrefs:
            r = res(ref, "needs")
            if r and r[1] is e:
                issues.error(where, b.line("needs"), f'"{e.title}" cannot need itself')
            elif r and r[1].type != "feature":
                issues.error(where, b.line("needs"), f'"{e.title}" needs "{r[1].title}", which is not a feature')
            elif r:
                e.needs.append(r)
        if e.type == "amendment":
            for ref in parse_refs(b.get("remove links"))[0]:
                r = res(ref, "remove links")
                if not r:
                    continue
                target = r[1].id if r[0] == "item" else None
                if target is not None and target not in e.amends.also and removed_already(e.amends.id, target):
                    continue  # apply-draft already took it out; the push is in progress
                if target is None or target not in e.amends.also:
                    issues.error(where, b.line("remove links"),
                                 f'"{e.title}": {e.amends.id} does not also serve "{r[1].title}"; only also-serves links can be removed')
                else:
                    e.remove.append(target)
            changes = (e.home or arefs or e.remove or e.needs or e.retire or open_questions(b.get("open questions"))
                       or any(b.get(f).strip() for f in ("new text", "done when", "design location", "label", "status")))
            if not changes:
                todo(where, b.line(), f'"{e.title}" changes nothing in the plan: put the new wording in "New text:" '
                                      '(Description is only the reason), or name the fields that change')
            st = " ".join(b.get("status").split()).lower()
            if st:
                ok = {"objective": ("open", "done"), "problem": ("open", "solved")}.get(ctype, ())
                if st not in ok:
                    issues.error(where, b.line("status"), f'"{e.title}": Status can only mark an objective Open or Done, '
                                                          'or a problem Open or Solved (use "Retire: yes" to retire)')
                else:
                    e.status = st
    if same_as_pushed:
        n = len(same_as_pushed)
        issues.warn(where, 0, f"{n} {'entry has' if n == 1 else 'entries have'} the same title as a pushed item "
                              f"({', '.join(same_as_pushed)}). Expected while this draft is being pushed; "
                              "otherwise change pushed items with an Amendment")


# --------------------------------------------------------------------------- graphs (maps and trees)

class Graph:
    def __init__(self, title, note, highlight):
        self.title, self.note, self.highlight = title, note, highlight
        self.nodes = {}   # key -> dict(key, type, full, short, ref, mark, seq)
        self.links = []   # (child, parent, home, new)

    def node(self, key, type_, full, short, ref="", mark="", seq=0, built=False):
        if key not in self.nodes:
            self.nodes[key] = {"key": key, "type": type_, "full": full, "short": short,
                               "ref": ref, "mark": mark if self.highlight else "", "seq": seq, "built": built}
        return self.nodes[key]

    def link(self, c, p, home, new=False):
        if c in self.nodes and p in self.nodes and c != p:
            if not any(l[0] == c and l[1] == p for l in self.links):
                self.links.append((c, p, 1 if home else 0, bool(new) and self.highlight))

    def home_of(self):
        return {c: p for c, p, h, _ in self.links if h}

    def ordered(self):
        """Columns left to right; inside a column, children follow the order of their home parents."""
        home, pos, out = self.home_of(), {}, []
        for layer, _, _, type_ in LAYERS:
            col = [n for n in self.nodes.values() if n["type"] == type_]
            col.sort(key=lambda n: (pos.get(home.get(n["key"]), 2.0), n["seq"]))
            for i, n in enumerate(col):
                pos[n["key"]] = (i + 0.5) / len(col)
            out += col
        return out

    def data(self):
        order = self.ordered()
        present = {n["type"] for n in order}
        layers = [{"key": k, "name": name, "tone": tone} for k, name, tone, t in LAYERS if t in present]
        nodes = []
        for n in order:
            d = {"id": n["key"], "layer": LAYER_OF[n["type"]], "short": n["short"], "full": n["full"]}
            if n["ref"]:
                d["ref"] = n["ref"]
            if n["mark"]:
                d["mark"] = n["mark"]
            if n.get("built"):
                d["built"] = 1
            nodes.append(d)
        rank = {n["key"]: i for i, n in enumerate(order)}
        links = sorted(self.links, key=lambda l: (rank[l[0]], -l[2], rank[l[1]]))
        return {"version": self.title, "note": self.note, "layers": layers, "nodes": nodes,
                "links": [[c, p, h, "new"] if new else [c, p, h] for c, p, h, new in links]}

    def tree(self):
        if not self.nodes:
            return "Nothing yet."
        home = self.home_of()
        kids = {}
        for c, p in home.items():
            kids.setdefault(p, []).append(c)
        order = {n["key"]: i for i, n in enumerate(self.ordered())}
        also = {}
        for c, p, h, _ in self.links:
            if not h:
                also.setdefault(c, []).append(p)

        def name(k):
            n = self.nodes[k]
            return n["full"] + (f" ({n['ref']})" if n["ref"] else "")

        def line(k):
            n = self.nodes[k]
            s = f"{TYPE_NAME[n['type']]}: {name(k)}"
            if n["mark"]:
                s += " \u2014 " + {"new": "NEW", "amended": "AMENDED", "cut": "CUT"}[n["mark"]]
            if also.get(k):
                s += " \u00b7 also serves: " + ", ".join(name(p) for p in sorted(also[k], key=lambda x: order[x]))
            return s

        out = []

        def walk(k, prefix, last, root):
            if root:
                out.append(line(k))
                child_prefix = ""
            else:
                out.append(prefix + (" \u2514\u2500 " if last else " \u251c\u2500 ") + line(k))
                child_prefix = prefix + ("    " if last else " \u2502  ")
            ch = sorted(kids.get(k, []), key=lambda x: order[x])
            for i, c in enumerate(ch):
                walk(c, child_prefix, i == len(ch) - 1, False)

        roots = [n["key"] for n in self.ordered() if n["type"] == "objective"]
        for i, r in enumerate(roots):
            if i:
                out.append("")
            walk(r, "", True, True)
        placed = set()

        def mark_placed(k):
            placed.add(k)
            for c in kids.get(k, []):
                mark_placed(c)
        for r in roots:
            mark_placed(r)
        loose = [n["key"] for n in self.ordered() if n["key"] not in placed]
        if loose:
            out += ["", "Not placed yet (no home parent that reaches an objective):"]
            out += [" - " + line(k) for k in loose]
        return "```\n" + "\n".join(out) + "\n```"


def draft_graph(draft, main, built=frozenset()):
    """Pushed context (all objectives and problems, plus the chains this draft touches) and the draft's own entries."""
    highlight = bool(main.items)
    g = Graph(draft.title, f"Generated from {draft.path.name} by {TOOL} \u2014 edit the text, not this map", highlight)
    include = {it.id for it in main.active() if it.type in ("objective", "problem")}
    amended = {}
    for e in draft.entries:
        if e.type == "amendment" and e.amends:
            amended[e.amends.id] = e
            include.add(e.amends.id)
        for r in ([e.home] if e.home else []) + e.also:
            if r and r[0] == "item":
                include.add(r[1].id)
    stack = list(include)
    while stack:  # every pushed item's home chain up to its objective
        it = main.items.get(stack.pop())
        if it and it.serves and it.serves in main.items and it.serves not in include:
            include.add(it.serves)
            stack.append(it.serves)
    for iid in include:
        it = main.items[iid]
        am = amended.get(iid)
        mark = ("cut" if am.retire else "amended") if am else ""
        g.node(iid, it.type, it.title, short_label(it.title, it.label), iid, mark, it.seq, iid in built)
    for e in draft.entries:
        if e.type in TYPE_NAME:
            g.node(e.key, e.type, e.title, short_label(e.title, e.label), "", "new", 100000 + e.index)
    for iid in include:
        it, am = main.items[iid], amended.get(iid)
        if am and am.home:
            g.link(iid, am.home[1].id if am.home[0] == "item" else am.home[1].key, True, True)
        elif it.serves:
            g.link(iid, it.serves, True)
        for a in it.also:
            g.link(iid, a, False)
        if am:
            for r in am.also:
                g.link(iid, r[1].id if r[0] == "item" else r[1].key, False, True)
    for e in draft.entries:
        if e.type not in TYPE_NAME:
            continue
        if e.home:
            g.link(e.key, e.home[1].id if e.home[0] == "item" else e.home[1].key, True, True)
        for r in e.also:
            g.link(e.key, r[1].id if r[0] == "item" else r[1].key, False, True)
    return g


def version_graph(version, main, prev):
    """Everything pushed so far, with what this version changed marked (compared with the previous version)."""
    highlight = prev is not None
    note = (f"Everything pushed up to {version}; marked: what {version} changed" if highlight
            else f"Everything pushed in {version}, the first version")
    g = Graph(f"Version {version}", note, highlight)
    for it in main.ordered():
        old = prev.items.get(it.id) if prev else None
        mark = ""
        if it.retired:
            if not old or old.retired:
                continue
            mark = "cut"
        elif prev is not None and not old:
            mark = "new"
        elif old and main.entry_text(it, drop_backlinks=True) != prev.entry_text(old, drop_backlinks=True):
            mark = "amended"
        g.node(it.id, it.type, it.title, short_label(it.title, it.label), it.id, mark, it.seq)
    old_links = prev.links() if prev else set()
    for it in main.ordered():
        if it.id not in g.nodes:
            continue
        if it.serves:
            g.link(it.id, it.serves, True, (it.id, it.serves, 1) not in old_links)
        for a in it.also:
            g.link(it.id, a, False, (it.id, a, 0) not in old_links)
    return g


def plan_graph(main, built=frozenset()):
    """The whole plan as it stands: everything pushed, nothing marked."""
    g = Graph("Plan", f"Everything pushed so far \u00b7 generated by {TOOL}", False)
    for it in main.ordered(main.active()):
        g.node(it.id, it.type, it.title, short_label(it.title, it.label), it.id, "", it.seq, it.id in built)
    for it in main.ordered(main.active()):
        if it.serves:
            g.link(it.id, it.serves, True)
        for a in it.also:
            g.link(it.id, a, False)
    return g


def copied_block(main):
    out = []
    for doc, heading in (("objectives.md", "Objectives"), ("problems.md", "Problems")):
        items = [it for it in main.ordered() if it.doc == doc and not it.retired]
        if items:
            out += [f"### {heading}", ""]
            for it in items:
                out += main.entry_text(it, shift=2) + [""]
    if not out:
        return "No current objectives or problems yet."
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def js_data(data):
    def dump(x):
        s = json.dumps(x, ensure_ascii=False, separators=(",", ":"))
        return s.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    lines = ["var DATA={",
             f'"version":{dump(data["version"])},',
             f'"note":{dump(data["note"])},',
             '"layers":[', ",\n".join(dump(l) for l in data["layers"]), "],",
             '"nodes":[', ",\n".join(dump(n) for n in data["nodes"]), "],",
             '"links":[', ",\n".join(dump(l) for l in data["links"]), "]",
             "};"]
    return "\n".join(lines)


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_map(graph):
    tpl = TextFile(TEMPLATE_MAP).text
    if not DATA_BLOCK.search(tpl):
        raise SystemExit(f"{rel(TEMPLATE_MAP)} has no /* BEGIN DATA */ ... /* END DATA */ block")
    data = graph.data()
    head = f"/* BEGIN DATA (generated by {TOOL} build; edit the text, not this map) */"
    out = DATA_BLOCK.sub(lambda m: head + "\n" + js_data(data) + "\n/* END DATA */", tpl, count=1)
    title = "<title>" + html_escape(data["version"]) + " \u00b7 map</title>"
    return re.sub(r"<title>.*?</title>", lambda m: title, out, count=1)


def chain_js(main):
    chain = {}
    for it in main.ordered(main.active()):
        e = {"type": TYPE_NAME[it.type], "name": it.title}
        if it.type != "objective":
            e["home"] = it.serves
            e["also"] = [a for a in it.also if a in main.items and not main.items[a].retired]
        chain[it.id] = e
    body = json.dumps(chain, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return (f"/* Generated by {TOOL} build from plan/objectives.md, plan/problems.md and plan/solutions.md.\n"
            "   Do not edit: change the plan and rebuild. */\n"
            f"window.TRACE_CHAIN = {body};\n")


def draft_outputs(draft, main, built=frozenset()):
    """The regenerated draft text and map; `missing` lists generated blocks without markers."""
    g = draft_graph(draft, main, built)
    text = draft.tf.text
    missing = []
    for name, content in (("tree", g.tree()), ("copied", copied_block(main))):
        new = replace_generated(text, name, content)
        if new is None:
            missing.append(name)
        else:
            text = new
    return text, render_map(g), missing


# --------------------------------------------------------------------------- bugs, reviews, what is built

def bugs(backlog):
    """The backlog's Bugs section: (line index, fixed?, text) for each "- [ ] ..." line."""
    out, inside = [], False
    if backlog is None:
        return out
    hidden = mask(backlog.lines)
    for i, ln in enumerate(backlog.lines):
        if hidden[i]:
            continue
        h = HEADING.match(ln)
        if h and len(h.group(1)) <= 2:
            inside = len(h.group(1)) == 2 and h.group(2).strip().lower().startswith("bugs")
            continue
        m = BUG_LINE.match(ln) if inside else None
        if m:
            out.append((i, m.group(1).lower() == "x", m.group(2)))
    return out


def read_review(path):
    """A review file's fields. A value still in "(...)" is the template's hint and counts as empty."""
    vals = {}
    if Path(path).exists():
        for ln in TextFile(path).text.split("\n"):
            m = re.match(r"^-\s+([A-Za-z][A-Za-z ]*?)\s*:\s?(.*)$", ln)
            key = m.group(1).lower() if m else None
            if key in REVIEW_KEYS and key not in vals:
                v = m.group(2).strip()
                vals[key] = "" if re.fullmatch(r"\(.*\)", v) else v
    return vals


def review_filled(vals):
    return bool(vals.get("date")) and bool(vals.get("reviewed by"))


def ids_in(text):
    return [f"{m.group(1)}-{m.group(2)}" for m in ID_RE.finditer(text or "")]


def saved_reviews():
    """Saved reviews, oldest first: (version, path)."""
    out = []
    for f in version_folders():
        for path in (f / "prototype" / "REVIEW.md", f / "review.md"):
            if path.exists():
                out.append((f.name, path))
    return out


def accepted_features():
    """Feature ID -> the review that last accepted it (a later "Not accepted" takes it back)."""
    acc = {}
    live = [("prototype/REVIEW.md", PROTO_REVIEW), ("product/REVIEW.md", PRODUCT_REVIEW)]
    for label, path in saved_reviews() + live:
        vals = read_review(path)
        if not review_filled(vals):
            continue
        for iid in ids_in(vals.get("accepted")):
            acc[iid] = label
        for iid in ids_in(vals.get("not accepted")):
            acc.pop(iid, None)
    return acc


def text_files(folder, skip_md=False):
    for f in sorted(Path(folder).rglob("*")):
        if not f.is_file() or any(part in SKIP_DIRS for part in f.relative_to(folder).parts[:-1]):
            continue
        if skip_md and f.suffix.lower() == ".md":
            continue
        try:
            yield f, TextFile(f).text
        except (UnicodeDecodeError, OSError):
            continue


def prototype_markers():
    """(file, line, ID) for every "!" marker in the live prototype."""
    out = []
    if PROTOTYPE.exists():
        for f, text in text_files(PROTOTYPE):
            if f.suffix.lower() not in (".html", ".htm", ".js") or TRACE in f.parents:
                continue
            for n, ln in enumerate(text.split("\n"), 1):
                chunks = [m.group(1) for m in TRACE_ATTR.finditer(ln)] + [m.group(1) for m in TRACE_JS.finditer(ln)]
                out += [(f, n, iid) for chunk in chunks for iid in ids_in(chunk)]
    return out


def product_ids():
    """(file, line, ID) for every plan ID named in the product's code (its .md notes are not code)."""
    out = []
    if PRODUCT.exists():
        for f, text in text_files(PRODUCT, skip_md=True):
            for n, ln in enumerate(text.split("\n"), 1):
                out += [(f, n, iid) for iid in ids_in(ln)]
    return out


def built_features(main):
    """Pushed features that the prototype (a "!" marker) or the product (its ID in code) builds."""
    found = {iid for _, _, iid in prototype_markers() + product_ids()}
    return frozenset(iid for iid in found if iid in main.items and main.items[iid].type == "feature"
                     and not main.items[iid].retired)


# --------------------------------------------------------------------------- versions and git

def version_folders():
    if not VERSIONS.exists():
        return []
    return sorted((p for p in VERSIONS.iterdir() if p.is_dir() and VERSION_RE.match(p.name)),
                  key=lambda p: version_key(p.name))


def log_lines():
    """The log's lines outside code fences (the entry-format example is not an entry)."""
    if not LOG.exists():
        return []
    lines = TextFile(LOG).text.split("\n")
    return [ln for ln, hidden in zip(lines, mask(lines)) if not hidden]


def reversed_versions():
    out, cur = set(), None
    for ln in log_lines():
        m = re.match(r"^##\s+(v[\d.]+)", ln)
        if m:
            cur = m.group(1).rstrip(".")
        m = re.match(r"^-\s+Rollback:\s*(.*)$", ln)
        if m and cur and m.group(1).strip().lower().startswith("reversed"):
            out.add(cur)
    return out


def logged_versions():
    return {m.group(1).rstrip(".") for ln in log_lines() for m in [re.match(r"^##\s+(v[\d.]+)", ln)] if m}


def latest_version(exclude_reversed=True):
    rev = reversed_versions() if exclude_reversed else set()
    folders = [p for p in version_folders() if p.name not in rev]
    return folders[-1] if folders else None


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None


def in_git():
    r = git("rev-parse", "--is-inside-work-tree")
    return bool(r) and r.returncode == 0 and r.stdout.strip() == "true"


def tag_exists(tag):
    r = git("rev-parse", "-q", "--verify", f"refs/tags/{tag}")
    return bool(r) and r.returncode == 0


def git_changes(base, spec):
    """(changed since base, untracked files, deleted files) for a list of pathspecs."""
    r = git("diff", "--quiet", base, "--", *spec)
    changed = bool(r) and r.returncode == 1
    s = git("status", "--porcelain", "--untracked-files=all", "--", *spec)
    lines = s.stdout.splitlines() if s else []
    return changed, [l[3:] for l in lines if l.startswith("??")], [l[3:] for l in lines if "D" in l[:2]]


def added_in(path):
    """The last commit that added this file (a move counts as adding it at its new place)."""
    r = git("log", "-1", "--diff-filter=A", "--format=%H", "--", rel(path))
    return r.stdout.strip() if r and r.returncode == 0 and r.stdout.strip() else None


def check_frozen_files(folder, issues, what):
    """Every file under a frozen folder must be unchanged since it was added (or last moved)."""
    waiting = False
    files = [Path(folder)] if Path(folder).is_file() else sorted(p for p in Path(folder).rglob("*") if p.is_file())
    for f in files:
        base = added_in(f)
        if not base:
            waiting = True
            continue
        changed, _, _ = git_changes(base, [rel(f)])
        if changed:
            issues.error(rel(f), 0, f"{what} was changed after it was saved")
    _, _, deleted = git_changes("HEAD", [rel(folder)])
    for d in deleted:
        issues.error(d, 0, f"{what} was deleted")
    if waiting:
        issues.warn(rel(folder), 0, "new files here are not committed yet; commit them")


# --------------------------------------------------------------------------- context

class Context:
    def __init__(self, main_texts=None, strict=None):
        self.issues = Issues()
        self.main = Main(PLAN, self.issues, texts=main_texts)
        self.drafts = find_drafts()
        self.strict = Path(strict).resolve() if strict else None
        self.backlog = next((d for d in self.drafts if d.is_backlog), None)
        self.open = [d for d in self.drafts if not d.is_backlog]
        btitles = set(self.backlog.by_title) if self.backlog else set()
        for d in self.drafts:
            resolve_draft(d, self.main, self.issues, btitles,
                          strict=bool(self.strict) and d.path.resolve() == self.strict)

    @staticmethod
    def frozen_paths():
        folders = [p for p in VERSIONS.iterdir() if p.is_dir()] if VERSIONS.exists() else []
        return folders + ([HISTORY] if HISTORY.exists() else [])


def draft_arg(value):
    if value and VERSION_RE.match(value):
        return DRAFTS / f"draft-{value}.md"
    return (Path.cwd() / value).resolve() if value else None


# --------------------------------------------------------------------------- check

def prototype_marker_issues(main, issues):
    for f, n, iid in prototype_markers():
        it = main.items.get(iid)
        if not it:
            issues.error(rel(f), n, f"marker uses {iid}, which is not pushed")
        elif it.retired:
            issues.error(rel(f), n, f"marker uses {iid}, which is retired")


def product_id_issues(main, issues):
    for f, n, iid in product_ids():
        it = main.items.get(iid)
        if not it:
            issues.error(rel(f), n, f"code names {iid}, which is not pushed")
        elif it.retired:
            issues.error(rel(f), n, f"code names {iid}, which is retired")


def review_and_bug_issues(ctx, issues):
    main = ctx.main
    for path in (PROTO_REVIEW, PRODUCT_REVIEW):
        vals = read_review(path)
        for key in ("accepted", "not accepted"):
            for iid in ids_in(vals.get(key)):
                it = main.items.get(iid)
                if not it or it.type != "feature":
                    issues.error(rel(path), 0, f'"{key.capitalize()}" lists {iid}, which is not a pushed feature')
    if ctx.backlog:
        for i, _, text in bugs(ctx.backlog):
            for iid in ids_in(text):
                it = main.items.get(iid)
                if not it:
                    issues.error(ctx.backlog.rel, i + 1, f"the bug names {iid}, which is not pushed")
                elif it.retired:
                    issues.warn(ctx.backlog.rel, i + 1, f"the bug names {iid}, which is retired")


def run_checks(ctx):
    issues, main = ctx.issues, ctx.main
    check_main(main, issues)
    fresh = served_by_texts(main)
    for doc, text in fresh.items():
        if text != main.files[doc].text:
            issues.error(rel(PLAN / doc), 0, '"Served by" lines are out of date; run build')
    built = built_features(main)
    if not PLAN_MAP.exists() or norm_text(TextFile(PLAN_MAP).text) != render_map(plan_graph(main, built)):
        issues.error(rel(PLAN_MAP), 0, "out of date; run build")
    # drafts
    if len(ctx.open) > 1:
        issues.error("drafts", 0, "only one draft can be open at a time (the next push): "
                                  + ", ".join(d.rel for d in ctx.open))
    titles = {}
    for d in ctx.drafts:
        s = d.status.lower()
        if not d.status:
            issues.error(d.rel, 0, 'no "**Status:**" line')
        elif d.is_backlog and s != "backlog":
            issues.error(d.rel, 0, 'the backlog\'s status is "Backlog"')
        elif not d.is_backlog and s != "active":
            issues.error(d.rel, 0, 'the open draft\'s status is "Active" (pushed drafts move to versions/vX/, '
                                   'abandoned ones to versions/abandoned/)')
        if not d.is_backlog:
            if not d.version:
                issues.error(d.rel, 0, "a draft is named draft-vX.md, after the version it will become")
            elif (VERSIONS / d.version).exists():
                issues.error(d.rel, 0, f"{d.version} is already pushed; this draft needs a new number")
            elif (ABANDONED / f"draft-{d.version}.md").exists():
                issues.error(d.rel, 0, f"{d.version} belonged to an abandoned draft; numbers are not reused")
        if not d.has_entries:
            issues.error(d.rel, 0, 'no "## Entries" section')
        for b in d.stray_levels:
            issues.warn(d.rel, b.line(), f'"{b.text}": entries are level-3 headings (###)')
        for e in d.entries:
            if e.type != "amendment":
                titles.setdefault(e.ntitle, []).append((d, e))
        text, html, missing = draft_outputs(d, main, built)
        for name in missing:
            issues.error(d.rel, 0, f"missing <!-- BEGIN/END GENERATED: {name} --> markers (see workflow/draft-template.md)")
        if text != d.tf.text:
            issues.error(d.rel, 0, "the generated overview or copied objectives and problems are out of date; run build")
        if not d.map_path.exists():
            issues.error(d.rel, 0, f"its map {d.map_path.name} is missing; run build")
        elif norm_text(TextFile(d.map_path).text) != html:
            issues.error(d.rel, 0, f"its map {d.map_path.name} does not match the text; run build")
    for t, where in titles.items():
        files = []
        for d, e in where:
            if all(d is not f for f, _ in files):
                files.append((d, e))
        if len(files) > 1:
            (d0, _), (d1, e1) = files[0], files[1]
            issues.warn(d1.rel, e1.block.line(), f'"{e1.title}" is also in {d0.rel}; ideas are moved, not copied')
    # versions and the log
    folders = version_folders()
    rev = reversed_versions()
    logged = logged_versions()
    for f in folders:
        if f.name not in logged:
            issues.warn(rel(LOG), 0, f"{f.name} has no entry in the log")
        for doc in MAIN_DOCS:
            if not (f / doc).exists():
                issues.error(rel(f), 0, f"{doc} is missing from this saved version")
    for v in logged:
        if not (VERSIONS / v).is_dir():
            issues.warn(rel(LOG), 0, f"the log has {v} but versions/{v}/ does not exist")
    latest = latest_version()
    if latest:
        differs = [doc for doc in MAIN_DOCS if (latest / doc).exists() and (PLAN / doc).exists()
                   and norm_text(TextFile(latest / doc).text) != norm_text(TextFile(PLAN / doc).text)]
        if differs:
            issues.warn("plan", 0, f"{', '.join(differs)} differ from the latest version ({latest.name}); "
                                   "that is only expected in the middle of a push")
    ever = {}
    for f in folders:
        if f.name in rev:
            continue
        for iid in Main(f, Issues()).items:
            ever.setdefault(iid, f.name)
    for iid, v in sorted(ever.items()):
        if iid not in main.items:
            issues.warn("plan", 0, f"{iid} was in {v} but is gone now; retire items instead of deleting them "
                                   "(only a rollback removes IDs)")
    # frozen files
    if in_git():
        for f in folders:
            # a saved prototype and a release review arrive after the tag; each is frozen from when it was added
            spec = [rel(f), f":(exclude){rel(f / 'prototype')}", f":(exclude){rel(f / 'review.md')}"]
            if tag_exists(f.name):
                changed, untracked, _ = git_changes(f.name, spec)
                if changed or untracked:
                    issues.error(rel(f), 0, f"a saved version was changed after tag {f.name}")
            elif f.name not in rev:
                issues.warn(rel(f), 0, f"no git tag {f.name} yet; commit, tag {f.name} and push")
            if (f / "prototype").exists():
                check_frozen_files(f / "prototype", issues, "a saved prototype")
            if (f / "review.md").exists():
                check_frozen_files(f / "review.md", issues, "a saved release review")
        if ABANDONED.exists():
            check_frozen_files(ABANDONED, issues, "an abandoned draft")
        if HISTORY.exists():
            check_frozen_files(HISTORY, issues, "a history file")
    else:
        issues.warn("git", 0, "not a git repository; frozen-file checks were skipped")
    # prototype
    if PROTOTYPE.exists():
        if not CHAIN_JS.exists() or norm_text(TextFile(CHAIN_JS).text) != chain_js(main):
            issues.error(rel(CHAIN_JS), 0, "out of date; run build")
    prototype_marker_issues(main, issues)
    product_id_issues(main, issues)
    review_and_bug_issues(ctx, issues)
    return issues


def print_issues(issues):
    order = {"error": 0, "todo": 1, "warn": 2}
    label = {"error": "ERROR", "todo": "TODO ", "warn": "WARN "}
    for level, where, line, msg in sorted(issues.items, key=lambda x: (order[x[0]], x[1], x[2])):
        loc = f"{where}:{line}" if line else where
        print(f"  {label[level]} {loc} \u2014 {msg}")
    n = {k: sum(1 for i in issues.items if i[0] == k) for k in order}
    print(f"\n{n['error']} errors, {n['todo']} to do, {n['warn']} warnings")
    return n


def summary(ctx):
    counts = {}
    for it in ctx.main.active():
        counts[it.type] = counts.get(it.type, 0) + 1
    parts = [f"{counts.get(t, 0)} {TYPE_NAME[t].lower()}{'' if counts.get(t, 0) == 1 else 's'}" for t in TYPE_NAME]
    latest = latest_version()
    phase = "product (v1.0 reached)" if latest and version_key(latest.name) >= (1, 0) else "prototype"
    print("Plan: " + ", ".join(parts) + f"  \u00b7  Phase: {phase}")
    print(f"Latest version: {latest.name if latest else 'none yet'}  \u00b7  "
          f"Open draft: {ctx.open[0].rel if ctx.open else 'none'}")


def cmd_check(args):
    strict = draft_arg(args.push)
    if strict and not strict.exists():
        raise SystemExit(f"No such draft: {args.push}")
    ctx = Context(strict=strict)
    summary(ctx)
    print()
    n = print_issues(run_checks(ctx))
    return 1 if n["error"] else 0


# --------------------------------------------------------------------------- build

def build(ctx, writer):
    fresh = served_by_texts(ctx.main)
    changed_main = False
    for doc, text in fresh.items():
        if writer.write(PLAN / doc, text):
            changed_main = True
    if changed_main:  # continue from the regenerated text (also correct in a dry run)
        ctx = Context(main_texts=fresh)
    built = built_features(ctx.main)
    writer.write(PLAN_MAP, render_map(plan_graph(ctx.main, built)))
    for d in ctx.drafts:
        text, html, missing = draft_outputs(d, ctx.main, built)
        for name in missing:
            print(f"  WARN  {d.rel} \u2014 no <!-- BEGIN/END GENERATED: {name} --> markers; that part was skipped")
        writer.write(d.path, text)
        writer.write(d.map_path, html)
    if PROTOTYPE.exists():
        writer.write(CHAIN_JS, chain_js(ctx.main))
    return ctx


def cmd_build(args):
    ctx = Context()
    writer = Writer(dry=args.dry_run, frozen=Context.frozen_paths())
    build(ctx, writer)
    verb = "Would update" if args.dry_run else "Updated"
    print(f"{verb}: " + (", ".join(writer.changed) if writer.changed else "nothing (already up to date)"))
    if args.dry_run:
        return 0
    print()
    ctx = Context()
    summary(ctx)
    print()
    n = print_issues(run_checks(ctx))
    return 1 if n["error"] else 0


# --------------------------------------------------------------------------- log entries, backlog moves, readiness

def entry_bounds(lines, v):
    """(start, end) of version v's entry among the log's lines, or None."""
    hidden = mask(lines)
    start = None
    for i, ln in enumerate(lines):
        m = None if hidden[i] else re.match(r"^##\s+(v[\d.]+)", ln)
        if m and start is not None:
            return start, i
        if m and m.group(1).rstrip(".") == v:
            start = i
    return (start, len(lines)) if start is not None else None


def log_value(text, v, key):
    lines = text.split("\n")
    b = entry_bounds(lines, v)
    if not b:
        return None
    for i in range(b[0] + 1, b[1]):
        m = re.match(rf"^-\s+{key}:\s*(.*)$", lines[i])
        if m:
            return m.group(1).strip()
    return None


def with_log_line(text, v, key, value):
    """Fill in one line of a version's entry (Prototype, Fixed, Released): replace it, or add it before Rollback."""
    lines = text.split("\n")
    b = entry_bounds(lines, v)
    if not b:
        raise SystemExit(f"{rel(LOG)} has no entry for {v}")
    body = range(b[0] + 1, b[1])
    line = f"- {key}: {value}"
    cur = next((i for i in body if re.match(rf"^-\s+{key}:", lines[i])), None)
    if cur is not None:
        lines[cur] = line
    else:
        rollback = next((i for i in body if re.match(r"^-\s+Rollback:", lines[i])), None)
        at = rollback if rollback is not None else max((i for i in body if lines[i].strip()), default=b[0]) + 1
        lines.insert(at, line)
    return "\n".join(lines)


def take_fixed_bugs(ctx, writer):
    """Remove the ticked bugs from the backlog and return their text."""
    fixed = [(i, text) for i, done, text in bugs(ctx.backlog) if done]
    if fixed:
        lines = list(ctx.backlog.lines)
        for i, _ in sorted(fixed, reverse=True):
            del lines[i]
        writer.write(BACKLOG, "\n".join(lines))
    return [text for _, text in fixed]


def entry_lines(draft, e):
    lines = draft.lines[e.block.start:e.block.end]
    while lines and (not lines[-1].strip() or RULE.match(lines[-1])):
        lines = lines[:-1]
    return lines


def backlog_with(backlog, moved):
    """The backlog's text with these lines added at the end of its Entries section."""
    blines = backlog.lines
    hidden = mask(blines)
    start = next((i for i, l in enumerate(blines) if not hidden[i] and re.match(r"^##\s+Entries", l)), None)
    if start is None:
        raise SystemExit(f'{rel(BACKLOG)} has no "## Entries" section')
    end = next((i for i in range(start + 1, len(blines))
                if not hidden[i] and re.match(r"^##\s", blines[i])), len(blines))
    at = end
    while at - 1 > start and (not blines[at - 1].strip() or RULE.match(blines[at - 1])):
        at -= 1
    tail = blines[at:end]
    return "\n".join(blines[:at] + [""] + moved + (["---", ""] if any(RULE.match(l) for l in tail) else [""])
                     + blines[end:])


def readiness(main):
    """What still stands between the prototype and v1.0."""
    active = main.active()
    served = {}
    for it in active:
        for parent in [it.serves] + it.also:
            served.setdefault(parent, []).append(it)
    kids = lambda it, types: [c for c in served.get(it.id, []) if c.type in types]
    features = [it for it in active if it.type == "feature"]
    built, accepted = built_features(main), accepted_features()

    def has_feature(s):
        return bool(kids(s, ("feature",))) or any(has_feature(c) for c in kids(s, ("sub-solution",)))
    r = {
        "Objectives with no problem": [o for o in active if o.type == "objective" and o.status != "done"
                                       and not kids(o, ("problem",))],
        "Open problems with no solution": [q for q in active if q.type == "problem" and q.status != "solved"
                                           and not kids(q, ("solution",))],
        "Solutions with no feature": [s for s in active if s.type in ("solution", "sub-solution") and not has_feature(s)],
        "Features with no \"Done when\"": [f for f in features if not f.done_when],
        "Features not built yet": [f for f in features if f.id not in built],
        "Features built but not accepted in a review": [f for f in features if f.id in built and f.id not in accepted],
    }
    blocking = ("Open problems with no solution", "Features not built yet", "Features built but not accepted in a review")
    missing = [k for k in blocking if r[k]] + ([] if features else ["No features pushed yet"])
    return r, not missing, missing


# --------------------------------------------------------------------------- IDs, drafts, pushes, prototypes

def all_ids():
    ids = set(Main(PLAN, Issues()).items)
    for f in version_folders():
        ids |= set(Main(f, Issues()).items)
    return ids


def next_ids():
    top = {"O": 0, "P": 0, "S": 0, "F": 0}
    for iid in all_ids():
        top[iid[0]] = max(top[iid[0]], int(iid[2:].split(".")[0]))
    return {k: f"{k}-{v + 1:03d}" for k, v in top.items()}


def cmd_next_ids(args):
    n = next_ids()
    print("Next free IDs (one above the highest ever used, including saved versions):")
    print(f"  Objective             {n['O']}")
    print(f"  Problem               {n['P']}")
    print(f"  Solution/Sub-solution {n['S']}")
    print(f"  Feature               {n['F']}")
    return 0


def check_new_version(v):
    if not VERSION_RE.match(v):
        raise SystemExit("A version looks like v0.2 or v0.1.1")
    if (VERSIONS / v).exists():
        raise SystemExit(f"{v} was already pushed; versions are never overwritten")
    if (ABANDONED / f"draft-{v}.md").exists():
        raise SystemExit(f"{v} belonged to a draft that was abandoned; numbers are not reused, pick the next one")
    latest = latest_version(exclude_reversed=False)
    if latest and version_key(v) <= version_key(latest.name):
        raise SystemExit(f"Version numbers only go up and are never reused: the latest is {latest.name}")


def cmd_new_draft(args):
    v = args.version
    check_new_version(v)
    ctx = Context()
    if ctx.open:
        raise SystemExit(f"Only one draft can be open at a time: push {ctx.open[0].rel} first "
                         f"(or give it up with: python {TOOL} abandon-draft).")
    text = TextFile(TEMPLATE_DRAFT).text.replace("vX", v)
    text = re.sub(r"^\*\*Status:\*\*.*$", "**Status:** Active", text, count=1, flags=re.M)
    writer = Writer(frozen=Context.frozen_paths())
    writer.write(DRAFTS / f"draft-{v}.md", text)
    build(Context(), writer)
    print("Created: " + ", ".join(writer.changed))
    return 0


def cmd_record_push(args):
    v = args.version
    check_new_version(v)
    ctx = Context()
    path = draft_arg(args.draft) if args.draft else (ctx.open[0].path if ctx.open else None)
    if not path:
        raise SystemExit("There is no open draft to push")
    draft = next((d for d in ctx.open if d.path.resolve() == Path(path).resolve()), None)
    if not draft:
        raise SystemExit(f"{args.draft or path} is not the open draft")
    ctx = Context(strict=draft.path)
    issues = run_checks(ctx)
    if any(i[0] == "error" for i in issues.items):
        print_issues(issues)
        raise SystemExit("\nNot recorded: fix the errors above first.")
    latest_any = latest_version(exclude_reversed=False)
    first_product = version_key(v) >= (1, 0) and not (latest_any and version_key(latest_any.name) >= (1, 0))
    gaps = None
    if first_product:
        r, ready, missing = readiness(ctx.main)
        if not ready and not args.accept_gaps:
            for k in missing:
                print(f"  {k}: " + ", ".join(it.id for it in r[k]))
            raise SystemExit(f"\nNot recorded: {v} starts the real product, but the prototype does not cover the whole "
                             "scope yet (see above and `status`). Close the gaps, or accept them in writing with "
                             "--accept-gaps \"why\".")
        gaps = args.accept_gaps
    target = VERSIONS / v
    prev_folder = latest_version()
    prev = Main(prev_folder, Issues()) if prev_folder else None
    writer = Writer(frozen=Context.frozen_paths())
    today = datetime.date.today().isoformat()
    # 1. the draft, as it was proposed (built against the version before this push), moves into its version
    before = prev if prev is not None else Main(PLAN, Issues(), texts={d: "" for d in MAIN_DOCS})
    d = Draft(draft.path)
    resolve_draft(d, before, Issues(), set(), strict=False)
    text, html, _ = draft_outputs(d, before)
    text = re.sub(r"^\*\*Status:\*\*.*$", f"**Status:** Pushed as {v} on {today}", text, count=1, flags=re.M)
    writer.write(target / d.path.name, text, allow_frozen=True)
    writer.write(target / d.map_path.name, html, allow_frozen=True)
    writer.remove(d.path)
    if d.map_path.exists():
        writer.remove(d.map_path)
    # 2. the plan as pushed, and its map
    for doc in MAIN_DOCS:
        writer.write(target / doc, ctx.main.files[doc].text, allow_frozen=True)
    for extra in (PROTOTYPE_BRIEF, CONSTRAINTS):
        if extra.exists():
            writer.write(target / extra.name, TextFile(extra).text, allow_frozen=True)
    writer.write(target / "mindmap.html", render_map(version_graph(v, ctx.main, prev)), allow_frozen=True)
    # 3. the log entry
    added, amended, retired = [], [], []
    for it in ctx.main.ordered():
        old = prev.items.get(it.id) if prev else None
        if it.retired and old and not old.retired:
            retired.append(it)
        elif not old:
            added.append(it)
        elif ctx.main.entry_text(it, drop_backlinks=True) != prev.entry_text(old, drop_backlinks=True):
            amended.append(it)

    def names(xs):
        return "; ".join(f"{x.id} {x.title}" for x in xs) or "none"
    entry = [f"## {v} ({today})", f"- Draft: {rel(target / d.path.name)}"]
    if args.note:
        entry.append(f"- Note: {' '.join(args.note.split())}")
    entry.append(f"- Approved by: {' '.join(args.approved_by.split())} on {today}")
    if gaps:
        entry.append(f"- Gaps accepted: {' '.join(gaps.split())}")
    entry += [f"- Added: {names(added)}", f"- Amended: {names(amended)}", f"- Retired: {names(retired)}",
              "- Released: not yet" if version_key(v) >= (1, 0) else "- Prototype: not saved yet", "- Rollback: none"]
    base = TextFile(LOG).text if LOG.exists() else "# Version log\n"
    writer.write(LOG, base.rstrip("\n") + "\n\n" + "\n".join(entry) + "\n")
    if version_key(v) >= (1, 0):
        for path, tpl in ((PRODUCT_DESIGN, TEMPLATE_DESIGN), (PRODUCT_REVIEW, TEMPLATE_REVIEW)):
            if not path.exists() and tpl.exists():
                writer.write(path, TextFile(tpl).text)
    print("Recorded " + v + ": " + ", ".join(writer.changed))
    if version_key(v) >= (1, 0):
        print(f"\nNext: commit everything, tag the commit {v}, and push the commit and the tag.\n"
              f"Then build {v}'s features in product/ (fill in product/design.md first if it is new), review them "
              f"in product/REVIEW.md, and release with: python {TOOL} record-release {v} --approved-by NAME")
    else:
        print(f"\nNext: commit everything, tag the commit {v}, and push the commit and the tag.\n"
              f"Then build the prototype for {v}, review it in prototype/REVIEW.md, and save it with: "
              f"python {TOOL} save-prototype {v}")
    return 0


def cmd_save_prototype(args):
    v = args.version
    latest = latest_version()
    if not latest or latest.name != v:
        raise SystemExit(f"Only the latest version's prototype can be saved (the latest is "
                         f"{latest.name if latest else 'none'})")
    target = VERSIONS / v / "prototype"
    if target.exists():
        raise SystemExit(f"{rel(target)} already exists; saved prototypes are never overwritten")
    files = [p for p in PROTOTYPE.rglob("*") if p.is_file()] if PROTOTYPE.exists() else []
    if not files:
        raise SystemExit("prototype/ is empty; there is nothing to save")
    issues = Issues()
    prototype_marker_issues(Main(PLAN, Issues()), issues)
    if issues.items:
        print_issues(issues)
        raise SystemExit("\nNot saved: fix the markers above first.")
    review = read_review(PROTO_REVIEW)
    if not review_filled(review):
        raise SystemExit(f"Review first: fill in {rel(PROTO_REVIEW)} (date, who reviewed, features accepted, findings). "
                         "Findings go to the backlog.")
    if review.get("version") and review["version"] != v:
        raise SystemExit(f"{rel(PROTO_REVIEW)} reviews {review['version']}, not {v}")
    ctx = Context()
    writer = Writer(frozen=Context.frozen_paths())
    for f in sorted(files):
        writer.copy(f, target / f.relative_to(PROTOTYPE), allow_frozen=True)
    if TEMPLATE_REVIEW.exists():
        writer.write(PROTO_REVIEW, TextFile(TEMPLATE_REVIEW).text)
    fixed = take_fixed_bugs(ctx, writer)
    # fill in the version's lines in the log (with Released and Rollback, the only lines that change in an entry)
    today = datetime.date.today().isoformat()
    log = with_log_line(TextFile(LOG).text, v, "Prototype", f"saved on {today}")
    if fixed:
        log = with_log_line(log, v, "Fixed", "; ".join(fixed))
    writer.write(LOG, log)
    print(f"Saved the prototype for {v}: {rel(target)}/ ({len(files)} files). Commit it.")
    return 0


def cmd_abandon_draft(args):
    ctx = Context()
    path = draft_arg(args.draft) if args.draft else (ctx.open[0].path if ctx.open else None)
    draft = next((d for d in ctx.open if path and d.path.resolve() == Path(path).resolve()), None)
    if not draft:
        raise SystemExit("There is no open draft to abandon")
    if not ctx.backlog:
        raise SystemExit(f"{rel(BACKLOG)} is missing")
    target = ABANDONED / draft.path.name
    if target.exists():
        raise SystemExit(f"{rel(target)} already exists")
    # 1. the entries go back to the backlog, word for word, at the end of its Entries section
    moved = []
    for e in draft.entries:
        moved += entry_lines(draft, e) + [""]
    writer = Writer(frozen=Context.frozen_paths())
    writer.write(BACKLOG, backlog_with(ctx.backlog, moved))
    # 2. the draft is kept as a frozen record; its number is never reused
    today = datetime.date.today().isoformat()
    text = re.sub(r"^\*\*Status:\*\*.*$", f"**Status:** Retired on {today} (abandoned; its entries went back "
                  "to the backlog)", draft.tf.text, count=1, flags=re.M)
    writer.write(target, text, allow_frozen=True)
    if draft.map_path.exists():
        writer.copy(draft.map_path, ABANDONED / draft.map_path.name, allow_frozen=True)
        writer.remove(draft.map_path)
    writer.remove(draft.path)
    build(Context(), writer)
    print(f"Abandoned {draft.rel}: {len(draft.entries)} entries went back to the backlog; the draft is kept in "
          f"{rel(target)}. Updated: " + ", ".join(writer.changed))
    return 0


def cmd_status(args):
    ctx = Context()
    main = ctx.main
    summary(ctx)
    r, ready, missing = readiness(main)
    accepted = accepted_features()
    active = main.active()

    quiet = []

    def show(title, items):
        if not items:
            quiet.append(title[0].lower() + title[1:])
            return
        print(f"\n{title} ({len(items)}):")
        for x in items:
            print("  - " + x)
    for k, items in r.items():
        show(k, [f"{it.id} {it.title}" for it in items])
    built = built_features(main)
    waiting = [f for f in active if f.type == "feature" and f.id not in built and any(n not in built for n in f.needs)]
    show("Features waiting for what they need", [f"{f.id} {f.title} (needs {', '.join(n for n in f.needs if n not in built)})"
                                                 for f in waiting])
    show("Accepted features", [f"{iid} ({where})" for iid, where in sorted(accepted.items())])
    show("Open questions", [f"{it.id}: {' '.join(it.questions.split())}" for it in active if it.questions])
    open_bugs = [text for _, done, text in bugs(ctx.backlog) if not done]
    show("Open bugs", open_bugs)
    if ctx.backlog:
        counts = {}
        for e in ctx.backlog.entries:
            if e.type != "amendment":
                counts[e.priority.capitalize() if e.priority in PRIORITIES else "No priority"] = \
                    counts.get(e.priority.capitalize() if e.priority in PRIORITIES else "No priority", 0) + 1
        print("\nBacklog: " + (", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "empty"))
    if quiet:
        print("\nNothing to report for: " + "; ".join(quiet) + ".")
    problems = [q for q in active if q.type == "problem"]
    objectives = [o for o in main.items.values() if o.type == "objective"]
    print(f"Problems solved: {sum(q.status == 'solved' for q in problems)} of {len(problems)}  \u00b7  "
          f"Objectives done: {sum(o.status == 'done' for o in objectives if not o.retired)} of "
          f"{sum(not o.retired for o in objectives)}")
    latest = latest_version()
    if not (latest and version_key(latest.name) >= (1, 0)):
        print("\nReady for v1.0: " + ("yes" if ready else "no (" + "; ".join(m.lower() for m in missing) + ")"))
    if objectives and all(o.status == "done" or o.retired for o in objectives):
        print("\nEvery objective is Done or Retired: close the project with a final version and a closing note.")
    return 0


FIELD_ORDER = ("description", "serves", "also serves", "needs", "done when", "design location", "label",
               "open questions", "status")


def field_lines(name, value):
    parts = [p.strip() for p in str(value).split("\n")] or [""]
    return [f"- {name}: {parts[0]}"] + ["  " + p for p in parts[1:] if p]


def is_field(line):
    m = FIELD.match(line)
    return bool(m) and field_name(m.group(1)) is not None


def set_field(texts, iid, name, value):
    """Replace (or add) one field of a pushed item, in memory."""
    m = Main(PLAN, Issues(), texts=texts)
    it = m.items[iid]
    lines, b, key = texts[it.doc].split("\n"), it.block, name.lower()
    new = field_lines(name, value)
    if key in b.fields:
        i = b.fields[key][1]
        j = i + 1
        while j < b.end and lines[j].strip() and not is_field(lines[j]) and not HEADING.match(lines[j]) \
                and not RULE.match(lines[j]):
            j += 1
        lines[i:j] = new
    else:
        at = b.fields["served by"][1] if "served by" in b.fields else \
            max((k for k in range(b.start, b.end) if lines[k].strip() and not RULE.match(lines[k])), default=b.start) + 1
        lines[at:at] = new
    texts[it.doc] = "\n".join(lines)


def region_end(lines, start, level):
    """Where the part of solutions.md that belongs to the heading at `start` ends."""
    hidden = mask(lines)
    for i in range(start + 1, len(lines)):
        h = None if hidden[i] else HEADING.match(lines[i])
        if h and len(h.group(1)) <= level:
            return i
    return len(lines)


def insert_block(lines, pos, block):
    q = pos
    while q > 0 and not lines[q - 1].strip():
        q -= 1
    after = [""] if q < len(lines) and lines[q].strip() else []
    return lines[:q] + [""] + block + after + lines[q:]


def finish(text):
    return text.rstrip("\n") + "\n"


def cmd_apply_draft(args):
    ctx = Context()
    if not ctx.open:
        raise SystemExit("There is no open draft to apply")
    first = ctx.open[0]
    skip = {norm_title(s) for s in (args.skip or [])}
    unknown = [s for s in (args.skip or []) if norm_title(s) not in first.by_title]
    if unknown:
        raise SystemExit("Not in the draft: " + ", ".join(f'"{s}"' for s in unknown))
    ctx = Context(strict=first.path)
    issues = run_checks(ctx)
    draft, main = ctx.open[0], ctx.main
    skipped = [e for e in draft.entries if e.ntitle in skip]
    spans = [(e.block.start + 1, e.block.end) for e in skipped]
    errors = Issues()
    errors.items = [i for i in issues.items if i[0] == "error"
                    and not (i[1] == draft.rel and any(a <= i[2] <= z for a, z in spans))]
    if errors.items:
        print_issues(errors)
        raise SystemExit("\nNot applied: fix the errors above first (or send those entries back with --skip).")
    approved = [e for e in draft.entries if e.ntitle not in skip]
    for e in approved:
        for r in ([e.home] if e.home else []) + e.also + e.needs:
            if r[0] == "entry" and r[1].ntitle in skip:
                raise SystemExit(f'"{e.title}" leans on "{r[1].title}", which is being sent back to the backlog')
    new = [e for e in approved if e.type in TYPE_NAME]
    amends = [e for e in approved if e.type == "amendment"]
    counters = {k: int(v[2:]) for k, v in next_ids().items()}
    rank = {"objective": 0, "problem": 1, "solution": 2, "sub-solution": 3, "feature": 4}
    prefix = {"objective": "O", "problem": "P", "solution": "S", "sub-solution": "S", "feature": "F"}
    newid = {}
    for e in sorted(new, key=lambda e: (rank[e.type], e.index)):
        k = prefix[e.type]
        newid[e.key] = f"{k}-{counters[k]:03d}"
        counters[k] += 1

    def rid(r):
        return r[1].id if r[0] == "item" else newid[r[1].key]

    def render(e):
        b = e.block
        level = {"objective": 2, "problem": 2, "solution": 2, "sub-solution": 3, "feature": 4}[e.type]
        out = [f"{'#' * level} {newid[e.key]}: {e.title}"] + field_lines("Description", b.get("description"))
        if e.type != "objective":
            out += [f"- Serves: {rid(e.home)}", f"- Also serves: {', '.join(rid(r) for r in e.also) or 'none'}"]
        if e.type == "feature":
            if e.needs:
                out.append(f"- Needs: {', '.join(rid(r) for r in e.needs)}")
            out += field_lines("Done when", b.get("done when")) + field_lines("Design location", b.get("design location"))
        if b.get("label").strip():
            out.append(f"- Label: {b.get('label').strip()}")
        if open_questions(b.get("open questions")):
            out += field_lines("Open questions", b.get("open questions"))
        if e.type in ("objective", "problem"):
            out.append("- Status: Open")
        return out

    texts = {doc: main.files[doc].text for doc in MAIN_DOCS}
    # 1. new objectives and problems go at the end of their documents
    for kind, doc in (("objective", "objectives.md"), ("problem", "problems.md")):
        lines = texts[doc].split("\n")
        for e in [e for e in new if e.type == kind]:
            lines = insert_block(lines, len(lines), render(e))
        texts[doc] = finish("\n".join(lines))
    # 2. solutions, sub-solutions and features go under their home parent in solutions.md
    children = {}
    for e in new:
        if e.type in ("sub-solution", "feature") and e.home[0] == "entry":
            children.setdefault(e.home[1].key, []).append(e)

    def subtree(e):
        out = render(e)
        for c in sorted(children.get(e.key, []), key=lambda c: (rank[c.type], c.index)):
            out += [""] + subtree(c)
        return out
    for e in sorted([e for e in new if e.type == "solution"], key=lambda e: e.index):
        lines = texts["solutions.md"].split("\n")
        texts["solutions.md"] = finish("\n".join(insert_block(lines, len(lines), subtree(e))))
    for e in sorted([e for e in new if e.type in ("sub-solution", "feature") and e.home[0] == "item"],
                    key=lambda e: (rank[e.type], e.index)):
        parent = Main(PLAN, Issues(), texts=texts).items[e.home[1].id]
        lines = texts["solutions.md"].split("\n")
        at = region_end(lines, parent.block.start, parent.block.level)
        texts["solutions.md"] = finish("\n".join(insert_block(lines, at, subtree(e))))
    # 3. amendments change pushed items in place
    for e in amends:
        iid, b = e.amends.id, e.block
        cur = Main(PLAN, Issues(), texts=texts).items[iid]
        if b.get("new text").strip():
            set_field(texts, iid, "Description", b.get("new text"))
        if e.home:
            set_field(texts, iid, "Serves", rid(e.home))
        if e.also or e.remove:
            also = [a for a in cur.also if a not in e.remove] + [rid(r) for r in e.also if rid(r) not in cur.also]
            set_field(texts, iid, "Also serves", ", ".join(also) or "none")
        if e.needs:
            set_field(texts, iid, "Needs", ", ".join(rid(r) for r in e.needs))
        for name in ("Done when", "Design location", "Label"):
            if b.get(name.lower()).strip():
                set_field(texts, iid, name, b.get(name.lower()))
        if open_questions(b.get("open questions")):
            set_field(texts, iid, "Open questions", b.get("open questions"))
        if e.status:
            set_field(texts, iid, "Status", e.status.capitalize())
        if e.retire:
            set_field(texts, iid, "Status", "Retired")
        if e.home and cur.type == "feature":  # a moved feature also moves under its new home parent
            it = Main(PLAN, Issues(), texts=texts).items[iid]
            lines = texts[it.doc].split("\n")
            block = lines[it.block.start:it.block.end]
            while block and not block[-1].strip():
                block = block[:-1]
            del lines[it.block.start:it.block.end]
            texts[it.doc] = "\n".join(lines)
            parent = Main(PLAN, Issues(), texts=texts).items[rid(e.home)]
            lines = texts[it.doc].split("\n")
            at = region_end(lines, parent.block.start, parent.block.level)
            texts[it.doc] = finish("\n".join(insert_block(lines, at, block)))
    # 4. entries not approved go back to the backlog
    writer = Writer(dry=args.dry_run, frozen=Context.frozen_paths())
    if skipped:
        moved = []
        pushed_titles = {e.ntitle: newid[e.key] for e in new}
        for e in skipped:
            for ln in entry_lines(draft, e):
                fm = FIELD.match(ln)
                if fm and field_name(fm.group(1)) in ("serves", "also serves", "needs"):
                    ln = QUOTED.sub(lambda m: pushed_titles.get(norm_title(m.group(1) or m.group(2)), m.group(0)), ln)
                moved.append(ln)
            moved.append("")
        writer.write(BACKLOG, backlog_with(ctx.backlog, moved))
        lines = list(draft.lines)
        for e in sorted(skipped, key=lambda e: e.block.start, reverse=True):
            del lines[e.block.start:e.block.end]
        writer.write(draft.path, "\n".join(lines))
    print("New IDs: " + ("; ".join(f"{newid[e.key]} {e.title}" for e in sorted(new, key=lambda e: (rank[e.type], e.index)))
                         or "none"))
    after = Main(PLAN, Issues(), texts=texts)
    changed = [e.amends.id for e in amends
               if main.entry_text(main.items[e.amends.id]) != after.entry_text(after.items[e.amends.id])]
    print("Amended: " + ("; ".join(changed) or "none"))
    print("Sent back to the backlog: " + ("; ".join(e.title for e in skipped) or "none"))
    for doc in MAIN_DOCS:
        writer.write(PLAN / doc, texts[doc])
    if args.dry_run:
        print("\nDry run: nothing was written.")
        return 0
    build(Context(), writer)
    print("Updated: " + ", ".join(writer.changed))
    v = draft.version or "vX"
    print(f"\nNext: look over plan/ (git diff plan/), run check, then: python {TOOL} record-push {v} --approved-by NAME")
    return 0


def cmd_record_release(args):
    v = args.version
    if not VERSION_RE.match(v) or version_key(v) < (1, 0):
        raise SystemExit("Releases start at v1.0 (the prototype is saved with save-prototype before that)")
    if not (VERSIONS / v).is_dir():
        raise SystemExit(f"{v} is not pushed")
    log = TextFile(LOG).text
    done = log_value(log, v, "Released")
    if done is None or not done.lower().startswith("not yet"):
        raise SystemExit(f"{v} is already released ({done})" if done else f"{rel(LOG)} has no Released line for {v}")
    target = VERSIONS / v / "review.md"
    if target.exists():
        raise SystemExit(f"{rel(target)} already exists")
    review = read_review(PRODUCT_REVIEW)
    if not review_filled(review):
        raise SystemExit(f"Review first: fill in {rel(PRODUCT_REVIEW)} (date, who reviewed, features accepted, findings). "
                         "Findings go to the backlog.")
    if review.get("version") and review["version"] != v:
        raise SystemExit(f"{rel(PRODUCT_REVIEW)} reviews {review['version']}, not {v}")
    ctx = Context()
    issues = Issues()
    product_id_issues(ctx.main, issues)
    if issues.items:
        print_issues(issues)
        raise SystemExit("\nNot released: fix the code's feature IDs above first.")
    writer = Writer(frozen=Context.frozen_paths())
    writer.copy(PRODUCT_REVIEW, target, allow_frozen=True)
    if TEMPLATE_REVIEW.exists():
        writer.write(PRODUCT_REVIEW, TextFile(TEMPLATE_REVIEW).text)
    fixed = take_fixed_bugs(ctx, writer)
    today = datetime.date.today().isoformat()
    log = with_log_line(log, v, "Released", f"{today}, approved by {' '.join(args.approved_by.split())}")
    if fixed:
        before = log_value(log, v, "Fixed")
        log = with_log_line(log, v, "Fixed", "; ".join(([before] if before else []) + fixed))
    writer.write(LOG, log)
    print(f"Released {v}: " + ", ".join(writer.changed))
    print(f"\nNext: commit, tag the commit {v}-release, and push the commit and the tag.")
    return 0


# --------------------------------------------------------------------------- main

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Check and generate everything derived in this workflow.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="report problems; changes nothing")
    c.add_argument("--push", metavar="DRAFT", help="also require every entry of this draft to be complete")
    b = sub.add_parser("build", help="regenerate everything derived from the text")
    b.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    sub.add_parser("next-ids", help="next free ID of each kind")
    n = sub.add_parser("new-draft", help="start the next draft (only when no draft is open)")
    n.add_argument("version")
    r = sub.add_parser("record-push", help="save versions/VERSION/, add the log entry, move the draft there")
    r.add_argument("version")
    r.add_argument("--draft", metavar="DRAFT", help="the draft being pushed (default: the open draft)")
    r.add_argument("--note", metavar="TEXT", help="one line for the log about what this version is")
    r.add_argument("--approved-by", metavar="NAME", required=True, help="who gave the green light")
    r.add_argument("--accept-gaps", metavar="WHY", help="for v1.0 only: go ahead although the prototype has gaps, and why")
    sub.add_parser("status", help="what is covered, built, accepted, open, and still missing")
    ap = sub.add_parser("apply-draft", help="write the open draft's entries into plan/ with new IDs")
    ap.add_argument("--skip", metavar="TITLE", action="append", help="an entry not approved: it goes back to the backlog")
    ap.add_argument("--dry-run", action="store_true", help="show the new IDs without writing")
    rr = sub.add_parser("record-release", help="release a version of the product (from v1.0)")
    rr.add_argument("version")
    rr.add_argument("--approved-by", metavar="NAME", required=True, help="who approved the release")
    s = sub.add_parser("save-prototype", help="save the live prototype into versions/VERSION/prototype/")
    s.add_argument("version")
    a = sub.add_parser("abandon-draft", help="give up the open draft; its entries go back to the backlog")
    a.add_argument("--draft", metavar="DRAFT", help="the draft to abandon (default: the open draft)")
    args = p.parse_args(argv)
    return {"check": cmd_check, "build": cmd_build, "next-ids": cmd_next_ids, "new-draft": cmd_new_draft,
            "record-push": cmd_record_push, "save-prototype": cmd_save_prototype,
            "abandon-draft": cmd_abandon_draft, "status": cmd_status, "apply-draft": cmd_apply_draft,
            "record-release": cmd_record_release}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
