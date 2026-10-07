# Classifying pages with Diátaxis

Diátaxis (<https://diataxis.fr>, by Daniele Procida) sorts documentation by the
reader's need at the moment they open the page. This file is a working guide
for classifying pages in Axoflow docs, written for this skill. Read the
original when a case is hard.

## Contents

- [The compass](#the-compass)
- [The four types](#the-four-types)
- [Mixed-page patterns](#mixed-page-patterns)
- [Confidence](#confidence)
- [Patterns in Axoflow docs](#patterns-in-axoflow-docs)

## The compass

Ask two questions about the page's content:

1. Does it tell the reader to **do** something, or does it give them
   **knowledge**?
2. Is the reader **studying** (building skill for later) or **working**
   (applying skill right now)?

| | Working (at work, has a goal) | Studying (learning) |
|---|---|---|
| **Doing** (action) | How-to guide | Tutorial |
| **Knowing** (cognition) | Reference | Explanation |

If you can't decide, ask "what would the reader be annoyed to find here?". A
reader working through a how-to is annoyed by background theory. A reader
looking up an option is annoyed by steps. The annoyance points at the part
that belongs elsewhere.

For reference versus explanation, ask where the reader would use it: in the
middle of a task (reference), or in a waiting room, away from the keyboard
(explanation).

### Verb mood

Instructions are imperative ("Run the installer"); facts are declarative
("The cache refreshes every 30 seconds"). A shift in mood is a cheap way to
spot mixed pages, with one exception:

- **Declarative sentences inside steps are fine.** Step results ("The
  service restarts.") and short notes that belong to a step are part of a
  how-to. Don't count them as mixing.
- **Declarative paragraphs outside steps are a signal.** Prose before,
  between, or after the steps that explains how something works is
  explanation inside a procedure.

## The four types

### Tutorial: learning by doing

A lesson. The reader doesn't know enough to choose their own path yet, so the
page chooses for them and guarantees they succeed.

- Signals: an upfront learning goal ("In this tutorial, you build…"), a
  single fixed path, a concrete end result ("you now have a relay
  forwarding logs to…"), frequent "you should see…" checks.
- Not a signal: "you will" scattered through steps or results ("You will
  need to restart the service"). That's informal style, common on how-tos.
  Only a deliberate goal statement near the top counts. Steps without one
  make a how-to, however the steps are written.
- Good: minimal explanation (one sentence, then a link), no options or
  alternatives, every step works on a fresh machine.
- In Axoflow docs: rare. `quickstart/` pages are the closest. Many "getting
  started" pages are really how-tos for people who already know syslog.

### How-to guide: getting a task done

Directions for a competent reader with a specific goal.

- Signals: title names a task ("Send logs to Splunk", "Configure TLS on the
  server"), prerequisites, numbered steps, "To X, complete the following
  steps", ends when the goal is reached.
- Good: starts from the reader's situation, covers the real-world variants
  as short branches, links to reference for every option it uses instead of
  explaining it.
- Not a how-to: a numbered list that describes what the product does
  internally (for example, "the route of a message"). That's explanation
  written as a list.

### Reference: looking something up

Accurate, complete, and neutral description of the machinery.

- Signals: `## option-name()` headings, `Type:` / `Default:` lines, tables of
  fields, macros, metrics, or CLI flags, man pages, a structure that mirrors
  the product (one entry per option).
- Good: complete (every option, not just common ones), consistent entry
  shape, short examples for each entry, no steps, no opinions.
- In Axoflow docs: the bulk of the content. Options pages, `filterx`
  function and operator references, `app-man-syslog-ng/`, and metrics lists.

### Explanation: understanding

Discussion that builds the reader's mental model: why it works this way,
how the parts relate, what the trade-offs are.

- Signals: "concepts" in the path or title, "how X works", "why",
  comparisons, design rationale, history, diagrams of data flow.
- Good: can be read away from the keyboard, makes connections to other
  topics, may hold opinions.
- In Axoflow docs: `chapter-concepts/`, `concepts/`, `architecture/`, and
  the intro parts of feature landing pages (disk buffer, flow control,
  multithreading).

## Mixed-page patterns

These are the patterns worth reporting. For each, the fix is to keep the
page's main type and move the rest out, with a link back.

### Tutorial or how-to that stops to explain

- Detect: long paragraphs between steps about why or how something works;
  "Understanding X" or "About X" headings inside a procedure.
- Fix: keep one sentence of context in place, move the rest to an
  explanation page (or the component's landing page), and link to it.

### How-to that teaches from zero

- Detect: a task page that also explains basic concepts ("A source is…"),
  or covers every possible option instead of the task.
- Fix: cut to the task. Link to the concept page and the options reference.

### Reference with embedded procedures

- Detect: an options page with numbered steps, or an entry that says "first
  do A, then B" across several options.
- Fix: keep the option entries. Move the procedure to a how-to under the
  same component, and link each involved option to it.

### Reference that argues

- Detect: option entries with recommendations, warnings about design
  choices, or long "why" discussion.
- Fix: keep short warnings (`alert` shortcode) that prevent data loss or
  outages; they belong at the point of use. Move design discussion to
  explanation.

### Explanation buried in a how-to or reference

- Detect: the best description of how a feature works lives in the middle
  of a how-to or options page, and other pages link to that anchor.
- Fix: promote it to its own explanation page, or into the component's
  landing page, and update the links. This often also fixes
  `no_inbound_links` for the new page.

### Landing page that's only a list

- Detect: a section `_index.md` with a sentence and the auto-generated child
  list.
- Fix: give it a short explanation of what the section covers and when to
  use which child. This is the most valuable fix on wide sections.

## Confidence

| Confidence | Use when |
|---|---|
| High | Several strong signals agree, and the page has one clear purpose. |
| Medium | The main type is clear, but part of the page could be another type, or the page is short. |
| Low | Weak or conflicting signals. Say what you'd need to know (for example, "is this meant as a first-run guide?"), and don't propose a split on low confidence. |

A type counts only when **two or more** of its signals are present: one
signal is noise, two is a pattern. The same applies to a second type on a
mixed page. One explanatory paragraph doesn't make a how-to mixed; a
recurring pattern does.

When confidence stays low, ask the user. The person who wrote or requested
the page usually knows what it was meant to be, even if it didn't turn out
that way.

## Patterns in Axoflow docs

These patterns are deliberate. Classify them as noted and don't report them as
problems:

- **Component landing page plus options page** (for example,
  `chapter-sources/<driver>/_index.md` and `.../<driver>-options/`). The
  landing page is short: what it does, minimal config example, sometimes
  prerequisites. Classify the landing as how-to/reference (a "quick use"
  entry), the options page as reference. Report only if the landing page is
  missing its example, or the options page holds procedures.
- **Shared option descriptions as snippets.** Options that several drivers
  share come from `content/headless/chunk/option-*.md`. Duplication across
  options pages is by design. Report it only when two copies of the same
  option drift apart instead of using the snippet.
- **"Example" sections in reference.** A short config example per option or
  per driver is part of good reference, not a mixed page.
- **What's new / release notes** are their own type (news). Don't classify
  them as tutorials or reference, and don't report their links as structure
  problems.
- **Man pages** (`app-man-*`) are reference, and their structure is
  generated from the upstream source. Don't propose restructuring them.
