# docsy-axoflow — Shared Claude Configuration

This submodule is shared across Axoflow documentation projects built with Hugo and the Docsy theme. It provides the theme, shared scripts, and shared Claude agent configuration.

## Available scripts

### move_hugo_files.py

Moves Hugo content pages while preserving git history, adding URL aliases, and rewriting cross-references. Always use `/move-page` (or run directly) instead of `git mv`.

```bash
python3 themes/docsy-axoflow/scripts/move_hugo_files.py <source> <destination>
```

Both paths are relative to the project root. The script:
- Uses `git mv` to preserve history
- Adds the old URL to `aliases` in front matter (enables redirects)
- Rewrites all `xref`, `relref`, and `ref:` links across `content/`

### hugo_to_markdown.py

Converts the built Hugo site to Markdown for LLM consumption. Run after a full build:

```bash
python3 themes/docsy-axoflow/scripts/hugo_to_markdown.py --input public --output public
```

## Shared Claude config

The `.claude/` directory here contains commands and reference docs shared across all projects using this submodule. Each project symlinks these into its own `.claude/` directory alongside project-specific files (style guide, etc.).

### Commands

- `.claude/commands/move-page.md` — workflow for moving/renaming pages
- `.claude/commands/review-page.md` — page review against the style guide
- `.claude/commands/new-page.md` — new page creation workflow

### Reference docs

- `.claude/docs/shortcodes.md` — available Hugo/Docsy shortcodes
- `.claude/docs/frontmatter.md` — front matter fields and rules
- `.claude/docs/new-section.md` — adding pages and sections
