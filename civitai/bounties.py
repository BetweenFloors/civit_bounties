"""Bounty-related API methods."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import CivitaiClient

_CHUNK = 20  # max procedures per tRPC batch request


@dataclass
class BountyStats:
    bounty_id: int
    name: str
    status: str
    currency: str
    unit_amount: int
    entries: int
    benefactors: int
    total_buzz: int
    likes: int
    tracking: int
    comments: int
    starts_at: str
    expires_at: str


@dataclass
class BountyEntry:
    entry_id: int
    user: str
    awarded_buzz: int
    reactions: dict[str, int] = field(default_factory=dict)
    image_count: int = 0


@dataclass
class Benefactor:
    user: str
    unit_amount: int


class BountyAPI:
    def __init__(self, client: "CivitaiClient"):
        self._c = client

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_stats(self, bounty_id: int) -> BountyStats:
        data = self._c._trpc_get("bounty.getById", {"id": bounty_id})
        return self._parse_stats(data)

    def get_entries(self, bounty_id: int) -> list[BountyEntry]:
        entries: list[BountyEntry] = []
        for item in self._get_raw_entries(bounty_id):
            entries.append(self._parse_entry(item))
        return entries

    def get_benefactors(self, bounty_id: int) -> list[Benefactor]:
        items = self._c._trpc_get("bounty.getBenefactors", {"id": bounty_id})
        return [
            Benefactor(
                user=self._username(item.get("user")),
                unit_amount=item.get("unitAmount", 0),
            )
            for item in (items or [])
        ]

    def full_report(self, bounty_id: int) -> dict:
        """
        Fetch all bounty data including per-entry reactions and reactor usernames.
        Makes ~5 HTTP requests for a typical bounty of ~90 entries.
        """
        # 1. Bounty header + benefactors
        stats_raw, benefactors_raw = self._c._trpc_batch_get([
            ("bounty.getById", {"id": bounty_id}),
            ("bounty.getBenefactors", {"id": bounty_id}),
        ])
        stats = self._parse_stats(stats_raw)
        benefactors = [
            Benefactor(
                user=self._username(b.get("user")),
                unit_amount=b.get("unitAmount", 0),
            )
            for b in (benefactors_raw or [])
        ]

        # 2. All entries (basic list, paginated)
        raw_entries = self._get_raw_entries(bounty_id)
        entries = [self._parse_entry(e) for e in raw_entries]

        # 3. Per-entry details with reactions (batched)
        entry_ids = [e["id"] for e in raw_entries]
        entry_details = self._batch_entry_details(entry_ids)

        # 4. Resolve reactor user IDs → usernames
        reactor_ids: set[int] = set()
        for d in entry_details.values():
            for rx in (d.get("reactions") or []):
                reactor_ids.add(rx["userId"])
        user_map = self._resolve_users(reactor_ids) if reactor_ids else {}

        # 5. Merge reactions into raw entries
        for entry in raw_entries:
            detail = entry_details.get(entry["id"], {})
            raw_reactions = detail.get("reactions") or []
            entry["_reactions"] = [
                {
                    "username": user_map.get(rx["userId"], str(rx["userId"])),
                    "userId": rx["userId"],
                    "reaction": rx["reaction"],
                }
                for rx in raw_reactions
            ]
            entry["_description"] = detail.get("description", "")

        # 6. Winner — only if bounty is complete and a benefactor awarded an entry
        # awardedToId is only present in getById's benefactors, not in getBenefactors
        winner = None
        if stats_raw.get("complete"):
            for b in (stats_raw.get("benefactors") or []):
                awarded_id = b.get("awardedToId")
                if awarded_id:
                    detail = entry_details.get(awarded_id) or self._c._trpc_get(
                        "bountyEntry.getById", {"id": awarded_id}
                    )
                    if detail:
                        winner = {
                            "entry_id": awarded_id,
                            "username": self._username(detail.get("user")),
                            "awarded_buzz": b.get("unitAmount", 0),
                            "description": detail.get("description", ""),
                            "images": detail.get("images") or [],
                            "created_at": detail.get("createdAt", ""),
                        }
                    break

        return {
            "stats": stats,
            "benefactors": benefactors,
            "entries": entries,
            "_raw_entries": raw_entries,
            "_user_map": user_map,
            "winner": winner,
        }

    # ------------------------------------------------------------------
    # Internal fetch helpers
    # ------------------------------------------------------------------

    def _get_raw_entries(self, bounty_id: int) -> list[dict]:
        raw: list[dict] = []
        cursor = None
        while True:
            payload: dict = {"id": bounty_id, "limit": 60}
            if cursor is not None:
                payload["cursor"] = cursor
            page = self._c._trpc_get("bounty.getEntries", payload)
            raw.extend(page.get("items", []))
            cursor = page.get("nextCursor")
            if cursor is None:
                break
        return raw

    def _batch_entry_details(self, entry_ids: list[int]) -> dict[int, dict]:
        """Fetch bountyEntry.getById for all IDs, returns {entry_id: detail}."""
        result: dict[int, dict] = {}
        for i in range(0, len(entry_ids), _CHUNK):
            chunk = entry_ids[i : i + _CHUNK]
            batch = self._c._trpc_batch_get(
                [("bountyEntry.getById", {"id": eid}) for eid in chunk]
            )
            for eid, detail in zip(chunk, batch):
                result[eid] = detail or {}
        return result

    def _resolve_users(self, user_ids: set[int]) -> dict[int, str]:
        """Batch-resolve user IDs → usernames via user.getById."""
        ids = list(user_ids)
        result: dict[int, str] = {}
        for i in range(0, len(ids), _CHUNK):
            chunk = ids[i : i + _CHUNK]
            batch = self._c._trpc_batch_get(
                [("user.getById", {"id": uid}) for uid in chunk]
            )
            for uid, data in zip(chunk, batch):
                result[uid] = (data or {}).get("username") or str(uid)
        return result

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_stats(data: dict) -> BountyStats:
        stats = data.get("stats") or {}
        return BountyStats(
            bounty_id=data["id"],
            name=data.get("name", ""),
            status="Completed" if data.get("complete") else "Open",
            currency=data.get("currency", "Buzz"),
            unit_amount=data.get("unitAmount", 0),
            entries=stats.get("entryCountAllTime", 0),
            benefactors=stats.get("benefactorCountAllTime", 0),
            total_buzz=stats.get("unitAmountCountAllTime", 0),
            likes=stats.get("favoriteCountAllTime", 0),
            tracking=stats.get("trackCountAllTime", 0),
            comments=stats.get("commentCountAllTime", 0),
            starts_at=data.get("startsAt", ""),
            expires_at=data.get("expiresAt", ""),
        )

    @staticmethod
    def _parse_entry(item: dict) -> BountyEntry:
        stats = item.get("stats") or {}
        return BountyEntry(
            entry_id=item.get("id", 0),
            user=BountyAPI._username(item.get("user")),
            awarded_buzz=item.get("awardedUnitAmountTotal", 0),
            reactions={
                k: stats.get(k, 0)
                for k in ("likeCountAllTime", "heartCountAllTime",
                           "laughCountAllTime", "dislikeCountAllTime", "cryCountAllTime")
            },
            image_count=len(item.get("images") or []),
        )

    @staticmethod
    def _username(user: dict | None) -> str:
        if not user:
            return "unknown"
        return user.get("username") or user.get("name") or str(user.get("id", "?"))
