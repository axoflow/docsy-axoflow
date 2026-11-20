---
name: upstream-sync
description: "For a docs repo that mounts an upstream doc set as a submodule and overrides or adds pages (axosyslog-cv over axosyslog-core-docs, locker-docs over axoflow-docs): list what changed upstream since the pinned commit, check whether each local override page needs the same update or a correction, and decide for every other changed upstream file whether it applies to this product as is, or needs an only-in block upstream, a local override, or a stub page to hide it. Use before or after bumping the upstream submodule, or when someone asks what upstream changes mean for this doc set, whether overrides are stale, or what to wrap in only-in — even if they just say 'check upstream' or 'sync with core docs'."
---

# Upstream sync review

A downstream repo pins its upstream doc set as a submodule under `upstream/`,
and Hugo mounts the upstream `content/` and `layouts/` (sometimes `data/`,
`assets/`, `static/`, `i18n/`) after the repo's own folders. A local file at
the same mounted path wins. That gives three ways to diverge:

- **Override:** a local file at the same path replaces the upstream one. It
  stops following upstream, so every upstream edit to that page has to be
  ported by hand, or deliberately not.
- **Stub:** an override whose front matter has `build: {render: never, list: never}`
  hides the upstream page.
- **`only-in`:** `{{% only-in "Product A, Product B" %}}…{{% /only-in %}}` in
  the *upstream* file shows the block only on sites whose `product_name`
  matches. Use it for a paragraph, a list item, or a table row that applies to
  some products only, so the page itself doesn't have to be overridden.

This skill reviews one range of upstream commits and says, per change, what
the downstream repo (or upstream) has to do. It writes a report and **edits
nothing** until the user approves.

## Step 1: collect the changes

Run from the downstream repo root:

```bash
python3 themes/docsy-axoflow/.claude/skills/upstream-sync/scripts/upstream_changes.py > "$TMPDIR/upstream.json"
```

- The default is a **preview**: it runs from the SHA pinned in `HEAD` to the
  upstream `origin/<default branch>`, after a fetch. That is what the next
  submodule bump would bring in. The fetch needs `github.com` access. If the
  fetch fails, the script warns and uses the local refs.
- `--last-bump` reviews the range the last committed bump brought in.
- `--base <sha> --target <ref>` sets the range explicitly. `--no-fetch` skips the fetch.

If `base == target`, tell the user that upstream has nothing new and stop.

The JSON has `product_name`, `base`, `target`, a `diff_cmd` template, and these buckets:

| Bucket | Meaning |
|---|---|
| `overridden` | A local file replaces the changed upstream file. `stub: true` means it hides the page. `note` flags a local file in a different page-bundle form (`foo.md` vs `foo/_index.md`), which can make both build. |
| `orphaned_override` | Upstream renamed or deleted a file that has a local override. The override now builds as a page of its own, and on a rename the upstream page comes back unreviewed at its new path. **Always the top priority.** |
| `shared` | Headless snippets, shortcodes, partials, and assets. `used_by_local` lists the local pages that pull them in. |
| `new` | New upstream pages. This product shows them unless something hides them. |
| `changed` | Changed upstream content pages without an override. |
| `deleted` | Deleted upstream pages. `linked_from_local` lists the local files that still reference them. |
| `not_mounted` | Upstream config, package, and theme changes. These don't reach the site directly. |

Entries can also carry `under_unrendered_section`: a local section
`_index.md` with `render: never` above the page. Without a cascade, the page
still builds but has no place in the sidebar.

## Step 2: gather the product context

Before you judge any change, read:

1. The downstream `CLAUDE.md`, for what the product is and how it differs from upstream.
2. The page that lists what this product lacks or adds compared to upstream,
   if the repo has one. For example, axosyslog-cv has
   `content/chapter-concepts/axosyslog-cv-vs-axosyslog/`. Find it by searching
   the content for "differences" and by checking `CLAUDE.md`.
3. The existing stubs: `grep -rl "render: never" content/`. These show the
   kind of material this product already hides. A new upstream page on the
   same topic most likely needs hiding too.
4. The `only-in` blocks upstream that already name this product, or leave it
   out: `grep -rn 'only-in' upstream/*/content`. They show the line upstream
   already draws.

## Step 3: review the overrides (`overridden`, `orphaned_override`)

