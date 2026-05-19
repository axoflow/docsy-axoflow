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
- For long headings, headings with non-alphabetic characters, or headings that include shortcodes, include a custom anchor, for example `## <complex-heading> {#custom-anchor}`

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
- Use plain markdown `![alt](src)` syntax — **do not** wrap images in `<img>` HTML, `figure` shortcodes, or `imgproc` shortcodes unless you need a class. The theme's markdown image render hook (`layouts/_markup/render-image.html`) does the heavy lifting automatically.

### What the render hook does for you

Every `![alt](src)` in markdown is rewritten by the render hook into a responsive `<img>` element. You don't need to set anything yourself — Hugo derives it all from the source file:

- **WebP conversion** of raster sources (PNG / JPEG / GIF) at build time. SVGs pass through unchanged.
- **Responsive `srcset`** at 400 / 800 / 1200 / 1600 px widths (widths larger than the natural width are skipped, so we never upscale).
- **`sizes` attribute** aligned with the Docsy content column: `(min-width: 992px) 720px, 100vw`.
- **Explicit `width` and `height`** from the natural image dimensions — kills CLS and the `unsized-images` Lighthouse audit.
- **`loading="lazy"`** on every image except the first one on the page.
- **`decoding="async"`** on every image.

### Above-the-fold prioritization

The render hook treats the **first** markdown image on a page as the likely LCP candidate and emits `loading="eager" fetchpriority="high"` instead of `loading="lazy"` for it. On most doc pages this is correct — Docsy's content column starts a couple hundred pixels in, intros are short, and the first screenshot or diagram lands at or just below the fold.

When the heuristic is wrong, override it from the page's front matter:

```yaml
---
title: My page
weight: 200
# The first markdown image is a small icon, not the LCP — disable the hint:
no_priority_image: true
---
```

```yaml
---
title: My page
weight: 200
# The LCP is actually the third image on the page — name it explicitly. Match
# is by exact .Destination string equality (the value inside the ![](…) parens).
priority_image: /img/topology/topology.png
---
```

Rules of thumb for when to set these:

| Page shape | What to set |
| --- | --- |
| Short intro → first image is a screenshot or diagram | nothing (default is correct) |
| First image is a small status badge / icon | `no_priority_image: true` |
| First image is an SVG diagram that's small | `no_priority_image: true` |
| Long intro pushes the first image below the fold | `no_priority_image: true` |
| The LCP is the third image, not the first | `priority_image: "<exact src string>"` |

### Captions

If you supply a markdown title (the quoted string after the URL), the render hook wraps the image in `<figure><figcaption>…</figcaption></figure>`:

```markdown
![Alt text for screen readers](deployment-diagram.svg "Caption that's visible under the image.")
```

Reserve captions for images that genuinely need explanatory text below them. Most screenshots don't.

### When to bypass the render hook

The render hook only touches plain markdown `![]()` syntax. If you need something it can't express, use one of the existing escape hatches:

- **Need a CSS class** (`screenshot-medium`, `screenshot-small`, etc.) — use an inline HTML `<img>` tag. The render hook leaves HTML alone.
- **Need precise sizing or cropping** — use the `imgproc` shortcode (`{{< imgproc src "Resize 600x" >}}`).
- **Need `<picture>` with format fallbacks** — also use inline HTML or `imgproc`.

In all other cases, write plain `![alt](src)` and let the hook do its job.

## Versioning notes

- When documenting a feature introduced in a specific AxoSyslog version, add the following at the top of the relevant section: "Available in {{% param "product.name" %}} <version-number> and later."
