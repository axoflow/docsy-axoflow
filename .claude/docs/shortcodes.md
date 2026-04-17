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

---

*If you need a shortcode that is not listed here, ask the user before
creating one — new shortcodes require a layout file in `layouts/shortcodes/`.*
