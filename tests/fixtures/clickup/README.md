# Sanitized ClickUp Fixtures

These fixtures model real ClickUp response shapes without preserving firm,
client, matter, court, contact, email, file, or URL data.

Rules for adding fixtures:

- Keep IDs synthetic (`task_fixture_1`, `comment_fixture_1`, etc.).
- Use placeholder names only (`Example User`, `Example Team`, `Sample Task`).
- Do not include real task names, client names, matter names, emails, URLs,
  phone numbers, addresses, court captions, attachment titles, or transcript
  text.
- Preserve structural fields that have caused bugs: `comment_text`, rich
  `comment` blocks, nested `user`, `status`, `list`, `space`, `parent`, and
  `group_assignees`.
- If a fixture comes from live data, sanitize it before committing and keep the
  original out of the repository.
