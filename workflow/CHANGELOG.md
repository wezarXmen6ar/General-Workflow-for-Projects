# Changelog

Changes to the workflow itself (CLAUDE.md, templates, and tools). Each entry is the approved table of affected rules: kept, changed, removed, or fixed, and why.

## Workflow 1.4.2 (2026-09-23)

| Rule | Status | Now |
|---|---|---|
| Tests for the workflow | Fixed | workflow/test_tool.py builds its own blank project from the workflow's files, so it runs inside any project, not only an empty one. |

## Workflow 1.4.1 (2026-09-23)

Fixes found by testing the upgrade on a real project.

| Rule | Status | Now |
|---|---|---|
| An amendment changes the plan | Fixed | An amendment whose change sits only in its Description (the reason) used to change nothing without saying so. `check` now reports it, and `check --push` blocks it: the new wording goes in "New text:". |
| Open questions in amendments | Fixed | "Open questions: none" is no longer copied into the plan. |
| `apply-draft` report | Fixed | "Amended" lists only items whose text really changed. |

## Workflow 1.4 (2026-09-23)

A full cycle: from the first idea to released versions of the real product and the project's close.

| # | Rule | Status | Now |
|---|---|---|---|
| 1 | Technical design | New | At v1.0, `record-push` adds product/design.md (stack, architecture, data, integrations, environments, tests), filled in before building and changed only with the user's approval. |
| 2 | Product traceability | Changed | Code and tests in product/ name the feature ID they build; `check` reports IDs there that don't exist or are retired. |
| 3 | Testing | New | Every product feature gets at least one test, named with its ID and based on its "Done when". |
| 4 | Releases | New | `record-release vX --approved-by NAME` fills the log's Released line; the commit is tagged `vX-release`. |
| 5 | Status report | New | `status` lists what is covered, built, accepted, and missing, open questions and bugs, backlog priorities, and v1.0 readiness. |
| 6 | The v1.0 decision | Changed | `record-push v1.0` refuses while the prototype has gaps, unless the user accepts them in writing (`--accept-gaps`, recorded in the log). |
| 7 | Done when | New | Every feature has a "Done when" line; `check --push` requires it. |
| 8 | Review | New | prototype/REVIEW.md (from v1.0, product/REVIEW.md): who reviewed, what was accepted, findings. Required by `save-prototype` and `record-release`, and frozen with the version. Findings go to the backlog. |
| 9 | Bugs | New | The backlog's Bugs section, one ticked line per defect; fixes need no push and move into the version's log entry when saved or released. |
| 10 | Open questions | Changed | They stay with the item in the plan at a push; an answer comes back as an Amendment. |
| 11 | Priority | New | Backlog entries are Now, Next, or Later; the next draft is filled from Now, whole chains first. |
| 12 | Approval record | Changed | `record-push` and `record-release` require `--approved-by`; the log records who and when. |
| 13 | Constraints | New | plan/constraints.md, changed only with the user's approval and saved with every version. |
| 14 | Dependencies | New | A feature's "Needs" lists features to build first; `status` shows features waiting for them. |
| 15 | One session at a time | New | Start with `git pull` and `check`; end with commit and push. |
| 16 | Tests for the workflow | New | workflow/test_tool.py runs the whole cycle in a temporary copy; run it after any change in workflow/. |
| 17 | Closing the project | New | When every objective is Done or Retired, a final version with a closing note. |
| 18 | Changelog order | Fixed | Newest first (1.3 was below 1.2). |
| 19 | Built features on the map | Changed | The map design gains a ✓ on features built in the prototype or the product (plan, draft and backlog maps). |
| 20 | Push step 2 | Changed | `apply-draft` writes the approved draft into plan/ with new IDs, under each home parent, and applies every amendment; entries not approved (`--skip`) go back to the backlog. |
| — | Amendments | Changed | They name only the fields that change: New text, Serves, Also serves, Remove links, Needs, Done when, Design location, Label, Open questions, Status (Solved or Done), Retire. |

## Workflow 1.3 (2026-09-23)

A folder structure that follows the work: plan, drafts, versions, prototype, product.

