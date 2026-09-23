# General Workflow for Projects

A simple, traceable way to run any project with Claude Code: from objectives, to the problems in the way, to the solutions and the features that get built. Ideas are drafted first, pushed in small approved versions, shown on visual maps, and tried out in a prototype that improves version by version. When the prototype is right, the real product is built.

```
Objective > Problem > Solution > Sub-solution (optional) > Feature
```

## Folders

```
CLAUDE.md     how we work (the rules Claude follows)
README.md     what this project is
plan/         WHAT and WHY: objectives, problems, solutions, constraints, what the prototype must prove, the map
drafts/       NEXT: the backlog of ideas and the one open draft
versions/     HISTORY: one frozen folder per version, abandoned drafts, and the log
prototype/    NOW: the live prototype, improved version by version, and its review
product/      LATER: the real platform from v1.0: its design, code, tests, and review
workflow/     the machinery: the tool, its tests, the templates, the changelog
```

Work moves through them in one direction:

```
idea → drafts/backlog.md (Now / Next / Later) → drafts/draft-vX.md → push → plan/ + versions/vX/
     → build prototype/ → review → save it in versions/vX/prototype/ → findings to the backlog → next draft …
     → status shows no gaps → v1.0 → design, build and test product/ → review → release → next version …
     → every objective done → closing version
```

Each `versions/vX/` folder holds everything about that version: the plan as pushed, its map, the draft that proposed it, and the prototype built for it. To see how the prototype improved, open two versions' prototypes side by side.

## Start a new project

1. On GitHub, click "Use this template" to create your project's repository (or clone this one, delete its `.git` folder, and run `git init`).
2. Open the folder in Claude Code. It reads `CLAUDE.md`, which holds all the rules.
3. Talk about the project. Claude captures ideas in the backlog and sorts them into objectives, problems, solutions, and features.
4. Pick a small first slice into the draft (`drafts/draft-v0.1.md`) and give the green light to push it.
5. Build the prototype from the pushed features, review it with the team, save it, and repeat with the next small slice.
6. When `status` shows the prototype covers everything, push v1.0 and build the real product in `product/`.

You need Python 3.8 or newer (standard library only) and git.

## The tool

`workflow/tool.py` does the bookkeeping, so nothing is copied or linked by hand.

```
python workflow/tool.py status               # what is covered, built, accepted, open, and missing
python workflow/tool.py check                # report problems; changes nothing
python workflow/tool.py build                # regenerate back-links, maps, overviews, prototype trace data
python workflow/tool.py new-draft v0.2       # start the next draft (when no draft is open)
python workflow/tool.py apply-draft          # write the approved draft into plan/ with new IDs
python workflow/tool.py record-push v0.2 --approved-by NAME   # save the version, log it, move the draft into it
python workflow/tool.py save-prototype v0.2  # save the reviewed prototype into that version
python workflow/tool.py record-release v1.0 --approved-by NAME   # from v1.0: release the reviewed product
python workflow/tool.py abandon-draft        # give up the open draft; its entries go back to the backlog
python workflow/tool.py next-ids             # next free ID of each kind
python workflow/tool.py new-plan             # start the build plan for the latest version
python workflow/test_tool.py                 # test the workflow itself (after changing workflow/)
```

`check --push v0.2` also requires every entry of that draft to be complete. `build --dry-run` shows what would change.

## Maps

The plan, the backlog, the draft, and every version have a mind map, generated from the text. Serve the folder (`python -m http.server 8777`, or the `maps` config in `.claude/launch.json`) and open a map in the browser. Hover to trace an item's chain, click to pin, Esc to clear. Features already built show a ✓. Once anything is pushed, items not pushed yet show as NEW, changes as AMENDED, retirements as CUT, and new links are highlighted.

- **Which map:** today's plan is `plan/map.html`; the next change is the draft's map (`drafts/draft-vX-map.html`); a past version is `versions/vX/mindmap.html`.
- **Whole plan in every draft map:** the draft and backlog maps show everything already pushed, plain, with the draft's own changes marked on top. "Show only changes" hides the rest; click again for the whole plan.
- **Version chips and history:** each pushed item shows the version it was first pushed in (e.g. `v0.1`). Click it for its history: pushed, amended, built, accepted, released.

## Recommended skills

Optional. The workflow runs without them, and CLAUDE.md says where each one's output goes.

- **[Superpowers](https://github.com/obra/superpowers)**: brainstorming (shaping a draft), writing-plans (the build plan), subagent-driven-development or executing-plans (building it), test-driven-development, systematic-debugging, verification-before-completion.
- **[impeccable](https://github.com/pbakaus/impeccable)**: design. `init` writes PRODUCT.md and DESIGN.md; `craft`, `polish`, `audit`, and the rest improve the screens.

## Changes

See [workflow/CHANGELOG.md](workflow/CHANGELOG.md).
