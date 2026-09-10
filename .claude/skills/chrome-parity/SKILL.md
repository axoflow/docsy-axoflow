---
name: chrome-parity
description: "Review whether this documentation site's marketing chrome — the navbar and its mega panels, the announcement strip, the footer — still LOOKS like axoflow.com's, and decide what to change when it does not. Use when the chrome has been restyled, when scripts/check_chrome_css.py reports that live's design moved, after scripts/check_main_menu.py --write changes the shape of a menu, or whenever someone asks whether the bar, a dropdown panel, the strip or the footer matches the marketing site. This is the visual half that the four chrome checkers deliberately do not cover."
---

# Chrome parity review

The four scripts in `themes/docsy-axoflow/scripts/` answer everything about the
chrome that a diff can answer: `check_main_menu.py`, `check_footer.py` and
`check_banner.py` compare the words, links, icons and layout keys in the data
files against live's DOM, and `check_chrome_css.py` reports when live's own CSS
for the chrome changes. Run those first — this skill assumes they are green,
or that you know why they are not.

What none of them can answer is whether the result **looks** like axoflow.com.
That question is about rendered geometry, and it cannot be a script:

- The two sides share no class names. Live's panel is
  `.v3-navbar_mega-dropdown-col`; ours is `.axo-nav-col`. There is no mechanical
  mapping between their declarations.
- They reproduce the same boxes with deliberately different mechanisms. Live's
  1px column rule is its own `max-content` grid track; ours is a border. Live's
  dark fill lands on `:last-child`; ours on a named column. Both render
  identically, and a comparison of CSS text calls every one of them a
  difference.
- Which deltas matter is a judgement. An 8px row rhythm does. A font-smoothing
  hint does not.

So: measure both, diff the numbers, and decide. The measuring is deterministic
and lives in `measure.js` next to this file; the deciding is the part you are
here for.

## 1. Get both sides on screen at the same width

Serve the docs site:

```
hugo server --disableFastRender
```

Open <https://axoflow.com/> in one window and the URL Hugo prints in another
(`http://localhost:1313/` unless that port was taken), and **size both windows
the same**. Do the whole review at each of these three widths — they are the
bands the stylesheet is written against, and each one exercises a different
layout:

| Width | What it exercises |
|-------|-------------------|
| 1440 | the mega panels at the grid's full 1312px, and every measurement the SCSS comments quote |
| 1280 | the panel at 1232px, where the gutters change |
| 1100 | the `compact` variant — the six items no longer fit, so the whole outline collapses into one dropdown. Live has no equivalent, so compare it against live at 1280 for type and rhythm only, not for layout |

## 2. Measure

Paste `measure.js` into the DevTools console on each site. It detects which
site it is on, opens each mega panel, measures, closes it again, and copies a
JSON object to the clipboard. Save the four files:

```
chrome-parity-live-1440.json     chrome-parity-docs-1440.json
chrome-parity-live-1280.json     chrome-parity-docs-1280.json
```

It reports boxes relative to the panel's own left edge (so gutters and the
scrollbar do not enter into it), the gaps between columns and sub-columns, where
each section of a column starts and whether a rule sits above it, the dark
column's share of the panel, computed type for every role, and the row pitch of
the first link list.

If its `missing` array is not empty, a selector it expects is gone — that is a
finding in itself. Fix the profile at the top of `measure.js` and say so.

## 3. Diff, with these tolerances

Compare live against docs at the same width, field by field. Judge them like
this:

**Report as a defect**

- Any box position or size off by **more than 1px**. Half-pixel differences are
  the grid; 2px is a mistake.
- A different `columnGap`, `subcolGap`, or `highlightShare`. Live's dark column
  is 25% of the panel on the nose (328/1312 at 1440, 308/1232 at 1280).
- A different `sectionCount` or `sectionTops` length in any column: a section
  was gained, lost, or is sitting in the wrong column. This is what the
  `column` and `sub` keys in `data/nav-menu.yaml` exist to get right, so a
  mismatch here usually means the data is wrong, not the CSS.
- `sectionRules` disagreeing about whether a rule is above a section.
- Any `fontSize`, `fontWeight` or `lineHeight` difference at all. Live's scale
  is exact: 22px/500/1.45 for a card title and for a described product row,
  14px/500 for a link, 14px/500/1.8 for a sub-column heading, 12px/300 for a
  blurb.
- A `linkPitch` off by more than 1px. This is the one that hides: seven pixels
  per link is invisible in a screenshot and 40px too tall over a column.

**Do not report**

- Colours that differ only because the docs site is in dark mode. Check in
  light mode, or compare the light-mode values.
- `color` on the dark column: ours comes through `--axo-nav-on-dark`, live's is
  inherited. Same result, different route.
- Shadow and border colours within a hair of each other; live's own values are
  sampled, not specified.
- Anything about fonts that are not loaded locally, and any difference in
  antialiasing.
- The `compact` variant's layout. It has no counterpart on live.

## 4. Look at it as well

Numbers miss what a person sees at once: a wrapped label, a panel taller than
the viewport, an icon at the wrong size, a hover state that recolours when
live's only underlines. So after the diff, with each mega panel open on both
sides:

- Read across the two panels for wrapping and for text that overflows its
  column.
- Hover a link on each. Live's mega links underline and keep their navy; they
  do not change colour.
- Tab through one panel on the docs side. Live's is mouse-only, so this is the
  one place where we are deliberately better and a difference is not a defect.
- Check the strip and the footer at the same widths.

## 5. Report, then fix only what was agreed

Write the findings as a list, each one naming: the width, the box, live's number,
ours, and the delta. Then, for each, name the rule that owns it —
`assets/scss/_axo-navbar.scss` and `_axo-footer.scss` cite live's measurements
in their comments, so `grep` the number or the class and the owning rule is
usually one hit:

```
grep -n "1312\|axo-nav-cols\|highlight" themes/docsy-axoflow/assets/scss/_axo-navbar.scss
```

Then stop and ask which to change. Two reasons this is not automatic:

- A parity defect is sometimes the data's fault, not the stylesheet's. If a
  section is in the wrong column, the fix is `column:` in
  `data/nav-menu.yaml` — which means re-running `check_main_menu.py`, not
  editing SCSS.
- Some differences are deliberate. The keyboard behaviour above is one. The
  drawer below `md` is another: it renders `mobile.items`, a different menu from
  live's bar, on purpose.

When a fix is agreed:

1. Change the rule, keeping the comment style — these files explain *why* a
   number is what it is, and cite the measurement it came from. Add yours.
2. `hugo --minify` and re-measure at all three widths. A rule that fixes 1440
   often breaks 1280.
3. If the change was prompted by `check_chrome_css.py` reporting drift,
   re-record its baseline last, once the site has actually caught up:
   `python3 themes/docsy-axoflow/scripts/check_chrome_css.py --write`.

## Notes

- **This does not run in Claude Code's sandbox.** Chrome is installed but cannot
  start under it — crashpad and its socket directories are blocked — so the
  measuring has to happen in a browser the user drives. If you are asked to do
  this from a sandboxed session, say so and ask for the JSON files instead of
  pretending to have measured anything.
- If Playwright is available in the environment, the same measurements can be
  automated: navigate, set `aria-expanded="true"` on the docs toggle or click
  live's `.w-dropdown-toggle`, then `page.evaluate()` the body of
  `measure.js`. The tolerances above do not change.
- Never edit the data files by hand to fix a visual problem. They are read off
  live's DOM by the checkers, and a hand-edit is exactly what those exist to
  catch.
