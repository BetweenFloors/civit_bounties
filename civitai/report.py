"""Generates an HTML report for a bounty."""

from __future__ import annotations

import html
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .prompt_analysis import analyze as analyze_prompts


_IMG_CDN = "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA"
_BOUNTY_BASE = "https://civitai.red/bounties"
_USER_BASE = "https://civitai.red/user"

_REACTION_EMOJI = {
    "Like":    "👍",
    "Heart":   "❤️",
    "Laugh":   "😂",
    "Cry":     "😢",
    "Dislike": "👎",
}


def _img_url(uuid: str, name: str, width: int = 450) -> str:
    return f"{_IMG_CDN}/{uuid}/width={width}/{html.escape(name)}"


def _fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except Exception:
        return iso[:10]


def _days_left(iso: str) -> str:
    try:
        expires = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = expires - now
        if delta.days < 0:
            hours = int(-delta.total_seconds() / 3600)
            return f"Ended ({hours}h ago)" if hours < 48 else "Ended"
        if delta.days == 0:
            hours = int(delta.total_seconds() / 3600)
            return f"Expires in {hours}h"
        return f"{delta.days}d left"
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _reaction_badges(reactions: list[dict]) -> str:
    """Render inline reaction badges with reactor usernames as tooltip."""
    by_type: dict[str, list[str]] = defaultdict(list)
    for rx in reactions:
        by_type[rx["reaction"]].append(rx["username"])

    parts = []
    for rtype, users in by_type.items():
        emoji = _REACTION_EMOJI.get(rtype, rtype)
        tooltip = html.escape(", ".join(f"@{u}" for u in users))
        parts.append(
            f'<span class="rx-badge" title="{tooltip}">'
            f'{emoji} {len(users)}</span>'
        )
    return " ".join(parts)


def _entry_thumb(entry: dict, bounty_id: int, width: int = 200) -> str:
    """Small thumbnail card for use inside a participant card."""
    entry_id = entry.get("id", 0)
    images = entry.get("images") or []
    reactions = entry.get("_reactions") or []
    desc = entry.get("_description", "") or ""
    awarded = entry.get("awardedUnitAmountTotal", 0)
    date = _fmt_date(entry.get("createdAt", ""))
    entry_url = f"{_BOUNTY_BASE}/{bounty_id}/entries/{entry_id}"

    img_tag = ""
    if images:
        img = images[0]
        img_tag = (
            f'<img src="{_img_url(img["url"], img["name"], width)}" '
            f'loading="lazy" alt="entry #{entry_id}">'
        )
    else:
        img_tag = '<div class="no-img">—</div>'

    rx_html = _reaction_badges(reactions)

    awarded_badge = (
        f'<div class="awarded-badge">⚡ {awarded:,} Buzz</div>'
        if awarded > 0 else ""
    )

    # Strip HTML tags from description for display
    import re
    clean_desc = re.sub(r"<[^>]+>", "", desc).strip()
    desc_html = (
        f'<div class="thumb-desc" title="{html.escape(clean_desc)}">'
        f'{html.escape(clean_desc[:60])}{"…" if len(clean_desc) > 60 else ""}</div>'
        if clean_desc else ""
    )

    return f"""
    <div class="thumb">
      <a href="{entry_url}" target="_blank" class="thumb-img">
        {img_tag}
        {awarded_badge}
      </a>
      {desc_html}
      <div class="thumb-foot">
        <span class="thumb-date">{date}</span>
        <span class="thumb-rx">{rx_html}</span>
      </div>
    </div>"""


