# Structural checks

What each issue in the `ia_inventory.py` summary means, when it's a false
alarm, and what to do about it. Then the reader-journey and cross-link checks
that the script can't do.

## Contents

- [Inventory issues](#inventory-issues)
- [Reader journey](#reader-journey)
- [Cross-links](#cross-links)
- [Labels and order](#labels-and-order)

## Inventory issues

Ordered roughly by how often the fix is worth doing.

`unresolved_link`
: A `relref`/`xref` or `.md` link whose target the script can't find. The
  script follows Hugo's rules (`a/b.md` and `a/b/_index.md` are the same
  page, and a unique basename resolves), but Hugo is the authority: confirm
  with `hugo --minify` warnings before reporting. Real ones are bugs, so
  fix them first.

`missing_index`
: A directory with pages but no `_index.md`. Hugo doesn't make it a section,
  so its pages attach to the parent in odd ways. Add an `_index.md` with a
  short landing text.

`weight_collision`
: Siblings with the same `weight`. The sidebar then orders them by title,
  which changes when someone renames a page. Give each a distinct weight,
  and keep the gaps (100, 200, …) so later pages fit in between.
  Exception: sections where alphabetical order is the intent (a man-page
  list, an A–Z driver list). In that case, say so under "Not changing".

`duplicate_sibling_title`
: Two siblings with the same sidebar label. Readers can't tell them apart.
  Fix the `linkTitle` or `title`.

`duplicate_title_sitewide`
: The same title on pages in different sections (for example, "Batch mode
  and load balancing" under four destinations). Search results, browser
  tabs, and `llms.txt` show only the title, so readers and agents can't pick
  the right one. Add the component to the title ("Elasticsearch: batch mode
  and load balancing") and keep a short `linkTitle` for the sidebar.

`mixed_type_hint`
: The script found strong signals of two Diátaxis types on one page. Read
  the page and classify it with `diataxis.md`. Confirm or dismiss each one.

`wide_section`
: A section with more children than `--max-children`. For component
  reference (all sources, all destinations) a long A–Z list is fine as long
  as the landing page helps readers choose. Then the fix is a better
  landing page, maybe with a grouped table ("by protocol", "by vendor"),
  not more folders. For task or concept sections, grouping into subsections
  usually helps.

`deep_page`
: Deeper than `--max-depth`. Report it only if a level in the path is a
  writer's folder (one child, or a label like "General") rather than
  something the reader recognizes. Flattening means moves, so weigh it
  against the link churn.

`no_inbound_links`
: No other page links here; it's reachable only through the sidebar and
  search. Normal for leaf reference entries under a landing page that lists
  them. Worth fixing for how-tos and explanation pages: find the pages
  where a reader would need this one, and link from there.

`dead_end`
: A page over 150 words with no outgoing internal links. Readers who finish
  it have nowhere to go. Add the cross-links from [Cross-links](#cross-links).

`missing_weight`
: The page sorts by title among weighted siblings. Add a weight.

`missing_description`
: Entries marked "has short_description to copy" already have a one-line
  summary for driver lists; reuse it. `description` feeds `llms.txt`, the section's child listing, JSON-LD, and
  search snippets. This is usually the largest count. Report the number and
  fix it by section, starting with landing pages, not page by page in the
  report.

`stub`
: Under 60 words of prose (snippets included), and not a section page with
  children. Either fill it, merge it into its parent, or make it a landing
  page.
  False alarm: pages whose body a layout renders from `data/` or front
  matter (for example, the appliance pages in axoflow-docs). Check the
  built page before reporting.

`unused_snippet`
: A `headless` file that no page or other snippet includes. Before calling
  it dead, `grep -rn '<filename>' content/`: some are named only in HTML
  comments on purpose (for example, obsolete option aliases kept for
  `axosyslog-cfg-helper` comparisons). Otherwise either it's dead (delete
  it, but ask first) or a page copies its text instead of including it
  (search for a distinctive sentence from it).

## Reader journey

Map the section, or the whole product, against these stages and name the
empty or weak ones. Each stage lists the pages a reader expects there.

| Stage | Reader's question | Expected content |
|---|---|---|
| Discover | What is this, and is it for me? | Intro, concepts overview, "how it works" diagram |
| Start | How do I get it running? | Install, quickstart, first working config |
| Connect | How do I get my data in and out? | One how-to per common source and destination, with the options reference under it |
| Shape | How do I parse, filter, enrich, route? | Task-level how-tos ("parse JSON logs", "drop debug messages"), not just parser/filter reference |
| Operate | How do I keep it healthy? | Monitoring, metrics, performance tuning, disk buffer, troubleshooting by symptom |
| Upgrade | How do I move to a new version or off syslog-ng? | Upgrade notes, migration guide, what's new |

Common gaps in reference-heavy docs, worth checking first:

- **Shape** stage: lots of parser and filter reference, few tasks written
  from the reader's goal.
- **Troubleshooting organized by symptom** ("messages are dropped", "high
  CPU", "TLS handshake fails") rather than by component.
- **Migration from syslog-ng**: readers arriving from syslog-ng need a
  "what's different" page.

For the Axoflow platform docs, the same stages apply, with Start covering
onboarding a host or deploying AxoRouter, and Connect covering data sources
and destinations.

## Cross-links

A page connects to others in four ways. Check that each page type has the
ones it needs:

| Link | What it points to | Needed on |
|---|---|---|
| Prerequisites | What to install or configure first | How-to, tutorial |
| Inline | The reference entry for each option, macro, or function used | How-to, tutorial, explanation |
| Next steps | The logical follow-up task | Tutorial, how-to, landing pages |
| Related | The same topic as another type (reference ↔ how-to ↔ explanation) | All |

In Docsy, section pages list their children automatically (unless the
section sets `no_list: true`; a child with `hide_summary: true` is left out
of the list). That covers "down" links, but not
"sideways" ones. A how-to under destinations that needs a parser option has
to link to it explicitly.

Use `relref` for internal links, following the project's shortcode rules
(`.claude/docs/shortcodes.md`).

## Labels and order

- A sidebar label should tell the reader what they get: "Send logs to
  Splunk HEC" or "splunk-hec() destination" beats "Splunk".
- Keep label patterns consistent among siblings: all component names, or all
  tasks, not a mix.
- Use `linkTitle` for a short sidebar label, and keep `title` descriptive
  and unique site-wide.
- Order siblings by the reader's path, not alphabetically, unless the list
  is a lookup (A–Z components). Put the landing or overview first, common
  tasks next, and reference and troubleshooting last.
