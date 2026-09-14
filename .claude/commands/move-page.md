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
- Repoints any glossary term whose `full_link` front matter pointed at the moved page, keeping the `#fragment` if there was one

`full_link` needs its own pass because it holds a URL rather than a content path, so the `xref`/`relref` rewriting cannot see it, and Hugo's link render hook never reads front matter. Left alone, a move silently sends every tooltip for that term to a 404.

Projects with no glossary have no `full_link` keys and the pass does nothing — there is no flag to set either way. The script does not care where the glossary directory is, which matters because that path is configurable.

The script lists any term it repointed:

```
✅ Move complete: content/architecture → content/platform/architecture
   Repointed full_link in 2 glossary term(s):
     content/reference/glossary/axorouter.md
     content/reference/glossary/axoconsole.md
```

A `full_link` with a `#fragment` keeps the fragment, which is worth a look: the heading it names has to still exist on the moved page, and nothing checks that at move time. The build does check it afterwards, at the `errorLevel` the site sets in `params.render_hooks.link`.

After the move, verify the build:
```
hugo --minify
```

Report any build errors before considering the move complete.
