#!/bin/bash
set -euo pipefail

# Resolve the cached last30days skill's SKILL.md, if the plugin cache is present.
#
# Two cache layouts ship in the wild — nested ({version}/skills/last30days/SKILL.md)
# and flat ({version}/SKILL.md). Resolve to whichever shape actually exists, and
# pick the highest version directory when multiple are cached.
CLAUDE_CACHE_LATEST=$(find "$HOME/.claude/plugins/cache/last30days-skill/last30days" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -V | tail -1) || true

CLAUDE_CACHE_SKILL_MD=""
if [ -n "$CLAUDE_CACHE_LATEST" ]; then
  if [ -f "$CLAUDE_CACHE_LATEST/skills/last30days/SKILL.md" ]; then
    CLAUDE_CACHE_SKILL_MD="$CLAUDE_CACHE_LATEST/skills/last30days/SKILL.md"
  elif [ -f "$CLAUDE_CACHE_LATEST/SKILL.md" ]; then
    CLAUDE_CACHE_SKILL_MD="$CLAUDE_CACHE_LATEST/SKILL.md"
  fi
fi

if [ -n "$CLAUDE_CACHE_SKILL_MD" ]; then
  echo "export CLAUDE_CACHE_SKILL_MD=\"$CLAUDE_CACHE_SKILL_MD\"" >> "$CLAUDE_ENV_FILE"
fi
