import json
import os
import subprocess
import sys
import uuid
import warnings
from pathlib import Path

import pytest

from cupt.api import ClickUpClient
from cupt.config import ConfigManager
from cupt.services.task_service import TaskService
from cupt.utils import format_comment_text

pytestmark = pytest.mark.live_e2e

ROOT = Path(__file__).resolve().parents[2]


def _require_live_env():
    if os.environ.get("CUPT_LIVE_E2E") != "1":
        pytest.skip("set CUPT_LIVE_E2E=1 to run live ClickUp E2E tests")
    list_id = os.environ.get("CUPT_E2E_LIST_ID")
    if not list_id:
        pytest.skip("set CUPT_E2E_LIST_ID to a safe test ClickUp list")
    return list_id


@pytest.fixture(scope="module")
def live_client():
    _require_live_env()
    config = ConfigManager()
    if not config.is_authenticated():
        pytest.skip("local cupt config is not authenticated")
    token = config.get("auth.access_token")
    if not token:
        pytest.skip("local cupt config has no access token")
    return ClickUpClient(token)


@pytest.fixture
def live_dummy_task(live_client):
    list_id = _require_live_env()
    run_id = uuid.uuid4().hex[:10]
    task_name = f"cupt live e2e dummy {run_id}"
    comment_text = f"cupt live e2e comment {run_id}"

    created = live_client.create_task(
        list_id,
        {
            "name": task_name,
            "description": "Temporary task created by cupt live E2E tests.",
        },
    )
    task_id = created["id"]
    live_client.add_task_comment(task_id, comment_text)

    yield task_id, comment_text

    try:
        TaskService(live_client).complete_task(task_id, note="cupt live e2e cleanup")
    except Exception as exc:
        warnings.warn(
            f"Could not complete live E2E task {task_id}; clean it up manually: {exc}",
            stacklevel=2,
        )


def _run_cli(*args):
    env = os.environ.copy()
    env["CUPT_INTERACTIVE"] = "0"
    return subprocess.run(
        [sys.executable, "-m", "cupt.main", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _assert_success(result):
    assert result.returncode == 0, (
        "stdout:\n" + result.stdout + "\n\nstderr:\n" + result.stderr
    )


def test_live_dummy_task_round_trip(live_dummy_task):
    task_id, comment_text = live_dummy_task

    notes = _run_cli("notes", task_id)
    _assert_success(notes)
    assert comment_text in notes.stdout

    context = _run_cli("context", task_id)
    _assert_success(context)
    assert comment_text in context.stdout

    show_notes = _run_cli("show", task_id, "--notes")
    _assert_success(show_notes)
    assert comment_text in show_notes.stdout

    show_json = _run_cli("show", task_id, "--json")
    _assert_success(show_json)
    show_payload = json.loads(show_json.stdout)
    assert any(
        comment_text in format_comment_text(comment)
        for comment in show_payload["comments"]
    )

    statuses = _run_cli("statuses", task_id, "--json")
    _assert_success(statuses)
    status_payload = json.loads(statuses.stdout)
    assert status_payload["target"]
    assert status_payload["statuses"]

    dry_run = _run_cli("done", task_id, "--dry-run")
    _assert_success(dry_run)
    assert "Would mark task" in (dry_run.stdout + dry_run.stderr)
