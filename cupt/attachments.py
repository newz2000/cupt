import os

import click
import requests

from cupt.context import get_client_context
from cupt.utils import print_error, print_success, print_warning


def _human_size(n_bytes):
    if not n_bytes:
        return "-"
    n = float(n_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024
    return f"{n:.1f}GB"


def _resolve(attachments, selector):
    """Find an attachment by 1-based index or substring of title."""
    if selector.isdigit():
        idx = int(selector) - 1
        if 0 <= idx < len(attachments):
            return attachments[idx]
        return None
    needle = selector.lower()
    matches = [a for a in attachments if needle in (a.get("title", "")).lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise click.ClickException(
            f"'{selector}' matches {len(matches)} attachments — be more specific or use an index"
        )
    return None


@click.group(name="attach")
def attach_group():
    """List, download, and upload task attachments"""
    pass


@attach_group.command("list")
@click.argument("task_id")
def list_attachments(task_id):
    """List attachments on a task"""
    _, client, _ = get_client_context(need_team=False)
    if not client:
        return

    try:
        task = client.get_task(task_id)
    except Exception as e:
        print_error(f"Failed to fetch task: {e}")
        return

    attachments = task.get("attachments") or []
    if not attachments:
        print_warning(f"No attachments on {task_id}.")
        return

    click.echo(f"\n{'#':<4} {'Size':<10} {'Name'}")
    click.echo("-" * 60)
    for i, a in enumerate(attachments, start=1):
        click.echo(
            f"{i:<4} {_human_size(a.get('size')):<10} {a.get('title', '(untitled)')}"
        )


@attach_group.command("get")
@click.argument("task_id")
@click.argument("selector")
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    help="Save path (default: original filename in current dir)",
)
def get_attachment(task_id, selector, output):
    """Download an attachment by 1-based index or filename substring"""
    _, client, _ = get_client_context(need_team=False)
    if not client:
        return

    try:
        task = client.get_task(task_id)
    except Exception as e:
        print_error(f"Failed to fetch task: {e}")
        return

    attachments = task.get("attachments") or []
    if not attachments:
        print_warning(f"No attachments on {task_id}.")
        return

    target = _resolve(attachments, selector)
    if not target:
        print_error(f"No attachment matches '{selector}'.")
        return

    url = target.get("url")
    if not url:
        print_error("Attachment has no download URL.")
        return

    # No auth header — these are pre-signed S3 URLs; sending Authorization
    # can invalidate the signature.
    try:
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print_error(f"Download failed: {e}")
        return

    out_path = output or target.get("title") or "attachment.bin"
    try:
        with open(out_path, "wb") as fh:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    fh.write(chunk)
    except OSError as e:
        print_error(f"Could not write to {out_path}: {e}")
        return

    print_success(f"Downloaded {target.get('title')} -> {out_path}")


@attach_group.command("add")
@click.argument("task_id")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--name", help="Override the filename stored on ClickUp")
def add_attachment(task_id, file_path, name):
    """Upload a file as a task attachment"""
    _, client, _ = get_client_context(need_team=False)
    if not client:
        return

    try:
        result = client.upload_task_attachment(task_id, file_path, name)
        title = result.get("title") or name or os.path.basename(file_path)
        print_success(f"Attached '{title}' to {task_id}")
    except Exception as e:
        print_error(f"Failed to upload attachment: {e}")
