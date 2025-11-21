# src/skills/vital_knowledge/research.py
#
# This script scrapes Vital Knowledge for ticker-specific macro news using Stagehand.
# It logs in, navigates to morning and market close reports, and extracts ticker-specific news.

import asyncio
import os
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# DATA MODELS (Pydantic)
# =============================================================================

class VitalKnowledgeHeadline(BaseModel):
    """Single headline from Vital Knowledge report."""
    headline: str = Field(..., description="The headline text")
    context: Optional[str] = Field(default=None, description="Additional context or details")
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = Field(
        default=None,
        description="Sentiment of the headline"
    )


class VitalKnowledgeSummary(BaseModel):
    """Summary of all headlines for a ticker."""
    overall_sentiment: Optional[Literal["bullish", "bearish", "mixed", "neutral"]] = Field(
        default=None,
        description="Overall sentiment across headlines"
    )
    key_themes: List[str] = Field(
        default_factory=list,
        description="Main themes or topics"
    )
    summary: Optional[str] = Field(
        default=None,
        description="Very brief 1-2 sentence summary of key points"
    )


class VitalKnowledgeReport(BaseModel):
    """Container for all extracted Vital Knowledge data."""
    ticker: str
    headlines: List[VitalKnowledgeHeadline] = Field(default_factory=list)
    report_dates: List[str] = Field(default_factory=list, description="Dates of reports scraped")
    summary: Optional[VitalKnowledgeSummary] = Field(default=None)


class ExtractedBullets(BaseModel):
    """Helper model for extracting ticker-specific bullets from a report."""
    bullets: List[str] = Field(
        default_factory=list,
        description="List of bullet points about the ticker, max 5 per report"
    )


class CombinedBullets(BaseModel):
    """Helper model for combining and sorting bullets by importance."""
    model_config = ConfigDict(populate_by_name=True)
    
    top_bullets: List[str] = Field(
        default_factory=list,
        alias="topBullets",
        description="Top 5 most important bullets, sorted by importance"
    )


# =============================================================================
# MAIN SCRAPING FUNCTION
# =============================================================================

