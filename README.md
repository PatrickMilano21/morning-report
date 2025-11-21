# Morning Snapshot

A Stagehand-first Python application that automates pre-market research by aggregating financial data from multiple sources into a single, skimmable Markdown report.

## Overview

Morning Snapshot pulls quotes, AI analysis, and headlines from Yahoo Finance, Google News, MarketWatch, and Vital Knowledge for a watchlist of tickers, then generates a consolidated report with:

- **Market Overview**: Brief macro market summary from Vital Knowledge
- **Per-Ticker Statistics**: Price, volume, day range, extended hours data
- **Sentiment Analysis**: Bullish/bearish assessment with brief explanation
- **Key Points**: Four concise bullet points combining news from all sources

> 💡 **Example Report**: See [`data/reports/morning_snapshot_2025-11-20.md`](data/reports/morning_snapshot_2025-11-20.md) for a detailed example of the generated report.

## Features

- ✅ **Multi-Source Aggregation**: Yahoo Finance, Google News, MarketWatch, Vital Knowledge
- ✅ **AI-Powered Extraction**: Uses Stagehand for robust navigation and data extraction
- ✅ **Concurrent Processing**: Multiple browser sessions run in parallel for efficiency
- ✅ **Graceful Degradation**: Continues processing even when individual sources fail
- ✅ **Session Isolation**: Each source runs in its own browser session to prevent failures
- ✅ **Batch Processing**: Vital Knowledge uses shared sessions for consistency
- ✅ **Hybrid URL Extraction**: Google News uses Stagehand for metadata + JavaScript for URLs

## Requirements

- Python 3.10+
- Browserbase account with API key
- OpenAI API key (for Stagehand and fallback summary generation)
- Vital Knowledge account credentials (for macro news and ticker-specific research)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd morning_report
```

2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e .
```

## Configuration

### Environment Variables

Create a `.env` file in the project root. You can copy `.env.example` as a starting point:

```env
# ============================================
# Required Configuration
# ============================================

# Browserbase Configuration
# Get these from https://browserbase.com
BROWSERBASE_API_KEY=your_browserbase_api_key
BROWSERBASE_PROJECT_ID=your_project_id

# OpenAI Configuration (for Stagehand)
# Get this from https://platform.openai.com/api-keys
OPENAI_API_KEY=your_openai_api_key

# Vital Knowledge Credentials
# Your Vital Knowledge account credentials
Vital_login=your_vital_username
Vital_password=your_vital_password

# ============================================
# Optional Configuration
# ============================================

# Stagehand Model Configuration
# Options: gpt-4.1-mini, gpt-4.1, gpt-4.1-preview, etc.
STAGEHAND_MODEL_NAME=gpt-4.1-mini

# Stagehand Verbosity (0=minimal, 1=medium, 2=detailed)
STAGEHAND_VERBOSE=1

# Stagehand DOM Settle Timeout (milliseconds)
STAGEHAND_DOM_SETTLE_TIMEOUT_MS=30000

# Feature Flags (true/false, defaults to true if not set)
ENABLE_YAHOO_QUOTE=true
ENABLE_YAHOO_ANALYSIS=true
# MarketWatch: Keep false unless you have BROWSERBASE_ADVANCED_STEALTH enabled
# MarketWatch requires advanced stealth mode (Scale Plan) to avoid CAPTCHA
ENABLE_MARKETWATCH=false
ENABLE_GOOGLE_NEWS=true
ENABLE_VITAL_NEWS=true
ENABLE_MACRO_NEWS=true

# Concurrency (number of concurrent browser sessions, default: 2)
MAX_CONCURRENT_BROWSERS=2

# Browserbase Advanced Stealth Mode (requires Scale Plan, default: false)
BROWSERBASE_ADVANCED_STEALTH=false

# Browserbase CAPTCHA Solving (default: true)
BROWSERBASE_SOLVE_CAPTCHAS=true

# Browserbase Custom CAPTCHA Selectors (optional, only if needed)
# BROWSERBASE_CAPTCHA_IMAGE_SELECTOR=
# BROWSERBASE_CAPTCHA_INPUT_SELECTOR=

# Browserbase Proxies (recommended for CAPTCHA solving, default: true)
BROWSERBASE_USE_PROXIES=true
```

### Watchlist

Edit `config/watchlist.json` to specify your ticker symbols:

```json
[
  "AAPL",
  "GOOGL",
  "MSFT"
]
```

## Usage

Run the morning snapshot:

```bash
python -m src.core.cli.run_morning_snapshot
```

The script will:
1. Fetch data from all enabled sources for each ticker
2. Generate individual snapshots in `data/snapshots/`
3. Create a consolidated report in `data/reports/morning_snapshot_YYYY-MM-DD.md`

## Output

### Report Structure

```
# Morning Snapshot — 2025-11-20

## Market Overview
[Brief macro market summary from Vital Knowledge]

---

## Market Macro Overview
[Detailed morning and market close reports with bullets]

### AAPL
**Statistics:**
- Price, change, volume, day range, extended hours

**Bullish/Bearish**: [Sentiment with brief explanation]

**Key Points:**
- [4 concise bullet points from all news sources]
```

### Snapshots