For each entry, read the upstream diff
(`git -C <upstream> diff <base> <target> -- <path>`) and the whole local file.
Then decide:

- **Port:** the change fixes or adds something that is also true for this
  product, and the override has the old text. Give the patch adapted to the
  override, with the product name, links, and any rewording the override
  already uses.
- **Correct:** the change shows the override is now wrong, for example a
  renamed option, a changed default, or a removed step. Give the patch.
- **Skip:** the change is about something this product doesn't have. Say why
  in one line.
- **Drop the override:** upstream now says what the override said, or could
  say it with an `only-in` block. Suggest deleting the local file and, if
  needed, the `only-in` edit upstream.
- **Stubs:** check only whether the page still has to be hidden. If upstream
  rewrote the page so it now applies to this product, suggest removing the stub.
- **Orphans:** on a rename, the override has to move to the new path. Use
  `/move-page`, so aliases and cross-references follow. Then review the
  override as above. On a delete, decide whether the local page still has a
  reason to exist. If it does, it is now a local page and needs a sidebar
  `weight` that fits.
- **`note` (page-bundle mismatch):** recommend renaming the local file to the
  same form as upstream, through `/move-page`.

## Step 4: review everything else (`shared`, `new`, `changed`, `deleted`)

Group the entries by page and read each diff. Low-risk changes (typos, link
fixes, formatting, wording that doesn't name a feature) need one line at most
in the report. Collect them under "Applies as is".

For every change that adds or changes a **feature, option, driver, platform,
install step, product name, license term, or UI element**, decide:

| Situation | Action |
|---|---|
| True for this product too | **Applies as is.** |
| A block that doesn't apply here, in a page that otherwise does | **Upstream `only-in`.** Give the exact upstream file, the lines to wrap, and the product list. List the products that *should* see the block, not this product, unless this product is the only one. |
| The page is mostly right, but needs product-specific wording throughout | **New local override.** Copy the upstream file to the same path under `content/` and adapt it. |
| A whole new page or section that doesn't apply | **Stub** at the same path (`build: {render: never, list: never}`, keeping `title`), or `only-in` upstream if the page is a small one. Check `under_unrendered_section` first, because the page may already be out of the navigation. |
| A changed headless snippet or shortcode used by local pages (`used_by_local`) | Check that each listed page still reads correctly with the new snippet, and that new parameters or anchors don't break it. |
| A deleted upstream page with `linked_from_local` entries | Fix the local links. A broken `xref`/`relref` is a build error or warning. |

For `not_mounted`: scan the upstream config diff for new or renamed `params`
that mounted content now uses (for example `{{% param "…" %}}`), new menu
entries, and `themes/docsy-axoflow` bumps. A theme bump upstream usually
means the downstream repo should bump its own theme submodule to the same commit.

When you are unsure whether a feature exists in this product, say so in the
report, and say what would settle it: a build flag, a package listing, or the
differences page. Don't guess.

## Step 5: write the report

Write `tmp/upstream-sync-<YYYY-MM-DD>.md` in the downstream repo. Put the
range and the mode in the header. Group the findings by **who acts**, with the
most important first:

1. **Fix here first:** orphaned overrides, broken local links, and overrides
   that are now wrong.
2. **Port into overrides:** upstream changes the overrides should get.
3. **New overrides or stubs here:** pages to add.
4. **Upstream `only-in` edits:** grouped by upstream file, so they can go into
   a single upstream PR.
5. **Applies as is:** one line per page, or a count for trivial ones.

Each item names the file, says what to do in one sentence, and gives the patch
or the exact text when it is short. In the chat, give the counts per group
and the report path, then ask which groups to apply.

## Applying the changes

Only after the user approves:

- Make local edits in the downstream repo. Moves go through `/move-page`.
  New pages and overrides follow `.claude/docs/style-guide.md` and the
  front-matter rules.
- Never edit the files in `upstream/`. That is a submodule checkout, and
  edits there are lost or end up on a detached HEAD. Upstream `only-in` edits
  go into the upstream repo itself (ask where it is checked out) on a branch,
  or stay in the report for the user to raise.
- Bump the submodule only if the user asks for it. After a bump, build the
  site (`hugo`, without `--quiet`), because a stub, orphan, or missing link
  shows up as a build error or warning.
