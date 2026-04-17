# Adding a New Documentation Section or Page

## Adding a single page

1. Create `content/<parent-section>/my-page.md`.
2. Add front matter with at minimum `title` and `weight`.
3. Choose a `weight` that fits between existing siblings (use multiples of 10).
4. Verify the page appears in `hugo server` at the expected URL.

## Adding a new section (directory)

1. Create the directory: `content/<new-section>/`
2. Create `content/<new-section>/_index.md` with front matter:
   ```yaml
   ---
   title: "My New Section"
   weight: 50
   bookCollapseSection: true
   ---
   <!-- This file is under the copyright of Axoflow, and licensed under Apache License 2.0, except for using the Axoflow and AxoSyslog trademarks. -->
   ```
3. Add child pages inside the directory, each with their own front matter.
4. Add the section's `weight` so it appears in the correct sidebar position
   relative to sibling sections.

## Checklist before committing

- [ ] `hugo server` builds without errors or warnings.
- [ ] Page appears in the sidebar at the correct location.
- [ ] All internal links resolve (no 404s in the browser console).
- [ ] Front matter has `title` and `weight`.
- [ ] Headings use sentence case.
- [ ] Code blocks have language identifiers.
- [ ] Any renamed or moved page has an `aliases` entry for the old URL.

## Page bundle (page with images or attachments)

To attach images to a page, convert it to a page bundle:

```
content/my-section/
└── my-page/
    ├── index.md       ← the page content (note: index.md, not _index.md)
    ├── diagram.svg
    └── screenshot.png
```

Reference images with a relative path: `![Alt text](diagram.svg)`.
