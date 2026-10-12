"""Completing consent withdrawals in AuthWho.

A withdrawal stops capture locally at once and sets the durable
``withdrawal_pending`` flag. The AuthWho deletion (DELETE /v1/users/{id}) is
then retried until AuthWho answers 204, or 404 meaning already gone:
on login, GET /api/me and POST /api/consent, and in the background by
``run_retry_loop`` so users who never return are deleted as well.

Logs name users only by their pseudonymous AuthWho user ID, never by username.
"""

import asyncio
import logging
from collections.abc import Callable

from .authwho_client import CollectorClient, CollectorUnavailable
from .store import Store

logger = logging.getLogger(__name__)


def complete_withdrawal(store: Store, collector: CollectorClient, user_id: int, authwho_user_id: str) -> bool:
    """Send the DELETE; clear the flag and return True once AuthWho has confirmed it."""
    try:
        collector.delete_user(authwho_user_id)
    except CollectorUnavailable:
        logger.warning("Withdrawal still pending for AuthWho user %s; will retry", authwho_user_id)
        return False
    store.clear_withdrawal_pending(user_id)
    return True


def retry_pending_withdrawals(
    store: Store, collector: CollectorClient, should_stop: Callable[[], bool] = lambda: False
) -> int:
    """Retry every pending withdrawal once and return how many were completed.

    A failure for one user, of any kind, is logged and never stops the others.
    """
    completed = 0
    for user_id, authwho_user_id in store.pending_withdrawals():
        if should_stop():
            break
        try:
            if complete_withdrawal(store, collector, user_id, authwho_user_id):
                completed += 1
        except Exception:
            logger.exception("Unexpected error retrying withdrawal for AuthWho user %s", authwho_user_id)
    return completed


async def run_retry_loop(
    store: Store, collector: CollectorClient, interval_seconds: float, stop: asyncio.Event
) -> None:
    """Retry at once, then every ``interval_seconds``, until ``stop`` is set.

    Each run happens in a worker thread because the store and the collector
    client are blocking. On shutdown the loop lets an in-flight run finish its
    current user, then exits, so no request is sent after shutdown completes.
    """
    while not stop.is_set():
        try:
            await asyncio.to_thread(retry_pending_withdrawals, store, collector, stop.is_set)
        except Exception:
            logger.exception("Background withdrawal retry run failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
