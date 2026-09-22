# Version log

One entry per push, oldest first, written by `python tools/workflow.py record-push`. Each version's full copy of the three main documents and its map are in `versions/vX/`.

Never edit or delete an entry. The only exception: when a version is reversed, fill in its Rollback line.

**Entry format**

```
## v0.1 (YYYY-MM-DD)
- Draft: drafts/v0.1/draft-v0.1.md
- Added: IDs and titles
- Amended: IDs and titles
- Retired: IDs and titles
- Rollback: none | reversed on YYYY-MM-DD, restored from v0.x
```

---