def generate_html(report: dict, bounty_id: int, output_path: str | Path | None = None, theme: str = "dark") -> str:
    stats = report["stats"]
    entries = report["entries"]
    benefactors = report["benefactors"]
    raw_entries = report.get("_raw_entries", [])

    bounty_name = html.escape(stats.name)
    bounty_url = f"{_BOUNTY_BASE}/{bounty_id}"
    expires_label = _days_left(stats.expires_at)

    # --- Group entries by participant -----------------------------------
    by_participant: dict[str, list[dict]] = defaultdict(list)
    for e in raw_entries:
        username = (e.get("user") or {}).get("username") or "?"
        by_participant[username].append(e)

    # Sort participants: most entries first, then alphabetical
    sorted_participants = sorted(
        by_participant.items(),
        key=lambda x: (-len(x[1]), x[0].lower()),
    )

    # --- Reactions summary ---------------------------------------------
    reactor_counts: Counter = Counter()
    reaction_type_counts: Counter = Counter()
    entry_reaction_totals: dict[int, int] = {}
    for e in raw_entries:
        rxs = e.get("_reactions") or []
        entry_reaction_totals[e["id"]] = len(rxs)
        for rx in rxs:
            reactor_counts[rx["username"]] += 1
            reaction_type_counts[rx["reaction"]] += 1

    # --- Daily chart ---------------------------------------------------
    day_counts: Counter = Counter(e["createdAt"][:10] for e in raw_entries if e.get("createdAt"))
    sorted_days = sorted(day_counts.items())
    max_day = max((v for _, v in sorted_days), default=1)

    def bar_pct(n: int) -> int:
        return max(2, round(n / max_day * 100))

    bars_html = ""
    for day, count in sorted_days:
        bars_html += f"""
        <div class="bar-group">
          <div class="bar" style="height:{bar_pct(count)}%" title="{day}: {count}">
            <span class="bar-val">{count}</span>
          </div>
          <div class="bar-label">{day[5:]}</div>
        </div>"""

    # --- Reaction type summary strip -----------------------------------
    rx_summary = " &nbsp; ".join(
        f'{_REACTION_EMOJI.get(k, k)} <strong>{v}</strong> {k}'
        for k, v in reaction_type_counts.most_common()
    )

    # --- Top participants table ----------------------------------------
    top_participants_rows = ""
    for rank, (username, p_entries) in enumerate(sorted_participants, 1):
        top_participants_rows += f"""
        <tr>
          <td class="rank">#{rank}</td>
          <td><a href="{_USER_BASE}/{html.escape(username)}" target="_blank">@{html.escape(username)}</a></td>
          <td>{len(p_entries)}</td>
        </tr>"""


    # --- Participant cards ---------------------------------------------
    participant_cards = ""
    for username, p_entries in sorted_participants:
        n = len(p_entries)
        total_rx = sum(entry_reaction_totals.get(e["id"], 0) for e in p_entries)
        total_buzz = sum(e.get("awardedUnitAmountTotal", 0) for e in p_entries)
        user_url = f"{_USER_BASE}/{html.escape(username)}"

        thumbs = "\n".join(
            _entry_thumb(e, bounty_id)
            for e in sorted(p_entries, key=lambda x: x.get("createdAt", ""))
        )

        buzz_badge = (
            f'<span class="p-buzz">⚡ {total_buzz:,}</span>'
            if total_buzz > 0 else ""
        )

        participant_cards += f"""
        <div class="p-card">
          <div class="p-header">
            <a href="{user_url}" target="_blank" class="p-username">@{html.escape(username)}</a>
            <div class="p-meta">
              <span class="p-count">{n} entr{'y' if n == 1 else 'ies'}</span>
              {f'<span class="p-rx">💬 {total_rx} reactions</span>' if total_rx else ''}
              {buzz_badge}
            </div>
          </div>
          <div class="p-thumbs">{thumbs}</div>
        </div>"""

    # --- Benefactors ---------------------------------------------------
    bene_chips = " ".join(
        f'<span class="bene-chip">'
        f'<a href="{_USER_BASE}/{html.escape(b.user)}" target="_blank">@{html.escape(b.user)}</a>'
        f' · {b.unit_amount:,} Buzz</span>'
        for b in sorted(benefactors, key=lambda x: -x.unit_amount)
    )

    # --- Winner --------------------------------------------------------
    winner = report.get("winner")
    winner_html = ""
    if winner:
        import re as _re
        w_user = html.escape(winner["username"])
        w_entry_url = f"{_BOUNTY_BASE}/{bounty_id}/entries/{winner['entry_id']}"
        w_desc = _re.sub(r"<[^>]+>", "", winner.get("description", "")).strip()
        w_buzz = winner["awarded_buzz"]
        w_imgs = winner.get("images") or []
        w_img_tag = ""
        if w_imgs:
            img = w_imgs[0]
            w_img_tag = (
                f'<a href="{w_entry_url}" target="_blank">'
                f'<img src="{_img_url(img["url"], img["name"], 300)}" '
                f'alt="winning entry" style="width:100%;border-radius:8px;display:block;margin-bottom:10px"></a>'
            )
        winner_html = f"""
        <div class="winner-card">
          <div class="winner-header">🏆 Winner</div>
          {w_img_tag}
          <div class="winner-user">
            <a href="{_USER_BASE}/{w_user}" target="_blank">@{w_user}</a>
          </div>
          {f'<div class="winner-desc">{html.escape(w_desc)}</div>' if w_desc else ''}
          <div class="winner-buzz">⚡ {w_buzz:,} Buzz</div>
          <a href="{w_entry_url}" target="_blank" class="winner-link">View entry →</a>
        </div>"""

    # --- Prompt analysis -----------------------------------------------
    pr = analyze_prompts(raw_entries)
    max_avg = max((p.avg_tokens for p in pr.profiles), default=1)

    prompt_rows = ""
    for p in pr.profiles:
        bar_w = max(2, round(p.avg_tokens / max_avg * 100))
        excl_html = " ".join(
            f'<span class="tag excl">{html.escape(w)}</span>'
            for w in p.exclusive_words
        ) or '<span style="color:var(--muted)">—</span>'
        top_html = " ".join(
            f'<span class="tag">{html.escape(w)}</span>'
            for w, _ in p.top_words[:5]
        ) or '<span style="color:var(--muted)">—</span>'
        prompt_rows += f"""
        <tr>
          <td><a href="{_USER_BASE}/{html.escape(p.username)}" target="_blank">@{html.escape(p.username)}</a></td>
          <td>
            <div class="inline-bar" style="width:{bar_w}%"></div>
            <div class="bar-num">{p.avg_tokens:.0f}</div>
          </td>
          <td>{p.prompt_count}</td>
          <td class="tag-cell">{top_html}</td>
          <td class="tag-cell">{excl_html}</td>
        </tr>"""

    global_tags_html = " ".join(
        f'<span class="tag" style="font-size:{min(1.1, 0.7 + c/pr.global_top[0][1]*0.5):.2f}rem">'
        f'{html.escape(w)} <sup>{c}</sup></span>'
        for w, c in pr.global_top
    )

    # -------------------------------------------------------------------
    html_doc = f"""<!DOCTYPE html>
<html lang="fr" data-theme="{theme}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{bounty_name} — Bounty Report</title>
<style>
:root, [data-theme="dark"] {{
  --bg: #0d0d1a;
  --surface: #16213e;
  --surface2: #1a1a2e;
  --border: #2a2a4a;
  --accent: #e879f9;
  --accent2: #818cf8;
  --text: #e2e8f0;
  --muted: #64748b;
  --buzz: #facc15;
  --r: 10px;
}}
[data-theme="light"] {{
  --bg: #f1f5f9;
  --surface: #ffffff;
  --surface2: #f8fafc;
  --border: #e2e8f0;
  --accent: #9333ea;
  --accent2: #6366f1;
  --text: #1e293b;
  --muted: #94a3b8;
  --buzz: #b45309;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; padding: 20px 24px; max-width: 1400px; margin: 0 auto; }}
a {{ color: var(--accent2); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* HEADER */
.page-header {{ background: linear-gradient(135deg,var(--surface),var(--surface2));
  border: 1px solid var(--border); border-radius: var(--r); padding: 24px 28px; margin-bottom: 20px; }}
.page-header h1 {{ font-size: 1.7rem; }}
.page-header h1 a {{ color: var(--accent); }}
.expires-tag {{ display: inline-block; background: #7c3aed22; color: #a78bfa;
  border: 1px solid #7c3aed55; border-radius: 20px; padding: 2px 10px;
  font-size: 0.78rem; margin-left: 8px; vertical-align: middle; }}
.header-meta {{ color: var(--muted); font-size: 0.85rem; margin-top: 6px; }}

/* STATS GRID */
.stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px,1fr));
  gap: 12px; margin-bottom: 20px; }}
.stat {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r); padding: 14px 12px; text-align: center; }}
.stat-val {{ font-size: 1.9rem; font-weight: 700; color: var(--accent); line-height: 1; }}
.stat-val.buzz {{ color: var(--buzz); }}
.stat-label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase;
  letter-spacing: .05em; margin-top: 4px; }}

/* SECTIONS */
.section {{ margin-bottom: 28px; }}
.section-title {{ font-size: 1rem; font-weight: 600; color: var(--accent2);
  padding-bottom: 6px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }}

/* CHART */
.chart {{ display: flex; align-items: flex-end; gap: 8px; height: 130px;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r); padding: 14px; }}
.bar-group {{ flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 4px; height: 100%; justify-content: flex-end; }}
.bar {{ background: linear-gradient(180deg,var(--accent),var(--accent2));
  width: 100%; border-radius: 4px 4px 0 0; display: flex;
  align-items: flex-start; justify-content: center; min-height: 3px; }}
.bar-val {{ font-size: 0.65rem; font-weight: 700; color: #fff; padding: 2px 0; }}
.bar-label {{ font-size: 0.62rem; color: var(--muted); }}

/* TABLES */
table {{ width: 100%; border-collapse: collapse; background: var(--surface);
  border-radius: var(--r); overflow: hidden; border: 1px solid var(--border); }}
th {{ background: var(--surface2); color: var(--muted); font-size: 0.72rem;
  text-transform: uppercase; letter-spacing: .05em; padding: 9px 14px; text-align: left; }}
td {{ padding: 9px 14px; border-top: 1px solid var(--border); font-size: 0.88rem; }}
.rank {{ color: var(--muted); }}
tr:hover td {{ background: #ffffff06; }}

/* REACTION SUMMARY BAR */
.rx-summary {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r); padding: 12px 16px; font-size: 0.9rem;
  color: var(--text); margin-bottom: 14px; }}

/* PARTICIPANT CARDS */
.p-cards {{ display: flex; flex-direction: column; gap: 16px; }}
.p-card {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r); overflow: hidden; }}
.p-header {{ display: flex; align-items: center; gap: 14px; padding: 12px 16px;
  background: var(--surface2); border-bottom: 1px solid var(--border); flex-wrap: wrap; }}
.p-username {{ font-size: 1rem; font-weight: 700; color: var(--accent); }}
.p-meta {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
.p-count {{ background: #818cf822; color: var(--accent2); border: 1px solid #818cf844;
  border-radius: 12px; padding: 2px 9px; font-size: 0.75rem; }}
.p-rx {{ color: var(--muted); font-size: 0.8rem; }}
.p-buzz {{ background: #ca8a0422; color: var(--buzz); border: 1px solid #ca8a0444;
  border-radius: 12px; padding: 2px 9px; font-size: 0.75rem; }}

/* THUMBNAIL STRIP */
.p-thumbs {{ display: flex; flex-wrap: wrap; gap: 10px; padding: 12px; }}
.thumb {{ width: 200px; background: var(--surface2); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; flex-shrink: 0;
  transition: border-color .15s, transform .15s; }}
.thumb:hover {{ border-color: var(--accent2); transform: translateY(-2px); }}
.thumb-img {{ display: block; aspect-ratio: 1; overflow: hidden;
  background: #0a0a1a; position: relative; }}
.thumb-img img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.no-img {{ display: flex; align-items: center; justify-content: center;
  height: 100%; color: var(--muted); font-size: 0.8rem; }}
.awarded-badge {{ position: absolute; bottom: 6px; left: 6px;
  background: #ca8a04cc; color: #fef08a; border-radius: 8px;
  padding: 2px 7px; font-size: 0.7rem; font-weight: 700; }}
.thumb-desc {{ padding: 5px 8px 0; font-size: 0.72rem; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.thumb-foot {{ display: flex; justify-content: space-between; align-items: center;
  padding: 4px 8px 7px; }}
.thumb-date {{ font-size: 0.68rem; color: var(--muted); }}
.thumb-rx {{ display: flex; gap: 4px; flex-wrap: wrap; }}
.rx-badge {{ font-size: 0.72rem; background: #ffffff0a; border: 1px solid var(--border);
  border-radius: 10px; padding: 1px 6px; cursor: default; white-space: nowrap; }}

.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media (max-width: 700px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
.two-col .section {{ margin-bottom: 0; }}

/* WINNER */
.winner-card {{ background: linear-gradient(135deg, #7c3aed22, #e879f911);
  border: 1px solid #7c3aed66; border-radius: var(--r); padding: 16px; }}
.winner-header {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: #a78bfa; margin-bottom: 12px; }}
.winner-user {{ font-size: 1.1rem; font-weight: 700; margin-bottom: 6px; }}
.winner-user a {{ color: var(--accent); }}
.winner-desc {{ font-size: 0.85rem; color: var(--muted); margin-bottom: 8px;
  font-style: italic; }}
.winner-buzz {{ font-size: 0.9rem; color: var(--buzz); font-weight: 600;
  margin-bottom: 10px; }}
.winner-link {{ font-size: 0.8rem; color: var(--accent2); }}

/* PROMPT ANALYSIS */
.inline-bar {{ display: inline-block; height: 8px; background: linear-gradient(90deg,var(--accent2),var(--accent));
  border-radius: 4px; vertical-align: middle; margin-right: 6px; min-width: 2px; }}
.bar-num {{ font-size: 0.8rem; color: var(--muted); font-variant-numeric: tabular-nums; margin-top: 3px; }}
.tag-cell {{ max-width: 280px; }}
.tag {{ display: inline-block; background: #818cf811; border: 1px solid #818cf833;
  border-radius: 6px; padding: 1px 7px; font-size: 0.72rem; color: var(--accent2);
  margin: 2px 2px; white-space: nowrap; }}
.tag.excl {{ background: #e879f911; border-color: #e879f933; color: var(--accent); }}
.global-tags {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r); padding: 14px 16px; line-height: 2.2; }}
.prompt-table th:nth-child(2) {{ width: 160px; }}
.prompt-table th:nth-child(3) {{ width: 60px; }}

.header-bene {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.header-bene-label {{ font-size: 0.75rem; color: var(--muted); margin-right: 4px; }}
.bene-chip {{ background: #ca8a0418; border: 1px solid #ca8a0444; border-radius: 14px;
  padding: 2px 10px; font-size: 0.78rem; color: var(--buzz); white-space: nowrap; }}
.bene-chip a {{ color: var(--buzz); }}

.footer {{ text-align: center; color: var(--muted); font-size: 0.72rem;
  margin-top: 40px; padding-top: 14px; border-top: 1px solid var(--border); }}
</style>
</head>
<body>

<div class="page-header">
  <h1>
    <a href="{bounty_url}" target="_blank">{bounty_name}</a>
    <span class="expires-tag">{expires_label}</span>
  </h1>
  <div class="header-meta">
    {_fmt_date(stats.starts_at)} → {_fmt_date(stats.expires_at)}
    &nbsp;·&nbsp; Bounty #{bounty_id}
    &nbsp;·&nbsp; <a href="{bounty_url}" target="_blank">civitai.red</a>
  </div>
  {f'<div class="header-bene"><span class="header-bene-label">💰 Creator:</span> {bene_chips}</div>' if bene_chips else ''}
</div>

<div class="stats-grid">
  <div class="stat"><div class="stat-val">{stats.entries}</div><div class="stat-label">Entries</div></div>
  <div class="stat"><div class="stat-val">{len(sorted_participants)}</div><div class="stat-label">Participants</div></div>
  <div class="stat"><div class="stat-val buzz">{stats.total_buzz:,}</div><div class="stat-label">Total Buzz</div></div>
  <div class="stat"><div class="stat-val">{sum(reaction_type_counts.values())}</div><div class="stat-label">Reactions</div></div>
  <div class="stat"><div class="stat-val">{stats.favorites}</div><div class="stat-label">Favorites</div></div>
  <div class="stat"><div class="stat-val">{stats.comments}</div><div class="stat-label">Comments</div></div>
</div>

<div class="section">
  <div class="section-title">Submissions per day</div>
  <div class="chart">{bars_html}</div>
</div>

<div class="two-col">
  <div class="section">
    <div class="section-title">Participants ({len(sorted_participants)}) — entries</div>
    <table>
      <thead><tr><th>#</th><th>User</th><th>Entries</th></tr></thead>
      <tbody>{top_participants_rows}</tbody>
    </table>
  </div>
  <div style="display:flex;flex-direction:column;gap:16px">
    <div class="section" style="margin-bottom:0">
      <div class="section-title">Reactions — {sum(reaction_type_counts.values())} total</div>
      {f'<div class="rx-summary">{rx_summary}</div>' if rx_summary else '<div style="color:var(--muted);font-size:.85rem">No reactions yet.</div>'}
    </div>
    {winner_html}
  </div>
</div>


<div class="section" style="margin-top:40px">
  <div class="section-title">Prompt analysis — {pr.total_images_with_prompt}/{pr.total_images} images with prompt</div>
  <div class="section" style="margin-bottom:14px">
    <div class="section-title" style="font-size:.85rem">Most used words (all users)</div>
    <div class="global-tags">{global_tags_html}</div>
  </div>
  <table class="prompt-table">
    <thead>
      <tr>
        <th>User</th>
        <th>Avg tokens/prompt</th>
        <th>Prompts</th>
        <th>Top words</th>
        <th>Exclusive words ✦</th>
      </tr>
    </thead>
    <tbody>{prompt_rows}</tbody>
  </table>
  <div style="color:var(--muted);font-size:0.72rem;margin-top:8px">
    ✦ Words found only in this user's prompts
  </div>
</div>

<div class="section">
  <div class="section-title">Participants ({len(sorted_participants)}) — sorted by entry count</div>
  <div class="p-cards">{participant_cards}</div>
</div>

<div class="footer">
  Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} · <a href="https://github.com/BetweenFloors/civit_bounties" target="_blank">civit_bounties</a> · bounty #{bounty_id}
</div>
</body>
</html>"""

    if output_path:
        Path(output_path).write_text(html_doc, encoding="utf-8")

    return html_doc
