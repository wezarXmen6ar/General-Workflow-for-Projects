#!/usr/bin/env python3
"""Checks and generates everything derived in this workflow.

Run from the project root (or anywhere; paths are relative to the folder above tools/):

  python tools/workflow.py check [--push DRAFT]    report problems; changes nothing
  python tools/workflow.py build [--dry-run]       regenerate back-links, draft overviews, copies, maps, prototype chain
  python tools/workflow.py next-ids                next free ID of each kind
  python tools/workflow.py new-draft VERSION
                                                   create drafts/VERSION/ (only when no other draft is open)
  python tools/workflow.py record-push VERSION [--draft DRAFT]
                                                   save versions/VERSION/, add the log entry, freeze the draft

DRAFT is a path (drafts/v0.2/draft-v0.2.md) or a version (v0.2).
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
MAIN_DOCS = ["objectives.md", "problems.md", "solutions.md"]
DRAFTS = ROOT / "drafts"
BACKLOG = DRAFTS / "backlog" / "backlog.md"
VERSIONS = ROOT / "versions"
LOG = VERSIONS / "log.md"
TEMPLATE_MAP = ROOT / "templates" / "mindmap.html"
TEMPLATE_DRAFT = ROOT / "templates" / "draft.md"
PROTOTYPE = ROOT / "prototype"
CHAIN_JS = PROTOTYPE / "chain.js"

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
FIELDS = {"type", "description", "idea", "serves", "home parent", "also serves", "amends",
          "retire", "label", "design location", "open questions", "status", "served by"}
ALIAS = {"idea": "description", "home parent": "serves"}
ID_HEAD = re.compile(r"^([OPSF])-(\d{3,})\b\s*[:.\u2014\u2013-]?\s*(.*)$")
ID_RE = re.compile(r"\b([OPSF])-(\d{3,})\b")
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
        if rel(path) not in self.changed:
            self.changed.append(rel(path))
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return True


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


# --------------------------------------------------------------------------- main documents

class Item:
    def __init__(self, iid, title, doc, block, seq):
        self.id, self.prefix, self.num = iid, iid[0], int(iid[2:])
        self.title, self.doc, self.block, self.seq = title, doc, block, seq
        self.type = {"O": "objective", "P": "problem", "S": "solution", "F": "feature"}[self.prefix]
        self.serves, self.also, self.status = None, [], ""
        self.label = block.get("label")
        self.retired = False

    @property
    def name(self):
        return f"{self.title} ({self.id})"


class Main:
    """The three main documents (or a saved version of them)."""

    def __init__(self, folder, issues=None, texts=None, label=None):
        self.folder, self.items, self.files, self.lines = Path(folder), {}, {}, {}
        self.by_title = {}
        issues = issues if issues is not None else Issues()
        where = label or ""
        seq = 0
        for doc in MAIN_DOCS:
            path = self.folder / doc
            if texts and doc in texts:
                tf = TextFile(path, texts[doc])
            elif path.exists():
                tf = TextFile(path)
            else:
                issues.error(where + doc, 0, "file is missing")
                continue
            self.files[doc] = tf
            lines = tf.text.split("\n")
            self.lines[doc] = lines
            for b in parse_blocks(lines, mask(lines)):
                m = ID_HEAD.match(b.text)
                if not m:
                    if b.level >= 2 and b.fields:
                        issues.warn(where + doc, b.line(), f'heading "{b.text}" has fields but no ID')
                    continue
                iid = f"{m.group(1)}-{m.group(2)}"
                if PREFIX_DOC[m.group(1)] != doc:
                    issues.error(where + doc, b.line(), f"{iid} belongs in {PREFIX_DOC[m.group(1)]}")
                if iid in self.items:
                    issues.error(where + doc, b.line(), f"{iid} is used twice")
                    continue
                seq += 1
                it = Item(iid, m.group(3).strip(), doc, b, seq)
                self.items[iid] = it
                self.by_title.setdefault(norm_title(it.title), it)
        for it in self.items.values():
            refs, _ = parse_refs(it.block.get("serves"))
            ids = [r[1] for r in refs if r[0] == "id"]
            it.serves = ids[0] if ids else None
            arefs, _ = parse_refs(it.block.get("also serves"))
            it.also = [r[1] for r in arefs if r[0] == "id"]
            it.status = " ".join(it.block.get("status").split()).lower()
            it.retired = it.status == "retired"
        for it in self.items.values():  # a solution that serves a solution is a sub-solution
            if it.prefix == "S" and it.serves and it.serves.startswith("S-"):
                it.type = "sub-solution"

    def active(self):
        return [it for it in self.items.values() if not it.retired]

    def ordered(self, items=None):
        return sorted(items if items is not None else self.items.values(), key=lambda x: x.seq)

    def entry_text(self, it, shift=0, drop_served_by=False):
        lines = self.lines[it.doc][it.block.start:it.block.end]
        while lines and (not lines[-1].strip() or RULE.match(lines[-1])):
            lines = lines[:-1]
        out = []
        for i, ln in enumerate(lines):
            if drop_served_by and FIELD.match(ln) and field_name(FIELD.match(ln).group(1)) == "served by":
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
        where, b = it.doc, it.block
        if not it.title:
            issues.error(where, b.line(), f"{it.id} has no title")
        if not b.get("description").strip():
            issues.todo(where, b.line(), f"{it.id} has no description")
        if it.type == "objective":
            if it.status not in ("open", "done"):
                issues.error(where, b.line("status"), f"{it.id}: Status must be Open or Done")
            if b.get("serves").strip() and b.get("serves").strip().lower() != "none":
                issues.warn(where, b.line("serves"), f"{it.id}: objectives have no parent; Serves is ignored")
        else:
            allowed = ALLOWED[it.type]
            refs, stray = parse_refs(b.get("serves"))
            if any(r[0] == "title" for r in refs) or stray:
                issues.error(where, b.line("serves"), f"{it.id}: in the main documents, Serves must be an ID")
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
                issues.error(where, b.line("also serves"), f"{it.id}: in the main documents, Also serves must list IDs")
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
            if it.type == "problem" and it.status not in ("open", "solved", "retired"):
                issues.error(where, b.line("status"), f"{it.id}: Status must be Open, Solved or Retired")
            if it.type in ("solution", "sub-solution", "feature") and it.status not in ("", "active", "retired"):
                issues.error(where, b.line("status"), f"{it.id}: Status is either left out or Retired")
            if it.type == "feature" and not b.get("design location").strip():
                issues.warn(where, b.line(), f"{it.id} has no Design location")
        want = {"objective": 2, "problem": 2, "solution": 2, "sub-solution": 3, "feature": 4}[it.type]
        if b.level != want:
            issues.warn(where, b.line(), f"{it.id} ({TYPE_NAME[it.type]}) is usually a level-{want} heading")
    for it in main.items.values():
        if it.type == "objective" and it.status == "done":
            for p in main.active():
                if p.type == "problem" and (p.serves == it.id or it.id in p.also) and p.status != "solved":
                    issues.warn(it.doc, it.block.line("status"), f"{it.id} is Done but {p.id} is not Solved")


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


class Draft:
    def __init__(self, path):
        self.path = Path(path)
        self.rel = rel(path)
        self.tf = TextFile(path)
        self.lines = self.tf.text.split("\n")
        self.is_backlog = self.path.resolve() == BACKLOG.resolve()
        self.title = next((HEADING.match(l).group(2) for l in self.lines
                           if HEADING.match(l) and len(HEADING.match(l).group(1)) == 1), self.path.stem)
        self.status = ""
        for ln in self.lines:
            m = STATUS_LINE.match(ln)
            if m:
                self.status = m.group(1)
                break
        s = self.status.lower()
        self.frozen = s.startswith("pushed") or s.startswith("retired")
        self.active = s == "active"
        m = re.match(r"pushed as (v[\d.]+)", s)
        self.pushed_as = m.group(1).rstrip(".") if m else None
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
        for folder in sorted(DRAFTS.iterdir(), key=lambda p: p.name):
            if folder.is_dir() and folder.name not in ("backlog",):
                for f in sorted(folder.glob("draft-*.md")):
                    out.append(Draft(f))
    return out


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

        serves_raw = b.get("serves")
        refs, stray = parse_refs(serves_raw)
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

    def node(self, key, type_, full, short, ref="", mark="", seq=0):
        if key not in self.nodes:
            self.nodes[key] = {"key": key, "type": type_, "full": full, "short": short,
                               "ref": ref, "mark": mark if self.highlight else "", "seq": seq}
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
            s = n["full"] + (f" ({n['ref']})" if n["ref"] else "")
            return s

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


def draft_graph(draft, main):
    """Pushed context (all objectives and problems, plus the chains this draft touches) and the draft's own entries."""
    highlight = bool(main.items)
    who = "backlog.md" if draft.is_backlog else draft.path.name
    g = Graph(draft.title, f"Generated from {who} by tools/workflow.py \u2014 edit the text, not this map", highlight)
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
        g.node(iid, it.type, it.title, short_label(it.title, it.label), iid, mark, it.seq)
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
        elif old and main.entry_text(it, drop_served_by=True) != prev.entry_text(old, drop_served_by=True):
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