| Rule | Status | Now |
|---|---|---|
| Main documents and prototype.md at the top level | Changed | In plan/, with plan/map.html showing everything pushed. The top level keeps only CLAUDE.md and README.md. |
| Pushed and abandoned drafts kept in drafts/ as frozen records (1.2) | Changed | drafts/ holds only backlog.md and the one open draft. At a push the draft moves into versions/vX/; an abandoned draft moves into versions/abandoned/ with the new `abandon-draft` command. Both stay frozen there, and abandoned numbers are still never reused. |
| A version folder holds the three documents and the map | Changed | versions/vX/ holds everything about the version: the plan as pushed (with prototype.md), its map, the draft that proposed it, and the prototype built for it. |
| The prototype is one live folder | Changed | Still one live prototype/, and `save-prototype vX` keeps a frozen copy of each version's prototype, so versions can be compared. The log's Prototype line records it. |
| The real product | New | product/ starts at v1.0. Each piece of product code names the feature ID it builds. |
| Tool and templates in tools/ and templates/ | Changed | Together in workflow/ (tool.py, map-template.html, draft-template.md, CHANGELOG.md). |
| The prototype's "!" marker files | Changed | In prototype/trace/. |
| Moving to this workflow from an older one | New | Older dotted IDs (S-002.1) are read as they are, never renamed. Old back-link lines are ignored when versions are compared. Frozen files are checked from their last move, and history/ keeps old files, frozen. |
| `record-push` | Changed | Takes an optional `--note` for the log. |

## Workflow 1.2 (2026-09-23)

A consistency pass: places where the rules contradicted each other or the tool.

