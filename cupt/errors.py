"""Exit codes for the agent contract in ``docs/agent-contract.md``.

Commands used to print an error and ``return``, which exits 0. Scripts and
agents then could not tell "no results" from "your token expired" — the whole
point of the contract. Every command error path goes through :func:`fail` so
the documented code is what the shell actually sees.

Note that Click itself exits 2 for its own usage errors (unknown flag, missing
argument), which overlaps code 2 here. Both mean "you cannot proceed as asked";
the message on stderr distinguishes them.
"""

from typing import NoReturn, Optional

import click

from cupt.exceptions import APIError, AuthError, ConfigError
from cupt.resolver import IDResolutionError
from cupt.utils import print_error

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_AUTH = 2
EXIT_NOT_FOUND = 3
EXIT_INVALID_INPUT = 4
EXIT_API = 5


def exit_code_for(exc: Optional[BaseException]) -> int:
    """Map an exception to its documented exit code."""
    if isinstance(exc, click.exceptions.Exit):
        return exc.exit_code
    if isinstance(exc, (AuthError, ConfigError)):
        return EXIT_AUTH
    if isinstance(exc, IDResolutionError):
        return EXIT_NOT_FOUND if exc.not_found else EXIT_INVALID_INPUT
    if isinstance(exc, APIError):
        # ClickUp reports a missing object as a 404; everything else the API
        # can do to us is a transport or server failure.
        return EXIT_NOT_FOUND if "HTTP 404" in str(exc) else EXIT_API
    if exc is None:
        return EXIT_FAILURE
    return EXIT_FAILURE


def fail(
    message: str,
    exc: Optional[BaseException] = None,
    code: Optional[int] = None,
) -> NoReturn:
    """Print ``message`` to stderr and exit with the contract code.

    Pass ``exc`` to derive the code from the exception, or ``code`` to state it
    outright (for refusals that aren't exceptions, such as a command that needs
    a prompt in a non-interactive session).
    """
    # click.exceptions.Exit subclasses Exception, so a fail() raised inside a
    # command's own `except Exception` block arrives back here wrapped as `exc`.
    # Re-raise it untouched: the inner call already chose the right code and
    # printed the specific message, and the outer one would bury both.
    if isinstance(exc, click.exceptions.Exit):
        raise exc

    print_error(message)
    raise click.exceptions.Exit(code if code is not None else exit_code_for(exc))
