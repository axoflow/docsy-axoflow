---
name: docs-ia
description: "Audit and improve the information architecture of an Axoflow Hugo/Docsy documentation site: classify pages by Diátaxis type (tutorial, how-to, reference, explanation), find pages that mix types, gaps in the reader journey, sidebar problems (weight collisions, overlong sections, duplicate titles, missing _index.md or description), orphan and dead-end pages, and unused headless snippets, then propose fixes that go through /move-page. Use this whenever someone asks where a new page should go, wants to restructure or reorganize a section or the sidebar, asks for a content audit, gap analysis, or Diátaxis review, says a section is hard to navigate or find things in, or plans a larger docs reorganization — even if they never say 'information architecture'."
---

# Docs information architecture

This skill audits how a docs site is organized, not how individual sentences
read. Sentence-level review belongs to `/review-page` and `/lint`; moving
files belongs to `/move-page`. This skill decides *what* should change and
*why*, and hands the mechanics to those.

Two ideas drive it:

- **Diátaxis** says each page serves one of four reader needs: learning by
  doing (tutorial), getting a task done (how-to), looking something up
  (reference), or understanding (explanation). Pages that try to serve two
  needs at once serve both badly. That's the main page-level finding.
- **Change things one page at a time.** Diátaxis itself warns against
  reorganizing everything into four top-level folders at once. A big move
  breaks links and bookmarks and makes review impossible. Prefer small,
  independent fixes that leave the site better after each one.

## Axoflow-specific ground rules

These override generic IA advice, so keep them in mind while judging:

- **Reference organized by component is correct.** AxoSyslog's
  `chapter-sources/`, `chapter-destinations/`, `chapter-parsers/` and the
  Axoflow platform's per-integration pages are organized the way readers look
  things up: by the config object or product they're using. Don't propose
  splitting them into `tutorials/`, `how-to/`, `reference/` folders. Within a
  component, the usual pattern is a short landing page (what it is, a minimal
  example) with an options page under it. That's a healthy
  reference-plus-how-to pair, not a mixed page.
- **Depth is fine where it mirrors the product.** "Keep it to two or three
  levels" is web-IA advice for browsing sites. A deep reference tree is fine
  if each level is something the reader recognizes. Flag depth only when a
  level exists for the writer's convenience (a folder holding one page, or a
  level named "Overview", "General", "Misc").
- **Snippets are part of the page.** `content/headless/` files render inside
  the pages that include them (`include-headless`, `readfile`). The inventory
  script counts a snippet's words and links toward every page that includes
  it. When you read a page, read the snippets it includes too.
- **Never move, rename, or delete pages by hand.** Every structural change
  goes through `/move-page` (`move_hugo_files.py`), which keeps git history,
  adds aliases, and rewrites cross-references. New pages go through
  `/new-page`.
- **Follow the project's style guide** (`.claude/docs/style-guide.md` and any
  `style-guide.local.md`) for titles and labels you propose.

## Workflow

### 1. Scope

Ask what's being audited if it isn't clear: the whole site, one section, or
"where does this new page go?". A placement question skips to step 3 with
just the candidate sections. A full-site audit is large (AxoSyslog has about
500 pages), so do a site-wide structural pass, then deep-dive only into the
sections the user cares about or the inventory flags most.

### 2. Inventory

Run the script from the project root. It reads the whole site and resolves
links the way Hugo does, even when you narrow the report to one section:

```bash
python3 themes/docsy-axoflow/.claude/skills/docs-ia/scripts/ia_inventory.py --section <path-under-content>
# per-page data for sorting and reading:
python3 themes/docsy-axoflow/.claude/skills/docs-ia/scripts/ia_inventory.py --section <path> --format json --out tmp/ia/inventory.json
```

Options: `--max-depth` (default 4), `--max-children` (default 25),
`--content` and `--headless` if the site uses different directories,
`--no-git` to skip last-edited dates. Write outputs to a gitignored
directory: `tmp/` in axosyslog-core-docs. Check `.gitignore` in other repos.

With `--section`, page checks cover the section only, but `unused_snippet`
is always site-wide, because snippets don't belong to a section. You don't
need a second whole-site run.

The summary lists structural issues with a one-line meaning for each. Read
`references/structure-checks.md` for what each one implies and when it's a
false alarm. For example, `no_inbound_links` is normal for leaf reference
pages the sidebar already lists.

