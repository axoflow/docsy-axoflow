# Hugo Front Matter Reference

All documentation pages use **YAML** front matter delimited by `---`.

## Minimal front matter (regular page)

```yaml
---
title: "Configure the network() source"
weight: 20
---
<!-- This file is under the copyright of Axoflow, and licensed under Apache License 2.0, except for using the Axoflow and AxoSyslog trademarks. -->
```

## Minimal front matter (section index `_index.md`)

```yaml
---
title: "Sources"
weight: 30
---
<!-- This file is under the copyright of Axoflow, and licensed under Apache License 2.0, except for using the Axoflow and AxoSyslog trademarks. -->
```

## All supported fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `title` | string | **Yes** | Displayed as the page heading and in the sidebar. Sentence case. |
| `weight` | integer | **Yes** | Controls sidebar order within the parent section. Lower = higher. |
| `description` | string | No | Short description for SEO `<meta>` and section cards. |
| `linkTitle` | string | No | Shorter title used in the sidebar when `title` is long. |
| `aliases` | list of strings | No | Redirect old URLs here after a page is renamed/moved. |
| `draft` | bool | No | Set `true` only for WIP pages not yet ready to publish. Never commit `draft: true` to main. |

## Example: full front matter

```yaml
---
title: "Configure the syslog() source"
linkTitle: "syslog() source"
weight: 10
description: >
  Receive RFC 5424 messages over TCP or UDP using the syslog() source driver.
aliases:
  - /docs/old-path/syslog-source/
---
```

## Rules

- Do **not** add a `date` field; Hugo derives it from Git history
  (`enableGitInfo: true` is set in `config/`).
- Do **not** add `lastmod` manually for the same reason.
- The `weight` values within each directory should be multiples of 10
  (10, 20, 30 …) so that new pages can be inserted without renumbering.
- `aliases` paths must begin with `/` and be site-relative.
- Always include the `<!-- This file is under the copyright of Axoflow, and licensed under Apache License 2.0, except for using the Axoflow and AxoSyslog trademarks. -->` comment 
directly under the frontmatter when creating a new file.
