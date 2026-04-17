# Documentation Style Guide

This is the generic Axoflow style guide. Use it together with the project-specific style guide (`.claude/docs/style-guide.local.md`).

## Voice and tone

- **Second person** — address the reader as "you".
- **Active voice** — "AxoSyslog sends the log" not "the log is sent".
- **Present tense** — "The parser extracts…" not "The parser will extract…".
- Professional but not stuffy; assume a technically literate audience (syslog
  admins, DevOps engineers, developers).
- Use American English.
- If possible, follow the Microsoft Style Guide (it's also enabled in the vale config).
- Don't use hyphens and em-dashes to separate parts of a sentence. Use colons, parenthesis, commas, or separate sentences instead.
- Avoid Latin abbreviations (e.g., i.e.) — use "for example" and "that is".
- Follow the Microsoft Manual of Style if possible.

## Terminology

| Use | Avoid |
|-----|-------|
| AxoSyslog | Axosyslog, axosyslog, AxoSysLog |
| configuration file | config, conf |

## Headings

- **Sentence case**: "Configure the network source" not "Configure The Network
  Source".
- Use `##` (H2) for top-level sections within a page; `#` (H1) is used automatically for the
  page title set via front matter.
- Do not skip heading levels.
- Keep headings short (≤ 8 words where possible).
- Avoid using gerund in the title (`## Do stuff`).
- For long headings or headings with non-alphabetic characters, include a custom anchor, for example `## <commplex-heading> {#custom-anchor}`

## Code and configuration

- Inline code: option names, values, file paths, command names → `backticks`.
- Code blocks: always specify the language fence, e.g. ` ```yaml ` or
  ` ```shell `.
- For AxoSyslog configuration syntax, use `shell` as the
  language identifier.
- Prefer complete, runnable examples over fragments. If an example is
  incomplete, add a comment explaining what the omitted parts are.
- Never include real IP addresses, hostnames, or credentials in examples; use
  `192.0.2.x` (TEST-NET), `example.com`, and `<YOUR_VALUE>` placeholders.

## Lists

- Use bullet lists (dash) for unordered items; numbered lists for sequential steps. For numbered lists, start every item with `1.`
- Parallel structure within a list (all items start with a verb, or all are
  nouns, etc.).
- Avoid lists with only one item — convert to prose.

## Admonitions

Use Docsy shortcodes for callouts:

```markdown
{{% alert title="Note" color="info" %}}
Use notes for supplementary information the reader might find useful.
{{% /alert %}}

{{< warning >}}
Use warnings for information about potential data loss or security risks.
{{< /warning >}}
```

Do not use `> **Note:**` blockquote patterns — always use the shortcodes.

## Links and cross-references

- For internal cross-references:

    - Use the `{{< relref >}}` shortcode if the link text is custom text.
    - Use the `{{< xref >}}` shortcode to use the title of the linked heading/page as the link text.
    - Use bare Markdown links only for links within the same page.
    - To link to place in a page that's not a heading (for example, a step in a procedure), add an anchor like this: `<a name="exchange-secret" class="htmlanchor"></a>`.

    The path in the relref/xref can be relative, or hugo-style absolute (beginning with slash) that is relative from the content directory of the hugo project. Note that if the project uses hugo module mounts, the path must be where the file is mounted, not where the original source file is.

- Do not hardcode the full site URL in internal links.

## Paths, and cross-references

Use project-absolute (hugo-style) paths if possible (start with `/`, relative to the content folder, for example to reference `content/docs/folder/file`, use `/docs/folder/file`).

Hugo checks only that the referenced file exists, it doesn’t check the anchor, so using an invalid anchor won’t fail the build (and won’t produce a warning).

## Images

- Store images in the same directory as the page that uses them (page bundle).
- If the same image is used in multiple pages, place it in the `/assets/img/` directory, and link to it as `![image title](/img/<filename>)`.
- Use descriptive `alt` text.
- Prefer SVG for diagrams; PNG for screenshots.

## Versioning notes

- When documenting a feature introduced in a specific AxoSyslog version, add the following at the top of the relevant section: "Available in {{% param "product.name" %}} <version-number> and later."