The `type_hint` per page is a cheap guess from counted signals (numbered
steps, `name()` option headings, tables, tutorial phrasing, concept-like
paths). Use it only to decide which pages to read first, never as a
classification. It's often wrong on short pages and on table-heavy pages,
and a numbered list that describes a process (not a procedure) looks like a
how-to.

### 3. Classify

Read and classify with `references/diataxis.md`:

- every landing page (`_index.md` with children) and anything flagged
  `mixed_type_hint`;
- `unclear` pages over ~200 words;
- for sections under ~80 pages, the rest too; for larger ones, about one in
  five of the rest, picked across subsections.

Record:

- the type, with **high / medium / low** confidence;
- the evidence (a heading, a sentence, the structure);
- if it's mixed: which parts belong to which type.

Don't classify from titles alone. "Configuring X" pages in these repos are
often reference with an example, not how-to guides.

### 4. Assess the section

Look at the section as a reader would, not as a list of files:

- **Reader journey.** Can someone go from "what is this" to "it's running
  and I can troubleshoot it"? Check the stages in
  `references/structure-checks.md#reader-journey` and name the missing ones.
- **Type balance.** A section that's all reference with no how-to for its
  most common task is a gap, not a style problem. So is a section with
  how-tos but nowhere that explains what the component is and when to use
  it: neither an explanation page nor a landing page that does it. The
  concept text is then usually scattered across how-to intros; gather it
  into the landing page or a new explanation page.
- **Findability.** Sidebar labels: do they say what the page is for? Are
  siblings in a sensible order (weights)? Are two pages competing for the
  same query (duplicate titles, overlapping content)?
- **Connections.** Do how-tos link to the reference they use, and does the
  reference link back to a how-to? Are there dead ends?
- **Hand-maintained lists.** A landing page or snippet that lists the
  section's children by hand (a table of drivers, say) drifts as pages are
  added. Compare it against the real children in the inventory. If the
  project has a shortcode that generates the list (for example,
  `list-drivers` in axosyslog-core-docs), propose that instead.

### 5. Report

Write the report to `tmp/ia/<section>-<YYYY-MM-DD>.md` and summarize it in
chat: lead with the top three fixes. Use this structure:

```markdown
# IA audit: <section> (<date>)

## Summary
<3–5 sentences: what the section is for, overall health, the biggest problem.>

## Top fixes
1. <fix>: <why it matters to the reader>. Effort: S/M/L.
2. …
3. …

## Page classification
| Page | Type | Confidence | Notes |
|------|------|------------|-------|

## Mixed pages
### <page>
- Parts: <which headings are which type>
- Proposed split: <new page(s), what moves where, how they link>

## Gaps
- <missing journey stage or task>: <what page would fill it, where it goes>

## Structure
- <weight collisions, duplicate titles, labels, depth, unused snippets, with the fix>

## Proposed moves
| From | To | Why |
|------|----|-----|
(each row is one /move-page run)

## Not changing
- <things that look like problems but are fine here, and why>
```

"Not changing" matters. It stops the next audit from re-flagging the same
deliberate choices, and it shows the user you applied the Axoflow ground
rules rather than generic advice.

### 6. Act (only when the user asks)

Apply fixes in small, reviewable steps, one kind at a time, and run
`hugo --minify` after each batch. Do the changes that keep URLs first
(front matter, landing-page rewrites, splits, new pages), and confirm with
the user before the moves and merges that change paths. That way the
content changes can be reviewed and reverted without broken links mixed in.

- **Front matter fixes** (weights, `linkTitle`, `description`): edit
  directly. Descriptions follow `/review-page` rules: one sentence, under
  160 characters, says what the page covers. Where the inventory says a
  page "has short_description to copy", start from that text (it feeds
  driver lists, but not `llms.txt` or search snippets).
- **Moves and renames:** `/move-page`, one at a time. Report each result.
- **Merges** (folding a page into its parent or a sibling): `/move-page`
  can't merge, so do it by hand, in this order: move the text into the
  target page; add the removed page's URL (and its existing `aliases`) to
  the target's `aliases`; point every `relref`/`xref` to the removed page
  at the target (`grep -rn '<old-path>' content/`) and check any glossary
  `full_link`; then `git rm` the old file. Confirm with the user before the
  `git rm`.
- **Splits:** create the new page with `/new-page`, move the content, and add
  links both ways. If the same text has to appear on both pages, move it into
  a `content/headless/` snippet instead of copying it.
- **New pages for gaps:** propose an outline and get agreement before
  writing. Use the `technical-writer` agent if the project has one.

After the edits, rerun the inventory on the section and confirm the issues
you fixed are gone and nothing new appeared.
