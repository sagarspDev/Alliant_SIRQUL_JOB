"""Reusable HTTP client for Fleetlytics API calls."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Mapping, MutableMapping

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .logger import get_logger
from .config import AppConfig

DEFAULT_TIMEOUT_SECONDS = 30.0


class FleetlyticsAPIError(RuntimeError):
    """Raised when an API request returns an unexpected response."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass(slots=True)
class HTTPClient:
    """Thin HTTP helper with retries and structured logging."""

    base_url: str
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    retries: int = 3
    backoff_factor: float = 0.5
    session: Session | None = None
    _logger: logging.Logger = field(init=False, repr=False)
    _session: Session = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._logger = get_logger(self.__class__.__module__)
        self._session = self.session or requests.Session()
        retry = Retry(
            total=self.retries,
            connect=self.retries,
            read=self.retries,
            status=self.retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def get(
        self,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute a GET request."""

        return self._request("GET", path, headers=headers, params=params, timeout=timeout)

    def post_json(
        self,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute a POST request with a JSON body."""

        return self._request(
            "POST",
            path,
            headers=headers,
            params=params,
            json_body=json_body,
            timeout=timeout,
        )

    def post_form(
        self,
        path: str,
        *,
        form_data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute a POST request with form-encoded data."""

        return self._request(
            "POST",
            path,
            headers=headers,
            params=params,
            data=form_data,
            timeout=timeout,
        )

    def post_multipart(
        self,
        path: str,
        *,
        form_data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Execute a POST request as multipart/form-data.

        Requests uses the multipart encoder when `files` is provided, even if
        the values are simple text fields.
        """

        multipart_data = None
        if form_data is not None:
            multipart_data = {key: (None, str(value)) for key, value in form_data.items()}

        return self._request(
            "POST",
            path,
            headers=headers,
            params=params,
            files=multipart_data,
            timeout=timeout,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
        files: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        url = self._build_url(path)
        request_headers: MutableMapping[str, str] = dict(headers or {})
        start = time.perf_counter()

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=request_headers,
                params=params,
                data=data,
                json=json_body,
                files=files,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._logger.error(
                "%s %s failed after %.2fms: %s",
                method,
                url,
                elapsed_ms,
                exc,
            )
            raise FleetlyticsAPIError(f"{method} {url} failed: {exc}") from exc

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._log_response(response, method, url, elapsed_ms)
        self._raise_for_status(response, method, url)
        return self._decode_response(response)

    def _build_url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _log_response(self, response: Response, method: str, url: str, elapsed_ms: float) -> None:
        self._logger.info(
            "%s %s -> %s in %.2fms",
            method,
            url,
            response.status_code,
            elapsed_ms,
        )
        if self._logger.isEnabledFor(logging.DEBUG):
            body = self._truncate(response.text)
            self._logger.debug("%s %s response body: %s", method, url, body)

    def _raise_for_status(self, response: Response, method: str, url: str) -> None:
        if 200 <= response.status_code < 300:
            return

        body = self._truncate(response.text)
        raise FleetlyticsAPIError(
            f"{method} {url} returned HTTP {response.status_code}",
            status_code=response.status_code,
            body=body,
        )

    def _decode_response(self, response: Response) -> Any:
        if not response.content:
            return None

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type.lower():
            return response.json()

        try:
            return response.json()
        except ValueError:
            return response.text

    def _truncate(self, body: str, limit: int = 2000) -> str:
        body = body.strip()
        if len(body) <= limit:
            return body
        return body[:limit] + "...[truncated]"


def build_http_client(*, base_url: str, config: AppConfig) -> HTTPClient:
    """Build an HTTP client from validated application settings."""

    return HTTPClient(
        base_url=base_url,
        timeout=config.http_timeout_seconds,
        retries=config.http_retry_count,
        backoff_factor=config.http_backoff_factor,
    )
