# Product

The real platform or project goes here. It starts at v1.0: the version where the user confirms the prototype covers the full scope and approves building the real thing. Until then this folder stays empty.

At v1.0, `record-push` adds two files here:
- `design.md`: how the product is built (stack, architecture, data, integrations, environments, tests). Fill it in before building; it changes only with the user's approval.
- `REVIEW.md`: the review of each version before it is released.

Rules:
- Build only pushed features (an ID in plan/solutions.md and a complete chain up to an objective), after reading plan/constraints.md.
- Each piece of code and each test names the feature ID it builds (for example in a comment, `F-012`). `check` reports IDs here that don't exist or are retired, and `status` counts a feature as built once its ID appears here.
- Every feature gets at least one test, named with its ID and based on its "Done when".
- Release a version with `python workflow/tool.py record-release vX --approved-by NAME` after its review, then tag the commit `vX-release`.