async def fetch_vital_knowledge_headlines_batch(
    page,
    tickers: List[str],
) -> List[VitalKnowledgeReport]:
    """
    Fetch ticker-specific macro news from Vital Knowledge for multiple tickers.
    
    This function efficiently:
    1. Logs in once
    2. Opens morning report once and extracts data for all tickers
    3. Opens market close report once and extracts data for all tickers
    4. Combines and processes bullets for each ticker
    
    Args:
        page: A StagehandPage instance
        tickers: List of stock ticker symbols (e.g., ["AAPL", "GOOGL"])
    
    Returns:
        List of VitalKnowledgeReport objects, one per ticker
    """
    print(f"[VitalKnowledge] Starting batch scrape for {len(tickers)} tickers: {tickers}")
    
    # Login once
    username = os.getenv("Vital_login")
    password = os.getenv("Vital_password")

    if not username or not password:
        raise ValueError("Missing Vital_login or Vital_password in .env")

    print("[VitalKnowledge] Navigating to login page...")
    await page.goto("https://vitalknowledge.net/login", wait_until="networkidle", timeout=30000)

    print("[VitalKnowledge] Entering credentials...")
    await page.act(f"Enter '{username}' into the username or email input field")
    await page.act(f"Enter '{password}' into the password input field")
    await page.act("Click the login or sign in button")
    await page.wait_for_load_state("networkidle", timeout=30000)
    print("[VitalKnowledge] Login successful")

    # Initialize results dictionary: ticker -> {morning_bullets: [], market_close_bullets: [], dates: []}
    ticker_data: dict[str, dict] = {ticker: {"morning_bullets": [], "market_close_bullets": [], "dates": []} for ticker in tickers}

    try:
        # ---------------------------------------------------------------------
        # MORNING REPORT - Extract for all tickers from the same report
        # ---------------------------------------------------------------------
        print("[VitalKnowledge] Navigating to morning reports...")
        await page.act("Click on the 'morning' link or button in the navigation")
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        print("[VitalKnowledge] Clicking most recent morning report...")
        # Be more specific: click the morning report with today's date or the most recent date
        today_str = datetime.now().strftime("%b %d, %Y")  # e.g., "Nov 20, 2025"
        await page.act(f"Click the morning report link that shows the date '{today_str}' or the most recent date in the list")
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Extract date from URL (same for all tickers)
        try:
            if '/article/' in page.url:
                date_parts = page.url.split('/article/')[1].split('/')[:3]
                morning_date = '-'.join(date_parts)
            else:
                morning_date = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            morning_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"[VitalKnowledge] Morning report date: {morning_date}")
        
        # Extract ticker-specific bullets for ALL tickers from the same morning report
        print(f"[VitalKnowledge] Extracting ticker-specific news from morning report for {len(tickers)} tickers...")
        for ticker in tickers:
            print(f"[VitalKnowledge] Extracting {ticker} from morning report...")
            morning_bullets_result = await page.extract(
                instruction=f"""
                Read through this Vital Knowledge morning report.

                Extract ONLY news that specifically impacts {ticker} stock.

                Return up to 5 bullet points about {ticker}. Each bullet should be:
                - Specific to {ticker} (not general market news)
                - Concise but informative (1-2 sentences)
                - Focused on what's driving {ticker} stock movement

                If there is no news about {ticker} in this report, return an empty list.
                """,
                schema=ExtractedBullets,
            )
            
            morning_bullets = morning_bullets_result.bullets if morning_bullets_result else []
            ticker_data[ticker]["morning_bullets"] = morning_bullets
            ticker_data[ticker]["dates"].append(morning_date)
            print(f"[VitalKnowledge] Found {len(morning_bullets)} bullets for {ticker} in morning report")

        # ---------------------------------------------------------------------
        # MARKET CLOSE REPORT - Extract for all tickers from the same report
        # ---------------------------------------------------------------------
        # First, ensure we navigate away from the morning report page
        print("[VitalKnowledge] Navigating to market close reports...")
        # Use goto to ensure we're on the category page first
        await page.goto("https://vitalknowledge.net/?category=market-close", wait_until="networkidle", timeout=15000)
        await asyncio.sleep(2)
        
        print("[VitalKnowledge] Clicking most recent market close report...")
        # Use observe to find the first actual article link (not the category navigation link)
        # Look for a link that has a date in it, like "Nov 19, 2025" or "Nov 20, 2025"
        observe_results = await page.observe("Find the first article link in the market close reports list that has a date like 'Nov 19, 2025' or 'Nov 20, 2025' in the link text. This should be an actual report article link, not the 'Market Close' category navigation link.")
        if observe_results:
            await page.act(observe_results[0])
        else:
            # Fallback to act if observe fails
            today_str = datetime.now().strftime("%b %d, %Y")  # e.g., "Nov 20, 2025"
            await page.act(f"Click the market close report article link (not the category link) that shows the date '{today_str}' or the most recent date in the list")
        
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Verify we're on a market close report (check URL)
        current_url = page.url
        print(f"[VitalKnowledge] Current URL after clicking market close: {current_url}")
        
        # If we're not on a market close article, try again
        if 'morning' in current_url.lower() or '/article/' not in current_url:
            print("[VitalKnowledge] WARNING: Not on market close report, retrying...")
            await page.goto("https://vitalknowledge.net/?category=market-close", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(2)
            # More specific: look for article title link, not category link
            observe_results = await page.observe("Find the first article title link in the market close reports list. This should be a link to an actual article with a date, not the 'Market Close' category navigation button.")
            if observe_results:
                await page.act(observe_results[0])
            else:
                # Final fallback
                today_str = datetime.now().strftime("%b %d, %Y")
                await page.act(f"Click the first market close article title link (the actual report, not the category button) that contains a date")
            await asyncio.sleep(3)
            await page.wait_for_load_state("networkidle", timeout=15000)
            current_url = page.url
        
        # Extract date from URL (same for all tickers)
        try:
            if '/article/' in current_url:
                date_parts = current_url.split('/article/')[1].split('/')[:3]
                market_close_date = '-'.join(date_parts)
            else:
                market_close_date = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            market_close_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"[VitalKnowledge] Market close report date: {market_close_date}")
        print(f"[VitalKnowledge] Confirmed on market close report URL: {current_url}")
        
        # Extract ticker-specific bullets for ALL tickers from the same market close report
        print(f"[VitalKnowledge] Extracting ticker-specific news from market close report for {len(tickers)} tickers...")
        for ticker in tickers:
            print(f"[VitalKnowledge] Extracting {ticker} from market close report...")
            market_close_bullets_result = await page.extract(
                instruction=f"""
                Read through this Vital Knowledge market close report.

                Extract ONLY news that specifically impacts {ticker} stock.

                Return up to 5 bullet points about {ticker}. Each bullet should be:
                - Specific to {ticker} (not general market news)
                - Concise but informative (1-2 sentences)
                - Focused on what's driving {ticker} stock movement

                If there is no news about {ticker} in this report, return an empty list.
                """,
                schema=ExtractedBullets,
            )
            
            market_close_bullets = market_close_bullets_result.bullets if market_close_bullets_result else []
            ticker_data[ticker]["market_close_bullets"] = market_close_bullets
            ticker_data[ticker]["dates"].append(market_close_date)
            print(f"[VitalKnowledge] Found {len(market_close_bullets)} bullets for {ticker} in market close report")

        # ---------------------------------------------------------------------
        # PROCESS EACH TICKER: Combine, sort, and generate summary
        # ---------------------------------------------------------------------
        results: List[VitalKnowledgeReport] = []
        
        for ticker in tickers:
            print(f"\n[VitalKnowledge] Processing {ticker}...")
            all_bullets = ticker_data[ticker]["morning_bullets"] + ticker_data[ticker]["market_close_bullets"]
            
            # Combine and sort bullets by importance (max 5 total)
            final_bullets: List[str] = []
            
            if all_bullets:
                print(f"[VitalKnowledge] Combining {len(all_bullets)} bullets for {ticker}, sorting by importance...")
                
                # Have AI sort by importance and keep top 5
                combined_result = await page.extract(
                    instruction=f"""
                    You have {len(all_bullets)} bullet points about {ticker} stock from morning and market close reports:

                    {chr(10).join(f"- {bullet}" for bullet in all_bullets)}

                    Sort these by importance (most market-moving first) and return the top 5 most important bullets.
                    If there are fewer than 5, return all of them.
                    """,
                    schema=CombinedBullets,
                )
                
                final_bullets = combined_result.top_bullets[:5] if combined_result else []
                print(f"[VitalKnowledge] Selected {len(final_bullets)} top bullets for {ticker}")

            # Generate very brief summary
            summary = None
            if final_bullets:
                print(f"[VitalKnowledge] Generating brief summary for {ticker}...")
                
                bullets_text = "\n".join(f"- {bullet}" for bullet in final_bullets)
                
                summary = await page.extract(
                    instruction=f"""
                    Based on these Vital Knowledge bullets about {ticker}:

                    {bullets_text}

                    Provide:
                    - overall_sentiment: Must be exactly one of: "bullish", "bearish", "mixed", or "neutral"
                    - key_themes: List 2-3 main themes (e.g., ["earnings", "analyst upgrade"])
                    - summary: Write a very brief 1-2 sentence summary of the key points about {ticker}
                    """,
                    schema=VitalKnowledgeSummary,
                )

            # Convert bullets to headlines for compatibility
            headlines = [
                VitalKnowledgeHeadline(
                    headline=bullet,
                    context=None,
                    sentiment=None,
                )
                for bullet in final_bullets
            ]

            # Build result
            result = VitalKnowledgeReport(
                ticker=ticker.upper(),
                headlines=headlines,
                report_dates=ticker_data[ticker]["dates"],
                summary=summary,
            )

            print(f"[VitalKnowledge] Complete! {len(final_bullets)} bullets extracted for {ticker}")
            results.append(result)

        return results

    except Exception as e:
        print(f"[VitalKnowledge] Failed in batch scrape: {e}")
        # Return empty results for all tickers on error
        return [VitalKnowledgeReport(ticker=t.upper()) for t in tickers]


