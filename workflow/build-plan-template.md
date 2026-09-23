# Build plan for {version}

How {version}'s features get built in {where}. Started by `python workflow/tool.py new-plan` with one task per feature this version added or amended, in the order their Needs require. The writing-plans skill fills in the steps; subagent-driven-development or executing-plans works through them. Tick each step when it is done; `status` shows the progress.

Rules for every task:

- Build only what the task's feature says. Its "Done when" is the finish line.
- Prototype: add the "!" marker (`data-trace="F-…"`) to the feature's element. Product: name the feature ID in the code and in its test, and write the test first.
- Screens follow DESIGN.md (the impeccable skill). Respect plan/constraints.md.
- Run `python workflow/tool.py check` after each task, then commit.
- Something that needs a new or changed item goes to the backlog, not into this plan.

---

{tasks}
