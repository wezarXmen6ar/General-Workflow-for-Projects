# General Workflow for Projects

A simple, traceable way to run any project with Claude Code: from objectives, to the problems in the way, to the solutions and the features that get built. Everything is drafted first, pushed in small approved versions, shown on visual maps, and tried out in a prototype before the real product is built.

```
Objective > Problem > Solution > Sub-solution (optional) > Feature
```

## Start a new project

1. Create a repository from this one (GitHub's "Use this template", or clone it, delete `.git`, and run `git init`).
2. Open the folder in Claude Code. It reads `CLAUDE.md`, which holds all the rules.
3. Talk about the project. Claude captures ideas in the backlog and sorts them into objectives, problems, solutions, and features.
4. Pick a small first slice into the active draft (`drafts/v0.1/`) and give the green light to push it.
5. Build the prototype from the pushed features, then repeat with the next small slice.

You need Python 3.8 or newer (standard library only) and git.

## How it works

| Step | What happens |
|---|---|
| Capture | New ideas go into the backlog's Inbox, one line each. |
| Draft | A small slice moves from the backlog into a draft. Before a push, every entry needs its full chain up to an objective. |
| Push | On your green light, entries get permanent IDs in the main documents. The version is saved, logged, tagged, and pushed. |
| Build | Only pushed features are built into the prototype. Each carries a "!" marker showing its chain up to the objectives. |

- **Main documents:** `objectives.md`, `problems.md`, `solutions.md`, which change only through a push.
- **Drafts:** `drafts/backlog/` for every idea not yet in a draft; `drafts/vX/` for each push.
- **Versions:** `versions/vX/` (frozen snapshots) and `versions/log.md`.
- **Prototype:** `prototype.md` (what it must show) and `prototype/`.

## The tool

`tools/workflow.py` does the bookkeeping, so nothing is copied or linked by hand.

```
python tools/workflow.py check          # report problems; changes nothing
python tools/workflow.py build          # regenerate back-links, overviews, maps, prototype chain
python tools/workflow.py next-ids       # next free ID of each kind
python tools/workflow.py new-draft v0.2 # start a new draft
python tools/workflow.py record-push v0.2   # save the version, log it, freeze the draft
```

`check --push v0.2` also requires every entry of that draft to be complete. `build --dry-run` shows what would change.

## Maps

Every draft, the backlog, and every version has a mind map, generated from the text. Serve the folder (`python -m http.server 8777`, or the `maps` config in `.claude/launch.json`) and open a map in the browser. Hover to trace an item's chain, click to pin, Esc to clear. Items not pushed yet show as NEW, changes as AMENDED, retirements as CUT, and new links are highlighted.

## Changes

See [CHANGELOG.md](CHANGELOG.md).
