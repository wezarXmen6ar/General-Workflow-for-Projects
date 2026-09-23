# General Workflow for Projects

A simple, traceable way to run any project with Claude Code: from objectives, to the problems in the way, to the solutions and the features that get built. Ideas are drafted first, pushed in small approved versions, shown on visual maps, and tried out in a prototype that improves version by version. When the prototype is right, the real product is built.

```
Objective > Problem > Solution > Sub-solution (optional) > Feature
```

## Folders

```
CLAUDE.md     how we work (the rules Claude follows)
README.md     what this project is
plan/         WHAT and WHY: objectives, problems, solutions, what the prototype must prove, the map
drafts/       NEXT: the backlog of ideas and the one open draft
versions/     HISTORY: one frozen folder per version, abandoned drafts, and the log
prototype/    NOW: the live prototype, improved version by version
product/      LATER: the real platform, started at v1.0
workflow/     the machinery: the tool, the templates, the changelog
```

Work moves through them in one direction:

```
idea → drafts/backlog.md → drafts/draft-vX.md → push → plan/ + versions/vX/
     → build prototype/ → save it in versions/vX/prototype/ → review → next draft …
     → prototype approved → v1.0 → build product/
```

Each `versions/vX/` folder holds everything about that version: the plan as pushed, its map, the draft that proposed it, and the prototype built for it. To see how the prototype improved, open two versions' prototypes side by side.

## Start a new project

1. Clone this repository, delete its `.git` folder, and run `git init`. (GitHub's "Use this template" button also works once the repository is marked as a template in its settings.)
2. Open the folder in Claude Code. It reads `CLAUDE.md`, which holds all the rules.
3. Talk about the project. Claude captures ideas in the backlog and sorts them into objectives, problems, solutions, and features.
4. Pick a small first slice into the draft (`drafts/draft-v0.1.md`) and give the green light to push it.
5. Build the prototype from the pushed features, save it, and repeat with the next small slice.

You need Python 3.8 or newer (standard library only) and git.

## The tool

`workflow/tool.py` does the bookkeeping, so nothing is copied or linked by hand.

```
python workflow/tool.py check                # report problems; changes nothing
python workflow/tool.py build                # regenerate back-links, maps, overviews, prototype trace data
python workflow/tool.py next-ids             # next free ID of each kind
python workflow/tool.py new-draft v0.2       # start the next draft (when no draft is open)
python workflow/tool.py record-push v0.2     # save the version, log it, move the draft into it
python workflow/tool.py save-prototype v0.2  # save the live prototype into that version
python workflow/tool.py abandon-draft        # give up the open draft; its entries go back to the backlog
```

`check --push v0.2` also requires every entry of that draft to be complete. `build --dry-run` shows what would change.

## Maps

The plan, the backlog, the draft, and every version have a mind map, generated from the text. Serve the folder (`python -m http.server 8777`, or the `maps` config in `.claude/launch.json`) and open a map in the browser. Hover to trace an item's chain, click to pin, Esc to clear. Once anything is pushed, items not pushed yet show as NEW, changes as AMENDED, retirements as CUT, and new links are highlighted.

## Changes

See [workflow/CHANGELOG.md](workflow/CHANGELOG.md).
