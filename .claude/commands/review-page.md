Review the documentation page I point you to (or the file I paste).

First, run Vale on the file and include its output in the review:

```
vale <file>
```

Then check for:
1. **Vale findings** — report all errors and warnings from the Vale output above;
   suppress Vale suggestions unless they reveal a real problem
2. **Style guide compliance** — read .claude/docs/style-guide.md first
3. **Front matter** — title, weight, description present and correct
4. **Heading hierarchy** — no skipped levels, sentence case
5. **Headings containing shortcodes** — warn on every heading that has a
   shortcode but no explicit `{#custom-anchor}`, for example
   `### {{< console >}} updates`. Hugo derives the heading ID from the
   *unexpanded* shortcode placeholder, producing garbage like
   `hahahugoshortcode445s15hbhb-updates`. The numeric part shifts whenever
   content above the heading changes, so every link and bookmark to it breaks
   silently. Suggest a stable anchor for each occurrence. To see the real IDs,
   build the site and inspect them:

   ```
   hugo --minify && grep -oE '<h[1-4] id="[^"]*"' public/<page-path>/index.html
   ```

6. **Code blocks** — all have language identifiers
7. **Shortcodes** — only approved shortcodes from .claude/docs/shortcodes.md
8. **Links** — internal links use the {{< relref >}} shortcode; no hardcoded
   full URLs. Flag `{{% xref %}}` calls that include an `#anchor`: the shortcode
   emits an already-resolved permalink, which the link render hook can't resolve
   back to a page, so the build warns. Use
   `[text]({{< relref "path.md#anchor" >}})` instead.
9. **Terminology** — correct spelling of AxoSyslog, syslog-ng, etc.

Return a prioritized list of issues with the line numbers and suggested fixes.
Do not make changes until I confirm.

When referring to a specific line in a finding, format the reference as
`<absolute-file-path>:<line-number>` (for example,
`/Users/you/project/content/example.md:48`) — Claude Code renders this pattern
as a terminal hyperlink the user can CMD+click to open in the editor. Use this
format every time you cite a line — in section headings, inline references, and
when introducing suggested fixes — instead of bare `Line 48` text.
