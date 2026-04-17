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
5. **Code blocks** — all have language identifiers
6. **Shortcodes** — only approved shortcodes from .claude/docs/shortcodes.md
7. **Links** — internal links use the {{< relref >}} shortcode; no hardcoded
   full URLs
8. **Terminology** — correct spelling of AxoSyslog, syslog-ng, etc.

Return a prioritized list of issues with the line numbers and suggested fixes.
Do not make changes until I confirm.
