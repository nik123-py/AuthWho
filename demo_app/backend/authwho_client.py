"""Server-to-server client for the AuthWho collector (``docs/interfaces.md`` sections 4 and 11).

Every request carries the ``X-AuthWho-App-Key`` header. The HTTP client is
injectable so tests can use ``httpx.MockTransport``. Nothing in this module
logs request or response bodies, because stream keys pass through it.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

APP_KEY_HEADER = "X-AuthWho-App-Key"


class CollectorUnavailable(Exception):
    """The collector could not be reached or answered with an unexpected status."""


class CollectorNoConsent(CollectorUnavailable):
    """The collector has no consent row for the user (409 ``no_consent``)."""


class CollectorClient:
    def __init__(self, http: httpx.Client, base_url: str, api_key: str):
        self._http = http
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _request(
        self, method: str, path: str, expected: tuple[int, ...], json: dict | None = None
    ) -> httpx.Response:
        try:
            response = self._http.request(
                method,
                f"{self._base_url}{path}",
                json=json,
                headers={APP_KEY_HEADER: self._api_key},
            )
        except httpx.HTTPError as exc:
            logger.warning("AuthWho collector unreachable: %s %s (%s)", method, path, type(exc).__name__)
            raise CollectorUnavailable from exc
        if response.status_code in expected:
            return response
        if response.status_code == 409 and _error_code(response) == "no_consent":
            raise CollectorNoConsent
        logger.warning("AuthWho collector returned %s for %s %s", response.status_code, method, path)
        raise CollectorUnavailable

    def put_user(self, user_id: str, body: dict) -> None:
        self._request("PUT", f"/v1/users/{user_id}", (200,), json=body)

    def delete_user(self, user_id: str) -> None:
        """Delete the user in AuthWho. A 404 means it is already gone, which counts as done."""
        self._request("DELETE", f"/v1/users/{user_id}", (204, 404))

    def create_session(self, user_id: str, app_id: str, role: str) -> str:
        body = {"user_id": user_id, "app_id": app_id, "role": role}
        return self._request("POST", "/v1/sessions", (201,), json=body).json()["session_id"]

    def create_stream(self, session_id: str) -> dict:
        return self._request("POST", f"/v1/sessions/{session_id}/streams", (201,)).json()

    def end_session(self, session_id: str, reason: str) -> None:
        self._request("POST", f"/v1/sessions/{session_id}/end", (200,), json={"reason": reason})


def _error_code(response: httpx.Response) -> str | None:
    try:
        return response.json().get("error")
    except ValueError:
        return None