async def fetch_vital_knowledge_headlines(
    page,
    ticker: str,
) -> VitalKnowledgeReport:
    """
    Fetch ticker-specific macro news from Vital Knowledge morning and market close reports.

    This function:
    1. Logs in to vitalknowledge.net
    2. Navigates to morning reports and extracts ticker-specific news (max 5 bullets)
    3. Navigates to market close reports and extracts ticker-specific news (max 5 bullets)
    4. Combines bullets, sorts by importance, keeps top 5
    5. Generates a very brief summary

    Args:
        page: A StagehandPage instance
        ticker: Stock ticker symbol (e.g., "AAPL")

    Returns:
        VitalKnowledgeReport with headlines and summary
    """
    print(f"[VitalKnowledge] Starting scrape for {ticker}")

    # Login
    username = os.getenv("Vital_login")
    password = os.getenv("Vital_password")

    if not username or not password:
        raise ValueError("Missing Vital_login or Vital_password in .env")

    print("[VitalKnowledge] Navigating to login page...")
    await page.goto("https://vitalknowledge.net/login", wait_until="networkidle", timeout=30000)

    print("[VitalKnowledge] Entering credentials...")
    await page.act(f"Enter '{username}' into the username or email input field")
    await page.act(f"Enter '{password}' into the password input field")
    await page.act("Click the login or sign in button")
    await page.wait_for_load_state("networkidle", timeout=30000)
    print("[VitalKnowledge] Login successful")

    all_bullets: List[str] = []
    report_dates: List[str] = []

    try:
        # ---------------------------------------------------------------------
        # MORNING REPORT
        # ---------------------------------------------------------------------
        print("[VitalKnowledge] Navigating to morning reports...")
        await page.act("Click on the 'morning' link or button in the navigation")
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        print("[VitalKnowledge] Clicking first morning report...")
        await page.act("Click the first morning report link in the list to open it")
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Extract date from URL
        try:
            if '/article/' in page.url:
                date_parts = page.url.split('/article/')[1].split('/')[:3]
                morning_date = '-'.join(date_parts)
            else:
                morning_date = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            morning_date = datetime.now().strftime("%Y-%m-%d")
        report_dates.append(morning_date)
        print(f"[VitalKnowledge] Morning report date: {morning_date}")
        
        # Extract ticker-specific bullets from morning report
        print(f"[VitalKnowledge] Extracting ticker-specific news from morning report...")
        morning_bullets_result = await page.extract(
            instruction=f"""
            Read through this Vital Knowledge morning report.

            Extract ONLY news that specifically impacts {ticker} stock.

            Return up to 5 bullet points about {ticker}. Each bullet should be:
            - Specific to {ticker} (not general market news)
            - Concise but informative (1-2 sentences)
            - Focused on what's driving {ticker} stock movement

            If there is no news about {ticker} in this report, return an empty list.
            """,
            schema=ExtractedBullets,
        )
        
        morning_bullets = morning_bullets_result.bullets if morning_bullets_result else []
        print(f"[VitalKnowledge] Found {len(morning_bullets)} bullets in morning report")
        all_bullets.extend(morning_bullets)

        # ---------------------------------------------------------------------
        # MARKET CLOSE REPORT
        # ---------------------------------------------------------------------
        print("[VitalKnowledge] Navigating to market close reports...")
        await page.act("Click on the 'market close' link or button in the navigation")
        await asyncio.sleep(2)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        print("[VitalKnowledge] Clicking first market close report...")
        await page.act("Click the first market close report link in the list to open it")
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Extract date from URL
        try:
            if '/article/' in page.url:
                date_parts = page.url.split('/article/')[1].split('/')[:3]
                market_close_date = '-'.join(date_parts)
            else:
                market_close_date = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            market_close_date = datetime.now().strftime("%Y-%m-%d")
        
        report_dates.append(market_close_date)
        print(f"[VitalKnowledge] Market close report date: {market_close_date}")
        
        # Extract ticker-specific bullets from market close report
        print(f"[VitalKnowledge] Extracting ticker-specific news from market close report...")
        market_close_bullets_result = await page.extract(
            instruction=f"""
            Read through this Vital Knowledge market close report.

            Extract ONLY news that specifically impacts {ticker} stock.

            Return up to 5 bullet points about {ticker}. Each bullet should be:
            - Specific to {ticker} (not general market news)
            - Concise but informative (1-2 sentences)
            - Focused on what's driving {ticker} stock movement

            If there is no news about {ticker} in this report, return an empty list.
            """,
            schema=ExtractedBullets,
        )
        
        market_close_bullets = market_close_bullets_result.bullets if market_close_bullets_result else []
        print(f"[VitalKnowledge] Found {len(market_close_bullets)} bullets in market close report")
        all_bullets.extend(market_close_bullets)

        # ---------------------------------------------------------------------
        # COMBINE AND SORT BULLETS BY IMPORTANCE (MAX 5 TOTAL)
        # ---------------------------------------------------------------------
        final_bullets: List[str] = []
        
        if all_bullets:
            print(f"[VitalKnowledge] Combining {len(all_bullets)} bullets, sorting by importance...")
            
            # Have AI sort by importance and keep top 5
            combined_result = await page.extract(
                instruction=f"""
                You have {len(all_bullets)} bullet points about {ticker} stock from morning and market close reports:

                {chr(10).join(f"- {bullet}" for bullet in all_bullets)}

                Sort these by importance (most market-moving first) and return the top 5 most important bullets.
                If there are fewer than 5, return all of them.
                """,
                schema=CombinedBullets,
            )
            
            final_bullets = combined_result.top_bullets[:5] if combined_result else []
            print(f"[VitalKnowledge] Selected {len(final_bullets)} top bullets")

        # ---------------------------------------------------------------------
        # GENERATE VERY BRIEF SUMMARY
        # ---------------------------------------------------------------------
        summary = None
        if final_bullets:
            print("[VitalKnowledge] Generating brief summary...")
            
            bullets_text = "\n".join(f"- {bullet}" for bullet in final_bullets)
            
            summary = await page.extract(
                instruction=f"""
                Based on these Vital Knowledge bullets about {ticker}:

                {bullets_text}

                Provide:
                - overall_sentiment: Must be exactly one of: "bullish", "bearish", "mixed", or "neutral"
                - key_themes: List 2-3 main themes (e.g., ["earnings", "analyst upgrade"])
                - summary: Write a very brief 1-2 sentence summary of the key points about {ticker}
                """,
                schema=VitalKnowledgeSummary,
            )

        # ---------------------------------------------------------------------
        # CONVERT BULLETS TO HEADLINES FOR COMPATIBILITY
        # ---------------------------------------------------------------------
        headlines = [
            VitalKnowledgeHeadline(
                headline=bullet,
                context=None,
                sentiment=None,
            )
            for bullet in final_bullets
        ]

        # ---------------------------------------------------------------------
        # RETURN RESULTS
        # ---------------------------------------------------------------------
        result = VitalKnowledgeReport(
            ticker=ticker.upper(),
            headlines=headlines,
            report_dates=report_dates,
            summary=summary,
        )

        print(f"\n[VitalKnowledge] Complete! {len(final_bullets)} bullets extracted for {ticker}")

        return result

    except Exception as e:
        print(f"[VitalKnowledge] Failed for {ticker}: {e}")
        return VitalKnowledgeReport(ticker=ticker.upper())


