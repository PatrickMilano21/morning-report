# Morning Snapshot — Project Summary

## Overview

**Morning Snapshot** is a Stagehand-first prototype that automates pre-market research by aggregating financial data from multiple sources into a single, skimmable Markdown report. With one command, it pulls quotes, AI analysis, and headlines from Yahoo Finance, Google News, MarketWatch, and Vital Knowledge for a watchlist of tickers, then generates a consolidated report with macro overview, per-ticker statistics, sentiment analysis, and four concise key points.

## Technical Approach

### Core Stack
- **Stagehand** (AI-powered browser automation) for robust navigation and extraction
- **Browserbase** for managed browser sessions with stealth mode and CAPTCHA solving
- **Python** for clear orchestration of concurrent browser sessions
- **Pydantic** for structured data validation and schema definition

### Architecture Decisions
- **Separate browser sessions per source**: Each data source (Yahoo Quote, Yahoo AI, Google News, Vital Knowledge) runs in its own isolated session to prevent state pollution and cascading failures
- **Batch processing for Vital Knowledge**: Single shared session processes all tickers from the same report instance to ensure consistency
- **Graceful degradation**: System continues processing even when individual articles or sources fail, returning partial results
- **OpenAI API fallback**: When browser sessions timeout, summary generation falls back to direct OpenAI API calls instead of failing

## Development Process

### Tools & Workflow
- **Cursor + Claude Code**: Primary development environment for rapid iteration
- **Browserbase Replay**: Critical for debugging CAPTCHA issues, navigation failures, and session timeouts
- **Heavy logging**: Extensive logging helped identify failure patterns and timing issues
- **Environment variable toggles**: `.env` file includes feature flags (`ENABLE_GOOGLE_NEWS`, `ENABLE_VITAL_NEWS`, `ENABLE_MACRO_NEWS`) that allow enabling/disabling individual sources. This was invaluable for debugging — when multiple sources were failing, I could isolate the problem by running sources one at a time to identify which specific source was causing issues.

### Key Challenges & Solutions

1. **MarketWatch CAPTCHA Issues**
   - **Problem**: Repeated CAPTCHA blocks even with basic stealth mode
   - **Solution**: Identified via Replay; considering advanced stealth mode for future runs
   - **Lesson**: Some sites require more sophisticated anti-detection measures

2. **Vital Knowledge Link Inconsistency**
   - **Problem**: Different tickers were getting different report dates from the same static page
   - **Solution**: Refactored to batch processing — open morning report once, extract for all tickers, then open market close report once, extract for all tickers
   - **Lesson**: Element identification can be inconsistent; batch processing ensures data consistency

3. **Google News Session Timeouts** ⚠️ **MAJOR ISSUE**
   - **Problem**: Browserbase sessions have a hard timeout limit (~10 minutes). When processing 5 articles sequentially, cumulative time easily exceeds this limit:
     - Each article: ~20-60 seconds (navigation + load + extraction)
     - 5 articles: ~2-5 minutes minimum, but can exceed 8-10 minutes with slow pages
     - Result: Session closes mid-operation with `Status 410: session has completed or timed out`
     - Impact: Lost collected summaries, cascading errors, incomplete data
   - **Current Mitigation**: 
     - Per-article timeout limits (60s max per article)
     - Session timeout protection (stops at 8 minutes)
     - Early exit when 3+ successful stories collected
     - OpenAI API fallback for summary generation when page closes
     - Reduced wait times and better error handling
   - **Root Cause**: Sequential processing of multiple time-consuming operations within a single session
   - **Real Solution**: **Run sources concurrently within each ticker** — instead of processing Yahoo Quote → Yahoo AI → Google News sequentially, run them in parallel. This would:
     - Reduce total session time per ticker from ~10+ minutes to ~3-5 minutes
     - Keep each session well under the 10-minute timeout limit
     - Require more concurrent browser sessions (but semaphore already controls this)
     - Primarily a code structure change (already have separate session infrastructure)
   - **Lesson**: Browserbase timeout limits are a hard constraint; concurrent processing is the architectural solution, not just timeout management

4. **State Pollution Between Sources**
   - **Problem**: Sharing a single browser page across multiple sources caused cascading failures
   - **Solution**: Complete isolation — each source gets its own dedicated browser session
   - **Lesson**: Isolation prevents one failure from affecting others

5. **Yahoo AI Panel Click Failures**
   - **Problem**: Intermittent timeouts when clicking "Analyze with AI" button
   - **Status**: Still investigating; works when run alone but fails under concurrent load
   - **Lesson**: Some interactions are sensitive to page state and timing

