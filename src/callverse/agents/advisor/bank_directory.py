"""Brazilian bank directory for the advisor's ``validate_bank_code`` tool (external API).

A boleto cannot be reversed: the refund is a bank transfer, so the customer must give
a bank, branch and account (refund policy). The bank code (3-digit COMPE code of the
Central Bank) can be checked against a public list. BrasilAPI serves that list as
JSON, but one request takes 1-5 s, so the list is downloaded once, saved under
``data/external/`` and read from disk afterwards: fast, offline and the same answer in
every run. Only the bank code is looked up; account numbers never leave CallVerse.
"""

# How it works: 1) the first call downloads the bank list from BrasilAPI (a free public API) and saves it as
# JSON in data/external/; 2) later calls read the saved file; 3) lookup("341") returns the bank (Itau) or
# None.
import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from callverse.config import PROJECT_ROOT, load_yaml


class BankDirectoryUnavailable(RuntimeError):
    """No cached list and the API could not be reached."""


def download_banks(url: str, timeout_seconds: float) -> list[dict[str, Any]]:
    """Bank list from BrasilAPI: ``[{"code": 341, "name": ..., "fullName": ..., "ispb": ...}]``."""
    # urllib is Python's built-in HTTP client; the User-Agent header names our app.
    request = urllib.request.Request(url, headers={"User-Agent": "CallVerse/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


@dataclass
class BankDirectory:
    """Bank codes, read from the cache file or downloaded once."""

    url: str
    cache_file: Path
    timeout_seconds: float = 8.0
    # downloader can be replaced by a fake function in the tests (no network needed).
    downloader: Callable[[str, float], list[dict[str, Any]]] = field(default=download_banks, repr=False)
    _banks: dict[str, dict[str, Any]] | None = field(default=None, init=False, repr=False)

    def load(self) -> dict[str, dict[str, Any]]:
        """Code -> bank. Downloads and caches the list on first use."""
        # Already loaded in memory: reuse it.
        if self._banks is not None:
            return self._banks
        # Saved on disk: read it (fast, and works offline).
        if self.cache_file.exists():
            payload = json.loads(self.cache_file.read_text(encoding="utf-8"))
        else:
            # Otherwise download the list once from the API, and save it for next time.
            try:
                raw = self.downloader(self.url, self.timeout_seconds)
            except Exception as error:  # network errors, timeouts, bad JSON
                reason = f"bank list not cached and BrasilAPI unreachable: {error}"
                raise BankDirectoryUnavailable(reason) from error
            payload = {
                "source": self.url,
                "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "banks": [
                    {
                        # Codes are stored as 3-digit text: 1 -> "001".
                        "code": f"{int(bank['code']):03d}",
                        "name": bank.get("name"),
                        "full_name": bank.get("fullName"),
                        "ispb": bank.get("ispb"),
                    }
                    for bank in raw
                    if bank.get("code") is not None
                ],
            }
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        # A dictionary code -> bank, for instant lookups.
        self._banks = {bank["code"]: bank for bank in payload["banks"]}
        return self._banks

    def lookup(self, code: str) -> dict[str, Any] | None:
        """The bank with this 3-digit code, or None."""
        return self.load().get(code)


# lru_cache(maxsize=1): one shared directory for the whole process.
@lru_cache(maxsize=1)
def bank_directory() -> BankDirectory:
    """Directory configured in ``configs/agents.yaml`` (advisor.bank_directory)."""
    raw = load_yaml("agents")["advisor"]["bank_directory"]
    return BankDirectory(
        url=str(raw["url"]),
        cache_file=PROJECT_ROOT / str(raw["cache_file"]),
        timeout_seconds=float(raw["timeout_seconds"]),
    )