| Rule | Status | Now |
|---|---|---|
| Any pushed item can be retired | Fixed | The tool refused "Status: Retired" on objectives, which blocked the push. Objectives can now be retired like everything else. |
| Serving a retired item | Fixed | Flagged for "Also serves" too, not only for the home parent. |
| Drafts show the full text of every objective and problem | Fixed | Only current (not retired) ones, the same items their maps show, so text and map agree. The backlog shows them too. |
| Only the user marks Solved or Done | Changed | Done through an Amendment in the draft, because the main documents change only through a push. |
| One draft at a time | Changed | Worded as "one open draft at a time": pushed and retired drafts stay in drafts/ as frozen records. |
| An abandoned draft | Changed | Its version number is not reused (the tool already refused it; now the rules and the tool's message say so). |
| NEW, AMENDED and CUT marks | Changed | They start once anything is pushed; before that everything is new, and the first version's map has nothing marked. |
| Drafts have no IDs | Changed | New entries have no ID; drafts refer to pushed items by ID. The main documents use IDs only. |
| An objective is done when its problems are solved | Changed | Retired problems don't count (the tool already worked this way). |
| Retired and rolled-back features | New | They are taken out of the prototype (`check` already reported them). |
| Amendments | Changed | The template says what an amendment can carry: new text, a link to remove, or a Solved or Done mark. |
| Starting a project from this repository | Changed | "Use this template" works only once the repository is marked as a template; cloning always works. |

## Workflow 1.1 (2026-09-23)

| Rule | Status | Now |
|---|---|---|
| Several drafts at once, only one Active | Changed | Only one draft exists at a time: the next push. Everything else waits in the backlog. `new-draft` refuses while a draft is open, and `check` reports an error if two exist. The "Pending" status is gone. |

## Workflow 1.0 (2026-09-23)

First generic release. Compared with the earlier version of this workflow, it cuts manual bookkeeping, keeps each fact in one place, and adds safety checks that run on their own.

### Hierarchy and IDs

| Rule | Status | Now |
|---|---|---|
| Objective > Problem > Solution > Sub-solution > Feature | Changed | Same order; sub-solutions are optional and only one level deep. |
| Every item has one home parent ("Serves") and may also serve others | Kept | Allowed parents are now spelled out per type. |
| Never duplicate an idea; link with "Also serves" instead | Kept | Overlaps are flagged for the user, never merged silently. |
| Sub-solution IDs include the parent's ID (S-001.1) | Changed | Flat, permanent IDs (S-004). An ID never changes when an item moves and is never reused. |
| Features live in solutions.md and record their design location | Kept | |
| An objective is done when all its problems are solved | Kept | Only the user marks a problem Solved or an objective Done. |
| Stability decreases top to bottom | Kept | |

### Drafts

| Rule | Status | Now |
|---|---|---|
| Everything goes into a draft first | Kept | Into the backlog or a draft. |
| Ask for the problem, objective, and home parent before adding anything | Changed | Capture fast in the backlog's Inbox; the full chain is required, and asked for, before a push. |
| One subfolder per version draft | Kept | Plus drafts/backlog/ for every idea not in a draft. |
| Drafts are never combined | Changed | Drafts never copy each other or pushed items; they refer to pushed items by ID. |
| Mirroring an update into a later draft, with a preview map | Removed | Nothing is copied between drafts, so nothing needs mirroring. |
| Keep every confirmed preview map in drafts/update-previews/ | Removed | Each draft map and version map shows its own changes; git keeps the history. |
| Overview tree and "also serves" table kept by hand | Changed | Generated by `tools/workflow.py build`. |
| Every draft includes the full text of every objective and problem | Kept | Copied in by the tool, never by hand. |
| A draft's text and map must never contradict each other | Kept | Maps are generated from the text; `check` confirms they match. |
| Changes to pushed items | Changed | An Amendment entry names the ID; "Retire: yes" retires an item, which is never deleted. |
| Entries not approved at a push go to the next draft | Changed | They go back to the backlog. |
| Cut ideas | Changed | They go back to the backlog, or to its Dropped section with the date and the reason. |
| Several drafts at once | Changed | Allowed; only one is Active. |

### The mind map

| Rule | Status | Now |
|---|---|---|
| "The mind map" is always the template; never another format | Kept | |
| The settled design: columns, fanned links, hover, pin, Esc, light and dark | Kept | |
| Copy the template and replace only DATA; never change the render code | Changed | The tool generates every map. The template gained built-in NEW, AMENDED, and CUT marks and parent-aligned layout. |
| Order nodes by hand so children sit near their parent | Changed | Automatic: children sit next to their home parent, and parents are centred on their children. |
| A new draft that follows another keeps its changes highlighted | Kept | Every draft map marks what the draft adds or changes against what is pushed. |
| On a push, copy the draft's map into the version | Changed | Each version gets a map of everything pushed so far, with that version's changes marked. The frozen draft keeps its own map. |
| Short labels of 2–4 words | Kept | Optional "Label:" field; otherwise the title is shortened. |

### Pushes and versions

| Rule | Status | Now |
|---|---|---|
| Never push without the user's green light | Kept | |
| Every push is a version with a snapshot and a log entry | Kept | `record-push` saves the snapshot and version map, writes the log entry, and freezes the draft. |
| Version numbers: 1.0 first, then 1.1, 1.2 | Changed | v0.1, v0.2 for new scope; v0.1.1 for fixes; v1.0 when the real product is approved. Numbers only go up. |
| Each push is a tagged git commit, pushed to origin | Kept | |
| Never edit a saved version or rewrite git history | Kept | `check` reports any saved version or pushed draft changed after its tag. |
| Rollback restores the previous version as a new commit | Kept | Reversed entries go back to the backlog; their IDs are never reused. |
| The main documents change only through a push | New | Explicit, and `check` warns when they differ from the latest version. |

### Safety

| Rule | Status | Now |
|---|---|---|
| Run `check` before and after every change | New | A change is kept only if it adds no new errors. |
| Keep each file's encoding and line endings | New | The tool preserves them; `.gitattributes` normalizes the repository. |
| Commit before any big change | New | A restore point. |
| Check what links to a file before moving it | New | Never move a file that a frozen file links to. |
| Rule changes need a kept/changed/removed table and approval | New | Recorded in this file; restructuring happens on a branch. |

### Prototype

| Rule | Status | Now |
|---|---|---|
| Prototype first; build the real product only after the user confirms | Kept | |
| Build only pushed features, in push order | Kept | `check` flags markers that use unknown or retired IDs. |
| Every feature has a "!" marker showing its chain | Kept | Chain data is generated (prototype/chain.js); prototype/trace.js and trace.css provide the marker. |
| prototype.md says what the prototype must show | Kept | A template to fill in. |