def copied_block(main):
    out = []
    for doc, heading in (("objectives.md", "Objectives"), ("problems.md", "Problems")):
        items = [it for it in main.ordered() if it.doc == doc]
        if items:
            out += [f"### {heading}", ""]
            for it in items:
                out += main.entry_text(it, shift=2) + [""]
    if not out:
        return "No objectives or problems have been pushed yet."
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


def render_map(graph):
    tpl = TextFile(TEMPLATE_MAP).text
    if not DATA_BLOCK.search(tpl):
        raise SystemExit(f"{rel(TEMPLATE_MAP)} has no /* BEGIN DATA */ ... /* END DATA */ block")
    data = graph.data()
    head = "/* BEGIN DATA (generated by tools/workflow.py build; edit the text, not this map) */"
    out = DATA_BLOCK.sub(lambda m: head + "\n" + js_data(data) + "\n/* END DATA */", tpl, count=1)
    title = "<title>" + html_escape(data["version"]) + " \u00b7 map</title>"
    return re.sub(r"<title>.*?</title>", lambda m: title, out, count=1)


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def chain_js(main):
    chain = {}
    for it in main.ordered(main.active()):
        e = {"type": TYPE_NAME[it.type], "name": it.title}
        if it.type != "objective":
            e["home"] = it.serves
            e["also"] = [a for a in it.also if a in main.items and not main.items[a].retired]
        chain[it.id] = e
    body = json.dumps(chain, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return ("/* Generated by tools/workflow.py build from objectives.md, problems.md and solutions.md.\n"
            "   Do not edit: change the documents and rebuild. */\n"
            f"window.TRACE_CHAIN = {body};\n")


def draft_outputs(draft, main):
    """The regenerated draft text and map, or None where the draft has no generated markers."""
    g = draft_graph(draft, main)
    text = draft.tf.text
    missing = []
    for name, content in (("tree", g.tree()), ("copied", copied_block(main))):
        new = replace_generated(text, name, content)
        if new is None:
            missing.append(name)
        else:
            text = new
    return text, render_map(g), missing


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


def changed_since(tag, path):
    r = git("diff", "--quiet", tag, "--", rel(path))
    changed = bool(r) and r.returncode == 1
    u = git("status", "--porcelain", "--untracked-files=all", "--", rel(path))
    untracked = bool(u) and any(l.startswith("??") for l in u.stdout.splitlines())
    return changed or untracked


# --------------------------------------------------------------------------- context

class Context:
    def __init__(self, main_texts=None, strict=None):
        self.issues = Issues()
        self.main = Main(ROOT, self.issues, texts=main_texts)
        self.drafts = find_drafts()
        self.strict = Path(strict).resolve() if strict else None
        self.backlog = next((d for d in self.drafts if d.is_backlog), None)
        btitles = set(self.backlog.by_title) if self.backlog else set()
        for d in self.drafts:
            if not d.frozen:
                resolve_draft(d, self.main, self.issues, btitles,
                              strict=bool(self.strict) and d.path.resolve() == self.strict)

    def frozen_paths(self):
        paths = [p for p in version_folders()]
        paths += [d.path.parent for d in self.drafts if d.frozen and not d.is_backlog]
        return paths


def draft_arg(value):
    if value and VERSION_RE.match(value):
        return DRAFTS / value / f"draft-{value}.md"
    return (Path.cwd() / value).resolve() if value else None


# --------------------------------------------------------------------------- check

def run_checks(ctx):
    issues, main = ctx.issues, ctx.main
    check_main(main, issues)
    fresh = served_by_texts(main)
    for doc, text in fresh.items():
        if text != main.files[doc].text:
            issues.error(doc, 0, '"Served by" lines are out of date; run build')
    # drafts
    open_drafts = [d for d in ctx.drafts if not d.frozen and not d.is_backlog]
    if len(open_drafts) > 1:
        issues.error("drafts", 0, "only one draft can exist at a time (the next push); move the others' ideas "
                                  "to the backlog and retire them: " + ", ".join(d.rel for d in open_drafts))
    titles = {}
    for d in ctx.drafts:
        s = d.status.lower()
        if not d.status:
            issues.error(d.rel, 0, 'no "**Status:**" line')
        elif d.is_backlog and s != "backlog":
            issues.error(d.rel, 0, 'the backlog\'s status is "Backlog"')
        elif not d.is_backlog and not (s == "active" or d.frozen):
            issues.error(d.rel, 0, 'status must be Active, "Pushed as vX on <date>" or "Retired on <date>"')
        if d.frozen:
            continue
        if not d.has_entries:
            issues.error(d.rel, 0, 'no "## Entries" section')
        for b in d.stray_levels:
            issues.warn(d.rel, b.line(), f'"{b.text}": entries are level-3 headings (###)')
        for e in d.entries:
            if e.type != "amendment":
                titles.setdefault(e.ntitle, []).append((d, e))
        text, html, missing = draft_outputs(d, main)
        for name in missing:
            issues.error(d.rel, 0, f"missing <!-- BEGIN/END GENERATED: {name} --> markers (see templates/draft.md)")
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
    # versions, log and frozen files
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
        differs = [doc for doc in MAIN_DOCS if (latest / doc).exists() and (ROOT / doc).exists()
                   and norm_text(TextFile(latest / doc).text) != norm_text(TextFile(ROOT / doc).text)]
        if differs:
            issues.warn("main documents", 0, f"{', '.join(differs)} differ from the latest version ({latest.name}); "
                                             "that is only expected in the middle of a push")
    ever = {}
    for f in folders:
        if f.name in rev:
            continue
        for iid in Main(f, Issues()).items:
            ever.setdefault(iid, f.name)
    for iid, v in sorted(ever.items()):
        if iid not in main.items:
            issues.warn("main documents", 0, f"{iid} was in {v} but is gone now; retire items instead of deleting "
                                             "them (only a rollback removes IDs)")
    if in_git():
        for f in folders:
            if tag_exists(f.name):
                if changed_since(f.name, f):
                    issues.error(rel(f), 0, f"a saved version was changed after tag {f.name}")
            elif f.name not in rev:
                issues.warn(rel(f), 0, f"no git tag {f.name} yet; commit, tag {f.name} and push")
        for d in ctx.drafts:
            if d.frozen and d.pushed_as and tag_exists(d.pushed_as) and changed_since(d.pushed_as, d.path.parent):
                issues.error(d.rel, 0, f"a pushed draft was changed after tag {d.pushed_as}")
    else:
        issues.warn("git", 0, "not a git repository; frozen-file checks were skipped")
    # prototype
    if PROTOTYPE.exists():
        if not CHAIN_JS.exists() or norm_text(TextFile(CHAIN_JS).text) != chain_js(main):
            issues.error(rel(CHAIN_JS), 0, "out of date; run build")
        for f in sorted(PROTOTYPE.rglob("*")):
            if f.suffix.lower() not in (".html", ".htm", ".js") or f.name in ("chain.js", "trace.js"):
                continue
            for n, ln in enumerate(TextFile(f).text.split("\n"), 1):
                found = [m.group(1) for m in TRACE_ATTR.finditer(ln)] + [m.group(1) for m in TRACE_JS.finditer(ln)]
                for chunk in found:
                    for m in ID_RE.finditer(chunk):
                        iid = f"{m.group(1)}-{m.group(2)}"
                        it = main.items.get(iid)
                        if not it:
                            issues.error(rel(f), n, f"marker uses {iid}, which is not pushed")
                        elif it.retired:
                            issues.error(rel(f), n, f"marker uses {iid}, which is retired")
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
    active = [d.rel for d in ctx.drafts if d.active]
    print("Main documents: " + ", ".join(parts))
    print(f"Latest version: {latest.name if latest else 'none yet'}  \u00b7  "
          f"Active draft: {active[0] if active else 'none'}")


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
        if writer.write(ROOT / doc, text):
            changed_main = True
    if changed_main:  # continue from the regenerated text (also correct in a dry run)
        ctx = Context(main_texts=fresh)
    for d in ctx.drafts:
        if d.frozen:
            continue
        text, html, missing = draft_outputs(d, ctx.main)
        for name in missing:
            print(f"  WARN  {d.rel} \u2014 no <!-- BEGIN/END GENERATED: {name} --> markers; that part was skipped")
        writer.write(d.path, text)
        writer.write(d.map_path, html)
    if PROTOTYPE.exists():
        writer.write(CHAIN_JS, chain_js(ctx.main))
    return ctx


def cmd_build(args):
    ctx = Context()
    writer = Writer(dry=args.dry_run, frozen=ctx.frozen_paths())
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


# --------------------------------------------------------------------------- IDs, drafts, pushes

def all_ids():
    ids = set(Main(ROOT, Issues()).items)
    for f in version_folders():
        ids |= set(Main(f, Issues()).items)
    return ids


def next_ids():
    top = {"O": 0, "P": 0, "S": 0, "F": 0}
    for iid in all_ids():
        top[iid[0]] = max(top[iid[0]], int(iid[2:]))
    return {k: f"{k}-{v + 1:03d}" for k, v in top.items()}


def cmd_next_ids(args):
    n = next_ids()
    print("Next free IDs (one above the highest ever used, including saved versions):")
    print(f"  Objective             {n['O']}")
    print(f"  Problem               {n['P']}")
    print(f"  Solution/Sub-solution {n['S']}")
    print(f"  Feature               {n['F']}")
    return 0


def cmd_new_draft(args):
    v = args.version
    if not VERSION_RE.match(v):
        raise SystemExit("Version looks like v0.2 or v0.1.1")
    folder = DRAFTS / v
    if folder.exists():
        raise SystemExit(f"{rel(folder)} already exists")
    if (VERSIONS / v).exists():
        raise SystemExit(f"{v} was already pushed; pick a new number")
    latest = latest_version(exclude_reversed=False)
    if latest and version_key(v) <= version_key(latest.name):
        raise SystemExit(f"Version numbers only go up: the latest is {latest.name}")
    ctx = Context()
    open_drafts = [d.rel for d in ctx.drafts if not d.frozen and not d.is_backlog]
    if open_drafts:
        raise SystemExit(f"Only one draft at a time: push {open_drafts[0]} first (or retire it and move its ideas to the backlog).")
    text = TextFile(TEMPLATE_DRAFT).text.replace("vX", v)
    text = re.sub(r"^\*\*Status:\*\*.*$", "**Status:** Active", text, count=1, flags=re.M)
    writer = Writer(frozen=ctx.frozen_paths())
    writer.write(folder / f"draft-{v}.md", text)
    build(Context(), writer)
    print("Created: " + ", ".join(writer.changed))
    return 0


def cmd_record_push(args):
    v = args.version
    if not VERSION_RE.match(v):
        raise SystemExit("Version looks like v0.2 or v0.1.1")
    target = VERSIONS / v
    if target.exists():
        raise SystemExit(f"{rel(target)} already exists; versions are never overwritten")
    latest_any = latest_version(exclude_reversed=False)
    if latest_any and version_key(v) <= version_key(latest_any.name):
        raise SystemExit(f"Version numbers only go up and are never reused: the latest is {latest_any.name}")
    ctx = Context()
    path = draft_arg(args.draft) if args.draft else next((d.path for d in ctx.drafts if d.active), None)
    if not path:
        raise SystemExit("No Active draft; name one with --draft")
    draft = next((d for d in ctx.drafts if d.path.resolve() == Path(path).resolve()), None)
    if not draft or draft.frozen or draft.is_backlog:
        raise SystemExit(f"{args.draft or path} is not a draft that can be pushed")
    ctx = Context(strict=draft.path)
    issues = run_checks(ctx)
    if any(i[0] == "error" for i in issues.items):
        print_issues(issues)
        raise SystemExit("\nNot recorded: fix the errors above first.")
    prev_folder = latest_version()
    prev = Main(prev_folder, Issues()) if prev_folder else None
    writer = Writer(frozen=ctx.frozen_paths())
    # 1. freeze the draft as it was proposed: built against the version before this push
    before = prev if prev is not None else Main(ROOT, Issues(), texts={d: "" for d in MAIN_DOCS})
    d = Draft(draft.path)
    resolve_draft(d, before, Issues(), set(), strict=False)
    text, html, _ = draft_outputs(d, before)
    today = datetime.date.today().isoformat()
    text = re.sub(r"^\*\*Status:\*\*.*$", f"**Status:** Pushed as {v} on {today}", text, count=1, flags=re.M)
    writer.write(d.path, text)
    writer.write(d.map_path, html)
    # 2. save the version
    for doc in MAIN_DOCS:
        writer.write(target / doc, ctx.main.files[doc].text, allow_frozen=True)
    writer.write(target / "mindmap.html", render_map(version_graph(v, ctx.main, prev)), allow_frozen=True)
    # 3. log entry
    added, amended, retired = [], [], []
    for it in ctx.main.ordered():
        old = prev.items.get(it.id) if prev else None
        if it.retired and old and not old.retired:
            retired.append(it)
        elif not old:
            added.append(it)
        elif ctx.main.entry_text(it, drop_served_by=True) != prev.entry_text(old, drop_served_by=True):
            amended.append(it)

    def names(xs):
        return "; ".join(f"{x.id} {x.title}" for x in xs) or "none"
    entry = [f"## {v} ({today})", f"- Draft: {rel(d.path)}", f"- Added: {names(added)}",
             f"- Amended: {names(amended)}", f"- Retired: {names(retired)}", "- Rollback: none"]
    base = TextFile(LOG).text if LOG.exists() else "# Version log\n"
    log_text = base.rstrip("\n") + "\n\n" + "\n".join(entry) + "\n"
    writer.write(LOG, log_text)
    print("Recorded " + v + ": " + ", ".join(writer.changed))
    print(f"\nNext: commit everything, tag the commit {v}, and push the commit and the tag.")
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
    n = sub.add_parser("new-draft", help="create drafts/VERSION/ (only when no other draft is open)")
    n.add_argument("version")
    r = sub.add_parser("record-push", help="save versions/VERSION/, add the log entry, freeze the draft")
    r.add_argument("version")
    r.add_argument("--draft", metavar="DRAFT", help="the draft being pushed (default: the open draft)")
    args = p.parse_args(argv)
    return {"check": cmd_check, "build": cmd_build, "next-ids": cmd_next_ids,
            "new-draft": cmd_new_draft, "record-push": cmd_record_push}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
