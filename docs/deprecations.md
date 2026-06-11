# Deprecation Policy

Starting with v1.0, everything exported from `cupt.__init__` and every documented
CLI command/flag is covered by SemVer.

- Additive changes are allowed in any minor release.
- Deprecated CLI flags emit a warning for at least one minor release before
  removal.
- Deprecated Python APIs remain available until the next major release unless a
  security issue requires faster removal.
- JSON output for read commands is additive within 1.x. Existing keys keep their
  meaning and type unless a new schema version is documented.
