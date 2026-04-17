Move a documentation page or directory to a new location.

Ask me for:
1. The source path (relative from repo root, e.g. `content/docs/old-section/page.md` or `content/docs/old-section/`)
2. The destination path (relative from repo root)

Then run:
```
python3 themes/docsy-axoflow/scripts/move_hugo_files.py <source> <destination>
```

The script does all of the following automatically — do NOT do these manually:
- `git mv` to move the file(s) and preserve git history
- Adds the old URL to `aliases` in the moved file's front matter so the old URL still redirects
- Rewrites all `xref`, `relref`, and `ref:` links across the entire `content/` tree to point to the new location

After the move, verify the build:
```
hugo --minify
```

Report any build errors before considering the move complete.