Individual JSON snapshots are saved in `data/snapshots/`:
- `yahoo_snapshot_YYYY-MM-DD.json`
- `googlenews_snapshot_YYYY-MM-DD.json`
- `vital_knowledge_snapshot_YYYY-MM-DD.json`
- `macro_news_snapshot_YYYY-MM-DD.json`

## Data Sources

### Yahoo Finance
- **Quote Data**: Price, volume, day range, extended hours
- **AI Analysis**: "Why is this stock moving?" analysis with bullets

### Google News
- **Top Stories**: 5 most relevant articles from the last 2 days
- **Hybrid Extraction**: Uses Stagehand `extract()` for article metadata (headlines, sources, ages) and JavaScript `evaluate()` to extract actual URLs, then matches them together
- **Direct Navigation**: Navigates directly to article URLs (no clicking/redirect overhead)
- **Sequential Processing**: Articles processed sequentially (Browserbase doesn't support concurrent tabs well)
- **Summary**: AI-generated overall sentiment and 4 key bullet points

### Vital Knowledge
- **Ticker-Specific News**: Extracted from morning and market close reports
- **Macro News**: Overall market-moving news summaries

### MarketWatch
- **Top Stories**: Latest market headlines
- **Note**: Requires `BROWSERBASE_ADVANCED_STEALTH=true` (Scale Plan) to avoid CAPTCHA issues. Keep `ENABLE_MARKETWATCH=false` unless you have advanced stealth mode enabled.

## Architecture

### Session Management
- Each data source runs in its own isolated browser session
- Concurrent execution controlled by `MAX_CONCURRENT_BROWSERS` semaphore
- Vital Knowledge uses batch processing: one session processes all tickers from the same reports

### Error Handling
- Individual source failures don't stop the entire run
- Partial results are preserved and included in the report
- Articles with failed extractions are still included with basic metadata (headline, URL, source)

### Data Flow
1. Load watchlist from `config/watchlist.json`
2. Create concurrent tasks for each ticker + macro news
3. Each ticker task fetches from enabled sources in separate sessions
4. Merge Vital Knowledge batch results into ticker data
5. Generate snapshots and consolidated report

## Project Structure

```
morning_report/
├── config/
│   └── watchlist.json          # Ticker symbols
├── data/
│   ├── reports/                 # Generated Markdown reports
│   └── snapshots/               # Individual JSON snapshots
├── src/
│   ├── core/
│   │   ├── cli/
│   │   │   └── run_morning_snapshot.py  # Main entry point
│   │   ├── report_builder.py            # Report generation
│   │   └── stagehand_runner.py          # Browser session management
│   └── skills/
│       ├── googlenews/          # Google News scraping
│       ├── marketwatch/         # MarketWatch scraping
│       ├── vital_knowledge/     # Vital Knowledge scraping
│       └── yahoo/               # Yahoo Finance scraping
└── README.md
```

## Development

### Key Design Decisions

- **Stagehand-first**: Uses `page.act()`, `page.extract()`, and `page.observe()` instead of raw Playwright for resilience
- **Python over Node.js**: Better orchestration of concurrent sessions and error handling
- **Pydantic models**: Structured data validation with automatic camelCase/snake_case handling
- **Separate sessions**: Complete isolation prevents cascading failures
- **Hybrid URL extraction (Google News)**: Combines Stagehand's AI extraction for visible metadata with JavaScript DOM queries for reliable URL extraction
- **Direct navigation**: Google News navigates directly to article URLs instead of clicking links, reducing overhead and session time

### Testing Individual Sources

```bash
# Test Google News
python -m src.skills.googlenews.research

# Test Vital Knowledge
python -m src.skills.vital_knowledge.research

# Test Macro News
python -m src.skills.vital_knowledge.macro_news
```

## Troubleshooting

### Browser Session Timeouts
- Reduce `max_stories` in Google News (default: 5)
- Google News processes articles sequentially to avoid session timeouts
- Direct navigation (no clicking/redirect overhead) reduces processing time
- Articles with failed extractions are still included with basic metadata

### CAPTCHA Issues
- **MarketWatch**: Keep `ENABLE_MARKETWATCH=false` unless you have `BROWSERBASE_ADVANCED_STEALTH=true` enabled (requires Browserbase Scale Plan). MarketWatch requires advanced stealth mode to avoid CAPTCHA blocking.

### Missing Data
- Check that environment variables are set correctly
- Verify credentials for Vital Knowledge
- Check logs for specific source failures

### Password Logging (Known Issue)
- **Note**: Vital Knowledge login actions include the password in the action string, which appears in Stagehand's logs (e.g., `{'action': "Enter 'password' into the password input field"}`)
- **Status**: We are aware of this but have not changed it because we are running in a local terminal environment where logs are not persisted or shared
- **Security Consideration**: If logs are being written to files or sent to external logging services, this should be fixed by using generic action strings that don't include the actual password value

## Next Steps

- [ ] Test MarketWatch with advanced stealth mode
- [ ] Add lightweight web UI
- [ ] Integrate with real portfolio (dynamic ticker list)
- [ ] Optimize concurrency and session usage (intra-ticker concurrency for sources)
- [ ] Add retry logic for failed article extractions
- [ ] Consider parallel article processing if Browserbase adds better tab support

## License

[Add your license here]

---

*Built with [Stagehand](https://github.com/browserbase/stagehand-python), [Browserbase](https://browserbase.com), and Python.*

