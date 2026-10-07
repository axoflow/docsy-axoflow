# Sources and inspiration

This skill was written from scratch in September 2026, after a review of
existing Diátaxis and information-architecture skills. No text was copied
from them, so their licenses (several are CC BY-SA 4.0) don't apply. This
file records what each one contributed, so you know where the ideas came
from when you change the skill.

## Framework

- [Diátaxis](https://diataxis.fr) by Daniele Procida: the four page types,
  and the advice to improve docs one page at a time instead of reorganizing
  everything into four top-level folders.

## Skills we borrowed ideas from

- [keithpatton/diataxis-agent-skill](https://github.com/keithpatton/diataxis-agent-skill)
  (CC BY-SA 4.0): the classification decision tree (`compass.md`), and
  mixed-page anti-patterns with detection signals and high/medium/low
  confidence levels. Basis for `references/diataxis.md`.
- [anivar/developer-docs-framework](https://github.com/anivar/developer-docs-framework)
  (MIT): inventory first, then classify and find gaps; the cross-link
  pattern (prerequisites, next steps, related); and the adoption funnel,
  adapted here as the reader-journey stages in
  `references/structure-checks.md`. Automated as `scripts/ia_inventory.py`.
  Its "two levels max" and "organize by type, not by component" rules were
  deliberately rejected; see the Axoflow ground rules in `SKILL.md`.
- [travcunn/diataxis-skill](https://github.com/travcunn/diataxis-skill)
  (CC BY-SA 4.0): ships the full diataxis.fr text as Markdown. Used as
  grounding while writing the classification guide.
- [neo4j-labs/agent-memory `docs-diataxis`](https://github.com/neo4j-labs/agent-memory/blob/main/.claude/skills/docs-diataxis/SKILL.md):
  the model for the skill's overall shape. It's written for one repo and
  ties the page types to real folders, nav edits, and a lint step, the way
  this skill ties them to `/move-page`, `/new-page`, `/review-page`, and
  `/lint`.
- [jrjsmrtn/diataxis-skills](https://github.com/jrjsmrtn/diataxis-skills):
  its audit → plan → convert → create split shaped the
  scope → inventory → classify → assess → report → act workflow.

- [trogera/diataxisSkills `docs-reorg`](https://github.com/trogera/diataxisSkills)
  (MIT), added in October 2026: the verb-mood rule (declarative step
  results aren't mixing), "you will" isn't a tutorial signal, the
  two-signal threshold, the mid-task or waiting-room test, and asking the
  author (all in `references/diataxis.md`). From its
  [case study](https://github.com/trogera/diataxisSkills/blob/main/case-study/docs-reorg-systemA.md):
  URL-preserving changes before moves, and the per-section explanation
  gap (both in `SKILL.md`). Its "way-finding" type (landing pages hold
  links only) and its typed `how-to/`, `reference/` folders were rejected:
  they conflict with the Axoflow ground rules.

## Reviewed, not used

- [aj-geddes/useful-ai-prompts `information-architecture`](https://github.com/aj-geddes/useful-ai-prompts/tree/main/skills/information-architecture):
  a generic UX/e-commerce template (card sorting, tree testing) that an
  agent can't run on a docs repo. Reviewing it started this work.
- [yuusakuri/diataxis-skill](https://github.com/yuusakuri/diataxis-skill):
  claims an `audit_docs.py` that flags mixed pages; couldn't confirm how it
  works.
- Variations on the same idea:
  [pfeff/claude-skills](https://github.com/pfeff/claude-skills/blob/main/skills/diataxis/SKILL.md),
  [joshuadavidthomas/agent-skills](https://github.com/joshuadavidthomas/agent-skills),
  [rlespinasse/agent-skills](https://github.com/rlespinasse/agent-skills),
  [github/awesome-copilot `documentation-writer`](https://github.com/github/awesome-copilot/blob/main/skills/documentation-writer/SKILL.md).

## Background reading

- [Fern: information architecture best practices for documentation](https://buildwithfern.com/post/information-architecture-best-practices-documentation)
- [GitBook: documentation structure tips](https://gitbook.com/docs/guides/docs-best-practices/documentation-structure-tips)
- [Tom Johnson: design principles for doc navigation](https://idratherbewriting.com/files/doc-navigation-wtd/design-principles-for-doc-navigation/)
