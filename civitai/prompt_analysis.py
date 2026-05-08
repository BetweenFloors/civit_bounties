"""Prompt analysis for bounty entries."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class UserPromptProfile:
    username: str
    prompt_count: int          # images avec un prompt
    avg_tokens: float          # moyenne de tokens par prompt
    total_tokens: int
    top_words: list[tuple[str, int]]       # (mot, fréquence) les plus utilisés
    exclusive_words: list[str]             # mots absents de tous les autres utilisateurs


@dataclass
class PromptReport:
    profiles: list[UserPromptProfile]      # triés par avg_tokens desc
    global_top: list[tuple[str, int]]      # mots les plus communs tous users confondus
    total_images_with_prompt: int
    total_images: int


# Mots trop génériques pour être significatifs comme "signature"
_COMMON_SD_TAGS = {
    "masterpiece", "best", "quality", "high", "ultra", "detailed",
    "realistic", "photorealistic", "sharp", "focus", "8k", "4k",
    "lighting", "light", "dark", "background", "style", "art",
    "beautiful", "highly", "render", "rendered", "photo", "digital",
    "painting", "illustration", "character", "image", "the", "and",
    "with", "from", "into", "very", "more", "full", "long", "wide",
    "skin", "eyes", "hair", "face", "body", "hands", "soft",
    "cinematic", "dramatic", "dynamic", "perfect", "amazing",
    "score_9", "score_8", "score_7", "score_6",
}


def _tokenize(prompt: str) -> list[str]:
    """Split prompt into lowercase tokens, stripping punctuation."""
    tokens = re.split(r"[,\s]+", prompt.lower())
    cleaned = []
    for t in tokens:
        t = re.sub(r"[^a-z0-9_\-]", "", t)
        if len(t) >= 3:
            cleaned.append(t)
    return cleaned


def analyze(raw_entries: list[dict]) -> PromptReport:
    """
    Analyse all prompts across raw bounty entries.
    raw_entries: the _raw_entries list from full_report().
    """
    # Collect tokens per user
    user_token_lists: dict[str, list[list[str]]] = defaultdict(list)  # user → [prompt_tokens, ...]
    total_images = 0
    total_with_prompt = 0

    for entry in raw_entries:
        username = (entry.get("user") or {}).get("username") or "?"
        for img in entry.get("images") or []:
            total_images += 1
            prompt = (img.get("meta") or {}).get("prompt", "")
            if prompt:
                total_with_prompt += 1
                user_token_lists[username].append(_tokenize(prompt))

    # Build per-user vocabulary sets (for exclusivity check)
    user_vocab: dict[str, set[str]] = {
        u: {tok for prompt_toks in lists for tok in prompt_toks}
        for u, lists in user_token_lists.items()
    }

    # Count how many users use each word
    word_user_count: Counter = Counter()
    for vocab in user_vocab.values():
        for w in vocab:
            word_user_count[w] += 1

    # Global frequency (all tokens, all users)
    global_freq: Counter = Counter()
    for lists in user_token_lists.values():
        for toks in lists:
            global_freq.update(toks)

    # Build profiles
    profiles: list[UserPromptProfile] = []
    for username, prompt_token_lists in user_token_lists.items():
        flat_tokens = [t for toks in prompt_token_lists for t in toks]
        counts = [len(toks) for toks in prompt_token_lists]
        avg = sum(counts) / len(counts) if counts else 0

        local_freq: Counter = Counter(flat_tokens)

        # Exclusive: word appears in only this user's vocab, not too generic,
        # and used at least once (single occurrence is enough — it's a bounty, not a corpus)
        exclusive = [
            w for w in user_vocab[username]
            if word_user_count[w] == 1
            and w not in _COMMON_SD_TAGS
            and len(w) >= 4
        ]
        # Sort exclusive by local frequency
        exclusive_sorted = sorted(exclusive, key=lambda w: -local_freq[w])

        # Top local words (excluding generic tags)
        top_words = [
            (w, c) for w, c in local_freq.most_common(20)
            if w not in _COMMON_SD_TAGS and len(w) >= 4
        ][:8]

        profiles.append(UserPromptProfile(
            username=username,
            prompt_count=len(prompt_token_lists),
            avg_tokens=avg,
            total_tokens=len(flat_tokens),
            top_words=top_words,
            exclusive_words=exclusive_sorted[:8],
        ))

    profiles.sort(key=lambda p: -p.avg_tokens)

    # Global top words (excluding generic)
    global_top = [
        (w, c) for w, c in global_freq.most_common(30)
        if w not in _COMMON_SD_TAGS and len(w) >= 4
    ][:15]

    return PromptReport(
        profiles=profiles,
        global_top=global_top,
        total_images_with_prompt=total_with_prompt,
        total_images=total_images,
    )
