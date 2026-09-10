Check the marketing chrome against axoflow.com and update the data files that
render it when it has drifted.

Four checkers in this submodule. Three compare content; the fourth compares
live's own design against a recorded baseline:

| Script | Data file | Live |
|--------|-----------|------|
| `check_main_menu.py` | `data/nav-menu.yaml` | the navbar, bar and phone menus |
| `check_footer.py` | `data/footer.yaml` | `footer.v3-footer_component` |
| `check_banner.py` | `data/chrome.yaml` | `.v2-banner_component` |
| `check_chrome_css.py` | `baselines/chrome-css.json` | the chrome's own CSS rules |

The first three report wording and layout drift as well as links: a group's
heading and blurb, the one-liners under the product rows, the icons, and which
column a group sits in. A rewritten blurb is drift even when every URL matches.

## 1. Report first

Run all four in report mode, in one message so they go in parallel:

```
python3 themes/docsy-axoflow/scripts/check_main_menu.py
python3 themes/docsy-axoflow/scripts/check_footer.py
python3 themes/docsy-axoflow/scripts/check_banner.py
python3 themes/docsy-axoflow/scripts/check_chrome_css.py
```

Exit status is the signal: `0` in sync, `1` drift, `2` a runtime error. A
`WARNING: attempt 1/4 to fetch … IncompleteRead` line is normal — axoflow.com
truncates roughly every other response and the scripts retry.

If all three exit 0, say so and stop. Do not run `--write`.

On exit 2, report the error and stop — a scrape that found nothing usually means
the marketing markup changed, which is a script fix, not a data fix.

## 2. Show me the drift before writing

For each script that exited 1, show me its report and call out these lines,
because `--write` does NOT resolve them on its own:

- **Rows live has dropped** (`-` in the report). The merge is additive and keeps
  them, so they survive the write. List them and ask me whether each one should
  stay (a deliberate entry this site adds) or go (marketing retired the page).
- **Notes.** Every note is something the data file holds that live does not say.
  Repeat them verbatim; §4 covers the ones that need work of their own.
- **Reworded and repointed rows** (`~`). These are marketing's copy changes and
  the write takes them as-is, but a label that reads like a typo is worth
  flagging — `data/footer.yaml` already carries one correction for exactly that.

## 3. Write

Then, per script that drifted:

```
python3 themes/docsy-axoflow/scripts/check_main_menu.py --write
python3 themes/docsy-axoflow/scripts/check_footer.py --write
python3 themes/docsy-axoflow/scripts/check_banner.py --write
```

Never edit the YAML by hand instead — every one of these files says at the top
that its values are read off the live DOM, and hand-edits are what the checkers
exist to catch.

Then, for each file written:

1. `git diff -- themes/docsy-axoflow/data/` and read it.
2. **Look for comments the write dropped.** The menu and footer writers preserve
   the comment blocks that sit above a key, but not a comment above one item of
   a list, and both files carry those. If the diff removed one, put it back.
   (`check_banner.py` rewrites only two lines, so it cannot lose any.)
3. Re-run that checker. What is left should be only the rows I said to keep in
   §2 — anything else means the merge did something I did not agree to; show me.

## 4. Follow-ups the scripts only report

Handle these when the notes mention them:

- **`re-vendor it`** (a badge, or the footer logo). The data file points at a
  file under `themes/docsy-axoflow/assets/img/footer/`; live now serves
  something else. Download live's file into that directory, keep the repo's
  naming style (`soc2-logo.webp`, not the CDN's hash), and set
  `badges[].file` to the new path. Show me the new image before committing it.
- **`no glyph named X in footer/row-3.html`.** A new social network. The mark
  has to be added to the `$glyphs` dict in
  `themes/docsy-axoflow/layouts/_partials/footer/row-3.html` as a 24x24 path, or
  the anchor renders empty. Ask me for the artwork.
- **A shape the schema cannot hold.** The rows are all there, but they do not
  sit the way live's do. Report it; changing it means changing
  `navbar-menu.html` and its stylesheet, which is a separate job I have to ask
  for.

- **`check_chrome_css.py` reporting drift.** It says marketing redrew a box and
  names the rule. It does NOT say what this site should do about it, and it
  cannot: live's classes and ours share no names, and whether two boxes look
  alike is a question about rendered geometry. So do not "fix" the SCSS from the
  diff. Show me the changed rules, say which of our own selectors reproduce
  those boxes (`grep` the class in `assets/scss/_axo-navbar.scss` — its comments
  cite live's measurements), and let me decide. Re-record the baseline with
  `--write` only once I have said the change is understood.

  The reason this stops here is that the visual half is not scriptable. Judging
  parity needs a browser, both sites side by side, and a decision about which
  differences matter. That review is the `/chrome-parity` skill — offer it when
  this reports drift, or when a menu changed shape. It needs a browser the user
  drives: Chrome is installed but cannot start under Claude Code's sandbox.

## 5. Verify the build

Data-file changes reach every page through the chrome partials, so build:

```
hugo --minify
```

Report any error or `WARN` that mentions the chrome. Then summarize what
changed, in one short list per data file, and stop — do not commit.
