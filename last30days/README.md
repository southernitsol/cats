# last30days

Reference copy of the manifest for the [`last30days-skill`](https://github.com/mvanhorn/last30days-skill)
Claude Code plugin (by Matt Van Horn), which this repo's SessionStart hook
(`.claude/hooks/session-start.sh`) resolves from the local plugin cache.

- `plugin.json` — the upstream plugin manifest
- `marketplace.json` — the upstream `.claude-plugin/marketplace.json`, the
  marketplace listing that makes the plugin installable via
  `/plugin marketplace add mvanhorn/last30days-skill`

Both are kept here for reference alongside the cache-layout-resolution logic.
