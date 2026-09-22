Add a new term to the glossary under `content/reference/glossary/`.

The term becomes usable with `{{< glossary_tooltip >}}` and
`{{< glossary_definition >}}` (see `themes/docsy-axoflow/layouts/_shortcodes/`).

If I named the term in the command arguments, take it as the answer to question 1
and don't ask it again.

## Step 1 — gather the info

First read `data/canonical-tags/*.yaml` for the current tag list, and list the
existing term files so you can spot duplicates and reuse their voice.

If a file for the term already exists, stop and tell me — offer to edit it
instead of creating a second one.

Ask me, in one `AskUserQuestion` round where the options are real choices and
free text where they aren't:

1. **Term** — the `title`, spelled as it appears in prose (`AxoRouter`, `SIEM`,
   `Apache Parquet`).
2. **Tags** — multi-select from `data/canonical-tags/`. At least one is
   required; a term with no tag is invisible in the filtered list. Offer
   `fundamental` alongside a topical tag for terms a reader meets in the first
   hour.
3. **Short description** — one sentence, the hover text. If I give you a rough
   version, tighten it and show me the result.
4. **Long definition** — the body after `<!--more-->`. Offer "skip for now" as an
   option; the `<details>` block is only drawn when this part is non-empty.
5. **`full_link`** — the concept page the tooltip should link to instead of the
   glossary entry. Search `content/` for a plausible target and offer it as the
   first option, plus "none (link to the glossary entry)". Must be
   site-relative, and it is build-validated.
6. **`aka`** — optional list of alternative names (the spelled-out form of an
   acronym, an older product name).

Derive the `id` from the term yourself — lowercase, hyphenated — and confirm it
with me only if it isn't obvious (`Apache Parquet` → `parquet`, not
`apache-parquet`).

## Step 2 — write the file

`content/reference/glossary/<id>.md`. **The filename stem is the lookup key and
must equal the `id` field**, or the shortcodes error out.

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
```

Rules that bite:

- **`short_description` is front matter, so no shortcodes.** Write
  "Axoflow Platform", "AxoRouter" literally — a `{{< product >}}` there ships as
  raw text into the tooltip.
- **The body is markdown, so use the shortcodes.** `{{< product >}}`,
  `{{< router >}}`, `{{< console >}}`, `{{< edge >}}`, `{{< lake >}}`,
  `{{< router-store >}}` for product names, and `{{< glossary_tooltip >}}` for
  every other glossary term the definition mentions — that cross-linking is what
  makes the glossary worth reading.
- The first paragraph is the preview and is what
  `{{< glossary_definition length="short" >}}` inlines elsewhere, so it has to
  stand alone as a sentence in someone else's page.
- Follow `.claude/docs/style-guide.md`: second person, active voice, present
  tense. Definitions say what the thing *is* first, why it matters second.

## Step 3 — verify

- `hugo --renderToMemory --logLevel warn` — an unresolvable `full_link`, an
  absolute one, or a dead fragment is reported here and nowhere else. Run it
  **bare**: an env-var prefix or a `>` redirect stops it matching the `hugo *`
  sandbox exclusion, and the sandboxed build then dies on an unrelated file
  whose name trips the secrets guard.
- Run `/lint` on the new file. Vale reads front matter, so `id:` and product
  slugs raise a few unavoidable alerts — report them, don't chase them.
- Tell me which existing pages mention the term in plain text and could now
  carry a `{{< glossary_tooltip term_id="<id>" >}}`. Don't edit them unless I
  say so.
