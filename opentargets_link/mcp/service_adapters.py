"""Process-wide dependency-injection registry for the Open Targets service.

The running server registers a concrete :class:`OpenTargetsService` at startup; tests inject
one over a respx-mocked client. An unregistered service is an ``internal`` error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentargets_link.exceptions import InternalError

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from opentargets_link.service import OpenTargetsService

_service: OpenTargetsService | None = None


def get_opentargets_service() -> OpenTargetsService:
    """Return the registered :class:`OpenTargetsService` or raise ``InternalError``."""
    if _service is None:
        raise InternalError(
            "Open Targets service is not initialised; the server must register it at startup.",
            recovery_action="switch_tool",
        )
    return _service


def set_opentargets_service(service: OpenTargetsService | None) -> None:
    """Register (or clear) the process-wide service. Used by the server and tests."""
    global _service
    _service = service
