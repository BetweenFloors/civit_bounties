# civit_bounties

Python client for the [Civitai](https://civitai.red) bounty API.  
Fetches participation statistics, reactions, and prompt data, and generates a self-contained HTML report.

> **Note:** Civitai bounties are only active on `civitai.red` (not `civitai.com`).

## Requirements

- Python 3.10+
- `requests`

## Installation

```bash
git clone https://github.com/BetweenFloors/civit_bounties.git
cd civit_bounties
pip install .
```

Get your API token at **civitai.red → account settings → API keys**.

## Usage

### Web UI (recommended)

```bash
civitai-server
```

Opens `http://localhost:8000` automatically. Enter your API token and bounty ID, choose a theme — the report opens in a new tab. No configuration needed.

> **⚠️ Note:** The report fetches every single entry, reaction, and prompt from the API. For large bounties (300+ entries) this can take 20–30 seconds. Don't close the tab while loading.

![UI screenshot: dark form with token/bounty ID fields and theme selector]

### CLI

```bash
# Console stats only
civitai --token YOUR_TOKEN bounty 12018

# Generate an HTML report
civitai --token YOUR_TOKEN bounty 12018 --html report.html

# Or use an environment variable
export CIVITAI_TOKEN=YOUR_TOKEN
civitai bounty 12018 --html report.html
```

### Python

```python
from civitai import Civitai
from civitai.report import generate_html

civ = Civitai(api_token="YOUR_TOKEN")

# Quick stats
stats = civ.bounties.get_stats(12018)
print(stats.entries, stats.total_buzz)

# Full report (entries + reactions + prompt analysis)
report = civ.bounties.full_report(12018)
generate_html(report, 12018, "report.html")
```

## How it works

All processing runs locally. The CLI and server both make requests directly to `civitai.red` using your token — nothing goes through a third-party. The local server exists only to bypass browser CORS restrictions; the generated HTML is self-contained and never uploaded anywhere.

## Example report

- [`examples/bounty_11729.html`](examples/bounty_11729.html) — 300+ entries, dark theme
- [`examples/bounty_11541_light.html`](examples/bounty_11541_light.html) — light theme

## HTML report contents

| Section | Description |
|---|---|
| Stats grid | Entries, participants, Buzz, reactions, favorites, comments |
| Daily chart | Submissions per day |
| Participants table | Ranked by entry count |
| Reactions table | Who reacted, reaction type breakdown |
| Prompt analysis | Avg token length per user, frequent words, exclusive vocabulary |
| Participant cards | One card per user with all their image thumbnails and reactions |
