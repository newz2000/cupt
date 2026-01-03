# CUPT - ClickUp Task Management CLI

A comprehensive command-line interface for ClickUp task management.

## Features

- Task listing with filtering and sorting
- Time tracking with start/stop/manual entry
- Notes and comments management
- Task completion tracking
- OAuth authentication
- Offline capability with caching

## Installation

```bash
pip install cupt
```

## Quick Start

1. Authenticate with ClickUp:
```bash
cupt auth
```

2. List your tasks:
```bash
cupt list --overdue
```

3. Start tracking time on a task:
```bash
cupt time start abc123
```

## Commands

### Authentication
- `cupt auth` - Authenticate with ClickUp using OAuth
- `cupt logout` - Clear authentication data

### Task Management
- `cupt list` - List tasks with optional filters
- `cupt show <task-id>` - Show task details
- `cupt done <task-id>` - Mark task as complete

### Time Tracking
- `cupt time start <task-id>` - Start timer
- `cupt time stop` - Stop timer
- `cupt time status` - Show current timer status
- `cupt time add <task-id> <duration> [-m "message"]` - Add manual time

### Notes Management
- `cupt note add <task-id> "Note text"` - Add note to task
- `cupt note list <task-id>` - List task notes

## Examples

```bash
# List overdue tasks (limit 5)
cupt list --overdue -n 5

# Show task details with notes
cupt show abc123 --notes

# Add 2 hours 30 minutes of time to a task
cupt time add abc123 2h30m -m "API development work"

# Mark task complete with note
cupt done abc123 --note "Completed after client review"
```

## Configuration

CUPT stores configuration in `~/.cupt/config.yaml`. You can customize:

- Team ID and default list ID
- Cache settings
- Authentication tokens

## License

MIT License