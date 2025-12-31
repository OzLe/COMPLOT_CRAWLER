"""
Base fetcher utilities for async HTTP operations.

Provides common URL building and HTTP request patterns.
"""

import asyncio
from typing import Optional, Dict, Any

import aiohttp

from src.config import CityConfig, DEFAULT_SETTINGS


# Default API configuration
API_BASE = DEFAULT_SETTINGS.api_base
REQUEST_TIMEOUT = DEFAULT_SETTINGS.request_timeout
MAX_RETRIES = DEFAULT_SETTINGS.max_retries
RETRY_DELAY = DEFAULT_SETTINGS.retry_delay
MAX_CONCURRENT = DEFAULT_SETTINGS.max_concurrent


def build_url(program: str, **params) -> str:
    """
    Build API URL with parameters.

    Args:
        program: API program name (e.g., 'GetTikimByAddress', 'GetTikFile')
        **params: URL parameters

    Returns:
        Complete URL string
    """
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{API_BASE}?appname=cixpa&prgname={program}&{param_str}"


class BaseFetcher:
    """Base class for async HTTP fetchers."""

    def __init__(self, config: CityConfig):
        """
        Initialize fetcher with city configuration.

        Args:
            config: City configuration for API calls
        """
        self.config = config
        self.timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    def build_url(self, program: str, **params) -> str:
        """Build API URL with parameters."""
        return build_url(program, **params)

    def get_headers(self) -> Dict[str, str]:
        """Get default HTTP headers."""
        return {
            "Referer": self.config.base_url,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

    async def fetch_with_retry(
        self,
        session: aiohttp.ClientSession,
        url: str,
        retry: int = 0
    ) -> Optional[str]:
        """
        Fetch URL with exponential backoff retry.

        Args:
            session: aiohttp session
            url: URL to fetch
            retry: Current retry count

        Returns:
            Response text or None on failure
        """
        try:
            async with session.get(
                url,
                headers=self.get_headers(),
                timeout=self.timeout
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None

        except asyncio.TimeoutError:
            if retry < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                return await self.fetch_with_retry(session, url, retry + 1)
            return None

        except Exception:
            if retry < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                return await self.fetch_with_retry(session, url, retry + 1)
            return None

    @staticmethod
    def create_connector() -> aiohttp.TCPConnector:
        """Create a TCP connector with appropriate limits."""
        return aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    @staticmethod
    def create_semaphore(limit: int = None) -> asyncio.Semaphore:
        """Create a semaphore for concurrency control."""
        return asyncio.Semaphore(limit or MAX_CONCURRENT)
