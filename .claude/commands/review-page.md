Review the documentation page I point you to (or the file I paste).

Check for:
1. **Style guide compliance** — read .claude/docs/style-guide.md first
2. **Front matter** — title, weight, description present and correct
3. **Heading hierarchy** — no skipped levels, sentence case
4. **Code blocks** — all have language identifiers
5. **Shortcodes** — only approved shortcodes from .claude/docs/shortcodes.md
6. **Links** — internal links use the {{< relref >}} shortcode; no hardcoded
   full URLs
7. **Terminology** — correct spelling of AxoSyslog, syslog-ng, etc.

Return a prioritised list of issues with the line numbers and suggested fixes.
Do not make changes until I confirm.