6. **Debugging with Environment Toggles**
   - **Approach**: `.env` file includes feature flags (`ENABLE_GOOGLE_NEWS`, `ENABLE_VITAL_NEWS`, `ENABLE_MACRO_NEWS`, `ENABLE_YAHOO_QUOTE`, `ENABLE_YAHOO_ANALYSIS`, `ENABLE_MARKETWATCH`) that allow enabling/disabling individual sources
   - **Value**: When multiple sources were failing concurrently, I could isolate the problem by running sources one at a time. For example, when Yahoo AI was failing, I disabled all other sources and confirmed it worked alone — revealing the issue was related to concurrent session state, not the source itself
   - **Lesson**: Feature flags are essential for debugging complex multi-source systems; they let you test sources in isolation to identify root causes

7. **Password Logging in Stagehand Actions** (Known Issue)
   - **Problem**: Vital Knowledge login uses `page.act(f"Enter '{password}' into the password input field")`, which includes the actual password in the action string
   - **Impact**: Stagehand logs the full action string, so passwords appear in console output/logs
   - **Status**: We are aware of this but have not changed it because we are running in a local terminal environment where logs are not persisted or shared
   - **Security Note**: If logs are being written to files or sent to external logging services, this should be fixed by using generic action strings that don't include the actual password value

## Migration: Node.js → Python

**Why**: The orchestration logic for managing multiple concurrent browser sessions, error handling, and data merging was clearer in Python. The async/await patterns and type hints (via Pydantic) made the codebase more maintainable and easier to reason about.

## Current Status

✅ **Working**:
- Yahoo Quote extraction
- Google News article collection and summary generation (with fallback)
- Vital Knowledge batch processing for ticker-specific news
- Report generation with statistics, sentiment, and key points
- Graceful error handling and partial result preservation

⚠️ **Needs Attention**:
- **Browserbase Session Timeout Limits** (CRITICAL): Sequential processing of multiple sources per ticker causes cumulative time to exceed Browserbase's ~10-minute session timeout. Current mitigation helps but doesn't solve the root cause. **Solution: Run sources concurrently within each ticker** (see Next Steps #6).
- MarketWatch CAPTCHA (advanced stealth mode)
- Yahoo AI panel click reliability under concurrent load
- **Password Logging** (Known Issue): Vital Knowledge login actions include passwords in Stagehand action strings, which appear in logs. Not changed because we're running in a local terminal environment. See Key Challenges #7 for details.

## Next Steps

1. **MarketWatch**: Test advanced stealth mode to resolve CAPTCHA issues
2. **UI Layer**: Add lightweight web interface on top of current CLI
3. **Portfolio Integration**: Wire directly into real portfolio (scrape tickers/positions instead of static watchlist)
4. **Performance**: Tune concurrency limits and session usage to reduce runtime
5. **Robustness**: Implement retry logic, circuit breakers, and explicit selectors for Google News
6. **Intra-Ticker Concurrency** (HIGH PRIORITY - Solves Session Timeout Issue): Currently, tickers run concurrently but sources within each ticker (Yahoo Quote, Yahoo AI, Google News) run sequentially. This sequential processing causes cumulative session time to exceed Browserbase's ~10-minute timeout limit, especially for Google News (5 articles × 30-60s each = 2.5-5+ minutes just for one source). 
   - **Solution**: Refactor to run sources concurrently within each ticker
   - **Impact**: 
     - Reduces total session time per ticker from ~10+ minutes to ~3-5 minutes
     - Keeps each session well under Browserbase's timeout limit
     - Reduces total runtime from ~15 minutes to ~5-7 minutes for 2 tickers
   - **Implementation**: The semaphore already controls overall concurrency, so this is primarily a code structure change. Each source already has its own session infrastructure (`_run_source_with_session`), so we just need to run them in parallel instead of sequentially.
   - **Why This Matters**: This is the architectural solution to the session timeout problem, not just a performance optimization. Current timeout mitigations (per-article limits, early exit) help but don't address the root cause of cumulative time exceeding Browserbase limits.

## Key Learnings

1. **Isolation is critical**: Separate sessions prevent cascading failures
2. **Batch processing ensures consistency**: When data is static, process all items from the same source instance
3. **Always have fallbacks**: Browser sessions can timeout; design for graceful degradation
4. **Replay is invaluable**: Browserbase Replay made debugging CAPTCHA and navigation issues much faster
5. **Stagehand-first approach**: Using `page.act()`, `page.extract()`, and `page.observe()` instead of raw Playwright makes the code more resilient to layout changes

## Development Timeline

- **Initial prototype**: Node.js SDK with basic scraping
- **Refactoring**: Moved to Python for better orchestration
- **Integration**: Added Google News, Vital Knowledge, macro news
- **Robustness**: Implemented session isolation, error handling, fallbacks
- **Current**: Production-ready prototype with graceful degradation

---

*Built with Stagehand, Browserbase, and Python. Designed for reliability and maintainability.*

