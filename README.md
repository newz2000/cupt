# CUPT - ClickUp Task Management CLI

A powerful, modular CLI tool for managing ClickUp tasks directly from your terminal.

## Features
- **Task Listing**: View active, overdue, and upcoming tasks with deep paging support.
- **Subtask Support**: Visual nesting (`↳`) and parent task resolution.
- **Hierarchical Context**: `cupt context <id>` shows parents and sibling subtasks.
- **Time Tracking**: Start/stop timers and add manual time entries.
- **Note Management**: Quick comments and note listing.
- **Flexible Auth**: Supports both OAuth and Personal API Tokens.

## Installation

### Local Installation (for development)
```bash
git clone https://github.com/matthewnuzum/cupt.git
cd cupt
pip install -e .
```

### Configuration
```bash
cupt auth
# Follow prompts to authenticate
```

## Usage
- `cupt list`: List your active tasks
- `cupt list --overdue`: Show overdue tasks
- `cupt show <id>`: Show task details
- `cupt context <id>`: Show task parent and siblings
- `cupt done <id>`: Mark task as complete
- `cupt time start <id>`: Start timer
- `cupt time stop`: Stop timer
- `cupt note <id> "Your message"`: Add a note

## Project Structure
- `cupt/`: Package root.
- `cupt/services/`: Core business logic (TaskService, TimeService, NoteService).
- `cupt/api.py`: ClickUp API client wrapper.
- `cupt/main.py`: CLI entry point.
- `tests/`: Comprehensive unit tests using `pytest` and mocks.

## Testing
Run the test suite with coverage:
```bash
pytest --cov=cupt tests/
```