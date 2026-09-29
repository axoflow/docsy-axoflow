Review the documentation page I point you to (or the file I paste).

First, run Vale on the file and include its output in the review:

```
vale <file>
```

Then check for:
1. Compliance with simplified technical English using /ste100-writer
2. **Vale findings** — report all errors and warnings from the Vale output above;
   suppress Vale suggestions unless they reveal a real problem
3. **Style guide compliance** — read .claude/docs/style-guide.md first
4. **Front matter** — title, weight, description present and correct. Flag a
   missing `description`: `llms.txt` lists it as the page summary, and agents
   use it to decide which page to fetch. Suggest one sentence (under 160
   characters) that says what the page covers, not "This page describes…".
5. **Heading hierarchy** — no skipped levels, sentence case
6. **Headings containing shortcodes** — warn on every heading that has a
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

7. **Code blocks** — all have language identifiers, and every fence is closed.
   Flag commands and configuration examples that do not work if copied as-is,
   for example `...` placeholders or a fragment that has no context, unless
   the text explains what to add
8. **Shortcodes** — only approved shortcodes from .claude/docs/shortcodes.md
9. **Links** — internal links use the {{< relref >}} shortcode; no hardcoded
   full URLs. Flag `{{% xref %}}` calls that include an `#anchor`: the shortcode
   emits an already-resolved permalink, which the link render hook can't resolve
   back to a page, so the build warns. Use
   `[text]({{< relref "path.md#anchor" >}})` instead.
10. **Terminology** — correct spelling of AxoSyslog, syslog-ng, etc.
11. **Glossary terms** — the first mention of a glossary term in running prose
    should link to the glossary; later mentions stay plain. Report both
    directions: a first prose mention that is still plain, and any second or
    third tooltip for the same term on one page.

    ```markdown
    {{< glossary_tooltip term_id="axorouter" >}} collects data from your sources.
    Configure {{< router >}} from {{< console >}}.
    ```

    Term ids are the filenames in `content/reference/glossary/`. Do not suggest
    a tooltip, and flag it as an error where one is already used, in any of
    these — each renders broken rather than merely untidy:

    - **In a heading** — the heading ends up with the term's link beside its own
      self-link, so clicking the heading navigates away.
    - **Inside markdown link text**, as in `[{{< router >}}]({{< relref … >}})` —
      an anchor inside an anchor. Invalid HTML: the browser auto-closes the
      outer one and drops the author's link target silently.
    - **In an image caption, alt text, or a shortcode parameter** — same nesting
      problem, or the shortcode does not run there at all.
    - **On the page the term's `full_link` points at** — the tooltip links the
      reader to the page they are already on. Read the term's front matter in
      `content/reference/glossary/<term_id>.md` to check.

    To find every tooltip on the page and spot duplicates:

    ```
    grep -n 'glossary_tooltip' <file>
    ```

12. **Agent readiness.** Agents often fetch one page, or one section cut at a
    heading, as Markdown. The rules follow the
    [Agent-Friendly Documentation Spec](https://agentdocsspec.com/spec/web/).
    Flag:

    - **Page size**: the page is over about 50,000 characters of Markdown,
      which agents truncate. Check it with `wc -c <file>` (included snippets
      add to it). Suggest where to split the page.
    - **Headings that don't make sense out of context**: generic headings like
      "Example", "Options", "Step 1", or "Overview". Also headings that repeat
      on the same page. Suggest a specific heading that names the object, for
      example "Options of the `http()` destination".
    - **Sections that depend on earlier text**: "as described above", "the
      previous section", "see below", or a pronoun that points to another
      section. Suggest naming the object or linking to the section.
    - **Content only in images or screenshots**: a UI step that has only a
      screenshot, a command or configuration shown as an image, or a diagram
      without alt text.
    - **Tabs**: the Markdown copy writes the tabs out one after another under
      their tab titles. Flag tabs whose content doesn't make sense that way,
      for example because it doesn't say which option it applies to.
    - **Error messages in prose**: an error message or log line that's
      paraphrased or shown only in an image. Show it verbatim in `inline code`
      or a code block, so agents can match it.
    - **Answer not first**: a long introduction or marketing text before the
      first useful content.

Return a prioritized list of issues with the line numbers and suggested fixes.
Do not make changes until I confirm.

When referring to a specific line in a finding, format the reference as
`<absolute-file-path>:<line-number>` (for example,
`/Users/you/project/content/example.md:48`) — Claude Code renders this pattern
as a terminal hyperlink the user can CMD+click to open in the editor. Use this
format every time you cite a line — in section headings, inline references, and
when introducing suggested fixes — instead of bare `Line 48` text.
