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

### check_main_menu.py / check_footer.py / check_banner.py / check_chrome_css.py

Four scripts that diff the site's marketing chrome against axoflow.com. The first three can merge the live version back into the data file it renders from; the fourth compares live's own design against a recorded baseline. They share `scripts/axoflow_site.py` (fetch with retry, comparison keys, raw-markup slicing, comment-preserving writes) — a module, not a script; run the four by path and the import resolves.

| Script | Data file | Live |
|--------|-----------|------|
| `check_main_menu.py` | `data/nav-menu.yaml` — `items`, `mobile.items` | `.v3-navbar_desktop-contents`, `.v3-navbar_mobile-contents` |
| `check_footer.py` | `data/footer.yaml` — columns, tagline, copyright, privacy, badges, social | `footer.v3-footer_component` |
| `check_banner.py` | `data/chrome.yaml` — `announcement` | `.v2-banner_component` |
| `check_chrome_css.py` | `baselines/chrome-css.json` | the CSS rules for the chrome's own classes |

The content checkers compare wording and layout, not just links: group headings and blurbs, the per-link one-liners, the icons (by their path data), and the `column` / `sub` keys that carry live's mega-panel layout. A rewritten blurb or a group that moved column is drift even when every URL matches.

`check_chrome_css.py` answers a different question — has marketing *redrawn* the chrome — by keeping every rule whose selector mentions a chrome class, normalizing it, and diffing against `baselines/chrome-css.json` (kept out of `data/` so Hugo does not load 27KB of somebody else's stylesheet into `site.Data`). It deliberately does not compare live's CSS with ours: the two share no class names, and visual parity is a question about rendered geometry that needs a browser and a judgement call.

```bash
python3 themes/docsy-axoflow/scripts/check_footer.py               # drift report
python3 themes/docsy-axoflow/scripts/check_footer.py --format yaml # the scraped chrome
python3 themes/docsy-axoflow/scripts/check_footer.py --write       # merge into the data file
```

All three exit 1 on drift, so any of them can gate CI. The menu and footer `--write` additively: rows the data file has and live does not are carried over, and the comment blocks are preserved. Comments inside a list are not — read the diff. `check_banner.py --write` edits only the two lines it owns, so anything else `chrome.yaml` grows is safe, and it rewrites nothing when the banner already matches.

The banner is the one piece of chrome meant to change often, and it also goes away — marketing takes the strip down between events. `announcement.label` empty is how that is recorded (the partial then renders nothing), the stored `href` is kept as the record of where the last one pointed, and a down strip is not counted as drift.

What the footer script deliberately does not copy from live, because the data file's values are this site's own: the vendored `logo.*` / `badges[].file` paths (it checks the artwork behind them instead and says when it needs re-vendoring), the social labels (which are the glyph keys in `footer/row-3.html`), the column title casing, and the `Capablities` typo, which it corrects on the way in and reports.

### hugo_to_markdown.py

Converts the built Hugo site to Markdown for LLM consumption. Run after a full build:

```bash
python3 themes/docsy-axoflow/scripts/hugo_to_markdown.py --input public --output public
```

## Shared Claude config

The `.claude/` directory here contains commands and reference docs shared across all projects using this submodule. Each project symlinks these into its own `.claude/` directory alongside project-specific files (style guide, etc.).

### Skills

- `.claude/skills/chrome-parity/` — review whether the chrome still *looks* like axoflow.com's, and decide what to change when it does not. The visual half the four checkers deliberately do not cover: it carries `measure.js`, a console snippet that measures rendered geometry and type on either site, plus the tolerances for judging the diff. Needs a browser the user drives — Chrome cannot start under Claude Code's sandbox.

### Commands

- `.claude/commands/sync-chrome.md` — run the four chrome checkers and update the data files that drifted
- `.claude/commands/move-page.md` — workflow for moving/renaming pages
- `.claude/commands/review-page.md` — page review against the style guide
- `.claude/commands/new-page.md` — new page creation workflow

### Reference docs

- `.claude/docs/shortcodes.md` — available Hugo/Docsy shortcodes
- `.claude/docs/frontmatter.md` — front matter fields and rules
- `.claude/docs/new-section.md` — adding pages and sections
