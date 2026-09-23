# Version log

One entry per push, oldest first, written by `python workflow/tool.py record-push`. Each `versions/vX/` folder holds that version: the plan as pushed, its map, the draft that proposed it, and the prototype built for it.

Never edit or delete an entry. The only lines that change afterwards: `save-prototype` fills in the Prototype line, and a reversed version gets its Rollback line filled in.

**Entry format**

```
## v0.1 (YYYY-MM-DD)
- Draft: versions/v0.1/draft-v0.1.md
- Note: (optional) what this version is about
- Added: IDs and titles
- Amended: IDs and titles
- Retired: IDs and titles
- Prototype: not saved yet | saved on YYYY-MM-DD
- Rollback: none | reversed on YYYY-MM-DD, restored from v0.x
```

---
