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

## Glossary

A filterable glossary page plus an inline tooltip shortcode, shared by every site using this theme. Descended from `kubernetes/website`'s glossary by way of `falcosecurity/falco-website`, and rewritten to carry **no JavaScript** — Docsy drops jQuery in 0.18, and all four behaviours the original needed a script for are things the platform now does on its own.

### What the theme provides

| File | Job |
|------|-----|
| `layouts/docs/glossary.html` | The page. Reached by `layout: glossary`. |
| `layouts/_partials/docs/glossary-path.html` | Returns `params.glossary.path`. One place, three readers. |
| `layouts/_partials/docs/glossary-terms.html` | Returns the term pages as a resource slice. |
| `layouts/_shortcodes/glossary_tooltip.html` | Inline term link with a hover definition. |
| `layouts/_shortcodes/glossary_definition.html` | Inlines a definition into another page. |
| `assets/scss/_glossary.scss` | Imported from `_styles_project.scss` here, so a site needs no stylesheet of its own. |
| `i18n/en.toml` | The six UI strings. |
| `config/_default/config.toml` | `params.glossary.path`, default `/reference/glossary`. |

A site supplies the content and the tags. Nothing in the theme touches the bundle until a page asks for a term, so a site with no glossary pays nothing and needs no opt-out.

### Setting one up

1. Create the leaf bundle. **`index.md`, not `_index.md`** — that is what keeps the terms off the sidebar and out of the URL space while still letting each one be a page with front matter.

   ```yaml
   # content/reference/glossary/index.md
   ---
   title: Glossary
   description: A standardized list of Axoflow terminology.
   layout: glossary
   body_class: glossary
   weight: 10
   ---
   ```

   Elsewhere than `content/reference/glossary/`? Set `params.glossary.path` in the site's config to match.

2. Write the tags, one file each, in the site's own `data/canonical-tags/`. They are per-site: the terms a product needs grouping by are not the terms another one does.

   ```yaml
   # data/canonical-tags/fundamental.yaml
   id: fundamental
   name: Fundamental
   description: Terms you meet in the first hour with the Axoflow Platform.
   ```

   `id` has to be a valid CSS identifier: it becomes both an element id and a class. `description` is the chip's `title` attribute. Adding a tag needs this file and nothing else — the layout generates the CSS rule that reveals it.

3. Write the terms, one file per term, beside `index.md`. **The filename is the lookup key, not the `id` field** — keep them equal or the shortcodes error.

   ```yaml
   ---
   title: AxoRouter
   id: axorouter
   full_link: /architecture/#router
   short_description: >
     The router and data curation engine of the Axoflow Platform.
   aka:
   - Router
   tags:
   - architecture
   - fundamental
   ---
   One or two sentences. Renders as the preview, and may itself use tooltips.

   <!--more-->
   The rest. Renders inside a <details> that the page only draws when this part
   is non-empty.
   ```

   | Field | Notes |
   |-------|-------|
   | `title` | Required. Sorts the list, and is the tooltip's default link text. |
   | `id` | Required. Must equal the filename stem. |
   | `short_description` | Required. The hover text. **Front matter, so no shortcodes** — write product names out literally. |
   | `full_link` | Optional. Where the tooltip links instead of the glossary entry. Use it wherever a real concept page exists. |
   | `aka` | Optional list. Renders as "Also known as". |
   | `tags` | Required. Must match ids in `data/canonical-tags/`. A term with no matching checked tag is invisible. |

4. Use it. `{{< glossary_tooltip term_id="axorouter" >}}`, or with `text="the router"` to inflect it. An unknown `term_id` **fails the build** rather than shipping a dead link.

   `{{< glossary_definition term_id="axorouter" length="short" >}}` inlines the definition into a concept page, so the two cannot drift. `length` is `short` (first paragraph) or `long`/`all`; `prepend="Here," ` splices your own opening onto the first sentence.

### How the filter works without a script

`_glossary.scss` hides **every** term, and the layout generates one rule per tag that reveals its own:

```css
#glossary:has(#glossary-filter-architecture:checked) .glossary-terms > li.tag-architecture { display: list-item; }
```

Showing beats hiding, so a term carrying three tags stays visible while any one of them is ticked and vanishes when the last is unticked — the OR semantics the Kubernetes original emulates in JavaScript with a `data-show-count` reference counter on every `<li>`. The weight works out because `:has()` takes the specificity of its most specific argument: the `#glossary-filter-*` inside it is an ID.

The other three behaviours:

- **Expand/collapse** is `<details>`, which also inherits the chevron treatment `_axo-content.scss` gives every hand-written `<details>` under `content/`.
- **Select all** is `<input type="reset">`: the defaults are all-checked, so reset *is* select-all. There is deliberately no "deselect all", which is the one thing that would need script.
- **Deep links** are `li:target`, which outranks the filter. That is the entire job that `?all=true` does on every Kubernetes tooltip link, and why ours carry no query string.

Tooltips themselves need no init either: Docsy's `base.js` initializes every `[data-bs-toggle="tooltip"]` on the page, in 0.15 through jQuery and in 0.18 through vanilla `bootstrap.Tooltip.getOrCreateInstance`. Same markup contract on both sides of the jQuery drop. The Bootstrap 4 spelling `data-toggle` is inert — that is what the Falco copy still ships.

### Traps

- **`layouts/docs/glossary.html` resolves through the page's type.** On both current sites everything resolves under `docs/`, which is why the file sits there beside `docs/baseof.html`. Confirm with `hugo --templateMetrics | grep docs/` before assuming it on a new site; if the type differs, the file moves to `layouts/<type>/glossary.html`.
- **`trim` takes the cutset last.** `{{ $s | trim " \n" }}` trims the *cutset* using the string and returns garbage; it shipped every tooltip empty until it was caught. Write `{{ trim $s " \n" }}`.
- **`.glossary-tooltip` needs the long selector.** `_axo-content.scss` states `.td-main .td-content a { color: … }`, so a bare `.glossary-tooltip` loses to it wherever the file is imported and every tooltip renders orange instead of body-coloured.
- **Vale reads front matter.** `id: axorouter` trips `Vale.Terms`, and product-name slugs trip `Vale.Spelling`. Expect a few unavoidable alerts per term file, or scope the two rules off the glossary directory in the site's `.vale.ini`.
- **PurgeCSS**: every class is written in this theme's layouts, which `postcss.config.js` scans, so nothing here needs a safelist entry. Verify after adding classes.

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
