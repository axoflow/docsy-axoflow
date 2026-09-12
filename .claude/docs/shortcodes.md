# Available Hugo Shortcodes

Only use shortcodes listed here or shortcodes that already appear in the
existing codebase. Do not invent new ones.

## Admonitions (Docsy)

```markdown
{{% alert title="Note" color="info" %}}
Supplementary information.
{{% /alert %}}

{{< warning >}}
Potential data loss or security concern.
{{< /warning >}}

{{< caution >}}
Irreversible or high-risk action.
{{< /caution >}}
```

## Include file snippet

If a file (for example a warning, a section, or the description of a parameter) is used in multiple pages, include the re-used snippet from the `content/headless` folder like this:

```markdown
{{< include-headless "path/to/snippet.md" >}}
```

The path is relative to `content/headless`.

### Macros (placeholder substitution)

A snippet can contain numbered placeholders `{{1}}`, `{{2}}`, … up to `{{9}}`. Pass values as extra positional arguments to replace them, so the same snippet can be reused with different parameter names:

```markdown
{{< include-headless "option-use-macros.md" "key" "cert" >}}
```

For example, if the snippet contains `Set the {{1}} and {{2}} fields.`, the call above renders as `Set the key and cert fields.`

- **Missing value** — if a placeholder is left unfilled (fewer arguments than placeholders), the build **fails** with an error naming the snippet and call site.
- **Extra value** — if an argument has no matching placeholder, the build logs a **warning** but succeeds.
- Values are inserted as plain text; avoid HTML-special characters.

To combine macros with the optional `module` parameter, use the named form for every argument (Hugo forbids mixing positional and named arguments in one call):

```markdown
{{< include-headless file="option-use-macros.md" module="axosyslog-core" 1="key" 2="cert" >}}
```

In some cases, the `include-headless` shortcode doesn't work or is not practical, for example if the page has a frontmatter parameter that is used with the `if` shortcode in the snippet/ In these cases use `readfile`:

```markdown
{{< readfile "/path/to/file/from-content" >}}
```

The path is relative to `content/`.

## Include external file as code block

```markdown
{{< include-code file="path/to/example.conf" language="syslog-ng" >}}
```

The path is relative to the page's directory (page bundle) or to `content/`.

## Cross-reference link

```markdown
{{% xref "path/to/md/file" %}}
```

Renders the linked page's `title` as the anchor text automatically.
Override with explicit text:

```markdown
[custom anchor text]({{< relref "path/to/file.md" >}})
```

The path is relative to `content/`.

## Glossary

Terms live in one leaf bundle, `content/reference/glossary/` by default, with
one file per term named after the term's `id`. Setting up a glossary for a site
is documented in `themes/docsy-axoflow/CLAUDE.md`.

### Link a term inline

```markdown
{{< glossary_tooltip term_id="axorouter" >}}
{{< glossary_tooltip term_id="axorouter" text="the router" >}}
```

Renders the term as a link that shows its short definition on hover. `text`
defaults to the term's title; use it to inflect the term into the sentence
("edge hosts", "tap into a running data flow"). An unknown `term_id` fails the
build, so a typo cannot ship as a dead link.

Where the term's front matter sets `full_link`, the link goes to that page.
Otherwise it goes to the term's own entry in the glossary.

### Inline a definition

```markdown
{{< glossary_definition term_id="axorouter" length="short" >}}
{{< glossary_definition term_id="axorouter" length="all" prepend="In this deployment," >}}
```

Pulls a definition out of the glossary, so a concept page and the glossary
cannot drift apart. `length` is `short` (the first paragraph) or `long`/`all`
(the whole definition). `prepend` splices your own opening onto the first
sentence and lower-cases what followed.

---

*If you need a shortcode that is not listed here, ask the user before
creating one — new shortcodes require a layout file in `layouts/shortcodes/`.*
