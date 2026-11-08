"""Resetting the library, which is not the same thing as resetting the infrastructure.

Nothing here touches Docker volumes or the models in Ollama. `docker compose down -v` would
delete both, and is never the way to reset a library.
"""

from app.errors import ConfirmationRequiredError
from app.services.library_data import LibraryData
from app.services.recovery_service import RESET_EVERYTHING, RESET_INDEX, LibraryGuard
from app.utils.logging import get_logger, operation

logger = get_logger("services.reset")

CONFIRM_RESET_INDEX = "RESET INDEX"
CONFIRM_RESET_EVERYTHING = "DELETE EVERYTHING"


class ResetService:
    def __init__(self, data: LibraryData, guard: LibraryGuard) -> None:
        self._data = data
        self._guard = guard

    def reset_index(self, confirmation: str) -> None:
        """Delete everything derived, keeping the original documents.

        The catalog is cleared too, and the library is empty afterwards. reindex_all rebuilds it
        from the originals, without uploading anything again.

        Args:
            confirmation: has to be CONFIRM_RESET_INDEX.

        Raises:
            ConfirmationRequiredError: the confirmation doesn't match.
            LibraryBusyError: an operation is running, and this rejects it rather than stopping it.
        """
        self._reset(RESET_INDEX, confirmation, CONFIRM_RESET_INDEX, keep_originals=True)

    def reset_everything(self, confirmation: str) -> None:
        """Delete the whole library, the original documents included.

        Args:
            confirmation: has to be CONFIRM_RESET_EVERYTHING.

        Raises:
            ConfirmationRequiredError: the confirmation doesn't match.
            LibraryBusyError: an operation is running, and this rejects it rather than stopping it.
        """
        self._reset(RESET_EVERYTHING, confirmation, CONFIRM_RESET_EVERYTHING, keep_originals=False)

    def _reset(self, kind: str, confirmation: str, expected: str, keep_originals: bool) -> None:
        if confirmation != expected:
            raise ConfirmationRequiredError(f"This needs the exact confirmation: {expected}")
        with self._guard.exclusive(), operation(logger, kind):
            journal = self._data.catalog.begin_operation(kind)
            self._data.clear(keep_originals=keep_originals)
            self._data.catalog.end_operation(journal)
