"""
civitai — Python client for the Civitai API.

Quick start:
    from civitai import Civitai

    civ = Civitai(api_token="your_token")
    report = civ.bounties.full_report(12345)
"""

from .client import CivitaiClient, CivitaiError
from .bounties import BountyAPI, BountyStats, BountyEntry, Benefactor


class Civitai:
    """Entry point for all Civitai API interactions."""

    def __init__(self, api_token: str | None = None, domain: str = "red"):
        self._client = CivitaiClient(api_token=api_token, domain=domain)
        self.bounties = BountyAPI(self._client)


__all__ = [
    "Civitai",
    "CivitaiClient",
    "CivitaiError",
    "BountyAPI",
    "BountyStats",
    "BountyEntry",
    "Benefactor",
]
