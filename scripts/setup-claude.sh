#!/usr/bin/env bash
# Sets up shared Claude Code configuration for a project using docsy-axoflow.
# Run from the project root after adding docsy-axoflow as a submodule at
# themes/docsy-axoflow/.
#
# Usage: bash themes/docsy-axoflow/scripts/setup-claude.sh

set -euo pipefail

SUBMODULE="themes/docsy-axoflow"
CLAUDE_DIR=".claude"

if [ ! -d "$SUBMODULE/.claude" ]; then
    echo "Error: $SUBMODULE/.claude not found. Is the submodule checked out?"
    exit 1
fi

mkdir -p "$CLAUDE_DIR/commands" "$CLAUDE_DIR/docs" "$CLAUDE_DIR/skills"

COMMANDS=(move-page review-page new-page sync-chrome)
DOCS=(style-guide shortcodes frontmatter new-section)
SKILLS=(chrome-parity)

for cmd in "${COMMANDS[@]}"; do
    target="../../$SUBMODULE/.claude/commands/$cmd.md"
    link="$CLAUDE_DIR/commands/$cmd.md"
    ln -sf "$target" "$link"
    echo "  linked $link"
done

for doc in "${DOCS[@]}"; do
    target="../../$SUBMODULE/.claude/docs/$doc.md"
    link="$CLAUDE_DIR/docs/$doc.md"
    ln -sf "$target" "$link"
    echo "  linked $link"
done

# A skill is a directory (SKILL.md plus whatever it carries), so `-n`: without
# it, re-running would drop the link inside the directory it already points at.
for skill in "${SKILLS[@]}"; do
    target="../../$SUBMODULE/.claude/skills/$skill"
    link="$CLAUDE_DIR/skills/$skill"
    ln -sfn "$target" "$link"
    echo "  linked $link"
done

echo ""
echo "Done. Shared Claude config symlinked from $SUBMODULE."
echo "Add project-specific files to $CLAUDE_DIR/docs/ (e.g. style-guide.md)."
echo "Commit .claude/ to version-control the setup."