# =============================================================================
# STANDALONE TEST FUNCTION
# =============================================================================

async def test_vital_knowledge(tickers: List[str] = None):
    """
    Test the Vital Knowledge scraper standalone with multiple tickers.

    Usage (from morning_report_copy directory):
        python -m src.skills.vital_knowledge.research

    Reads tickers from config/watchlist.json if not provided.
    """
    import json
    from pathlib import Path
    from src.core.stagehand_runner import create_stagehand_session

    # Load tickers from watchlist if not provided
    if tickers is None:
        watchlist_path = Path(__file__).parent.parent.parent.parent / "config" / "watchlist.json"
        with open(watchlist_path) as f:
            tickers = json.load(f)

    print(f"\n{'='*60}")
    print(f"Testing Vital Knowledge scraper for {len(tickers)} tickers")
    print(f"Tickers: {tickers}")
    print(f"{'='*60}\n")

    stagehand = None

    try:
        stagehand, page = await create_stagehand_session()

        # Use batch function to process all tickers from the same reports
        print(f"\n{'='*60}")
        print(f"Processing all {len(tickers)} tickers in batch (same reports)")
        print(f"{'='*60}\n")

        all_results = await fetch_vital_knowledge_headlines_batch(page, tickers)

        # Print results for each ticker
        for result in all_results:
            print(f"\n{'='*60}")
            print(f"Results for {result.ticker}")
            print(f"{'='*60}\n")
            print(f"Report Dates: {result.report_dates}")
            print(f"Bullets found: {len(result.headlines)}\n")

            for i, headline in enumerate(result.headlines, 1):
                print(f"Bullet {i}: {headline.headline}")

            if result.summary:
                print(f"\nSummary: {result.summary.summary}")
                print(f"Sentiment: {result.summary.overall_sentiment}")

        # Final summary
        print(f"\n{'='*60}")
        print("FINAL SUMMARY")
        print(f"{'='*60}\n")

        for result in all_results:
            print(f"{result.ticker}: {len(result.headlines)} bullets")
            if result.summary and result.summary.summary:
                print(f"  > {result.summary.summary[:150]}...")
            print()

        return all_results

    finally:
        if stagehand:
            await stagehand.close()
            print(f"\n[VitalKnowledge] Browser session closed")


# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()
    # Reads tickers from config/watchlist.json automatically
    asyncio.run(test_vital_knowledge())
