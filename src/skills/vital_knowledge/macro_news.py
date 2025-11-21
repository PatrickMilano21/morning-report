# src/skills/vital_knowledge/macro_news.py
#
# This script scrapes Vital Knowledge for macro market-moving news.
# It extracts morning and market close macro summaries with detailed bullets.
# This is independent from ticker-specific research and runs separately.

import asyncio
import os
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# =============================================================================
# DATA MODELS (Pydantic)
# =============================================================================

class MacroNewsSummary(BaseModel):
    """Container for morning and market close macro news summaries."""
    morning_date: Optional[str] = Field(default=None, description="Date of morning report")
    morning_url: Optional[str] = Field(default=None, description="URL of morning report")
    morning_summary: Optional[str] = Field(default=None, description="Morning macro market moving news summary (2-3 sentences)")
    morning_bullets: List[str] = Field(default_factory=list, description="4-5 detailed bullet points of morning macro news")

    market_close_date: Optional[str] = Field(default=None, description="Date of market close report")
    market_close_url: Optional[str] = Field(default=None, description="URL of market close report")
    market_close_summary: Optional[str] = Field(default=None, description="Market close macro market moving news summary (2-3 sentences)")
    market_close_bullets: List[str] = Field(default_factory=list, description="4-5 detailed bullet points of market close macro news")


class MacroExtract(BaseModel):
    """Helper model for extracting macro news from a report."""
    summary: str = Field(..., description="2-3 sentence summary of macro market moving news")
    bullets: List[str] = Field(..., description="4-5 detailed bullet points of what's driving market moves")


# =============================================================================
# MAIN SCRAPING FUNCTION
# =============================================================================

async def fetch_macro_news(page) -> MacroNewsSummary:
    """
    Fetch macro market-moving news from Vital Knowledge morning and market close reports.

    This function:
    1. Logs in to vitalknowledge.net
    2. Navigates to morning reports
    3. Extracts macro news summary and bullets from first morning report
    4. Navigates to market close reports
    5. Extracts macro news summary and bullets from first market close report
    6. Returns structured data with both summaries and bullets

    Args:
        page: A StagehandPage instance

    Returns:
        MacroNewsSummary with morning and market close summaries and bullets
    """
    print("[MacroNews] Starting macro news scrape")

    # ========================================================================
    # STEP 1: LOGIN TO VITAL KNOWLEDGE
    # ========================================================================
    # Get credentials from environment variables
    # These should be set in .env file as Vital_login and Vital_password
    username = os.getenv("Vital_login")
    password = os.getenv("Vital_password")

    # Validate credentials exist before attempting login
    if not username or not password:
        raise ValueError("Missing Vital_login or Vital_password in .env")

    # Navigate to login page and wait for it to fully load
    # Using networkidle ensures all resources (JS, CSS, etc.) are loaded
    print("[MacroNews] Navigating to login page...")
    await page.goto("https://vitalknowledge.net/login", wait_until="networkidle", timeout=30000)

    # Enter credentials using Stagehand's act() method
    # Stagehand AI will find the username/email input field and type into it
    print("[MacroNews] Entering credentials...")
    await page.act(f"Enter '{username}' into the username or email input field")
    await page.act(f"Enter '{password}' into the password input field")
    
    # Click the login button - Stagehand will find and click it
    await page.act("Click the login or sign in button")
    
    # Wait for navigation to complete after login
    # This ensures we're fully logged in before proceeding
    await page.wait_for_load_state("networkidle", timeout=30000)
    print("[MacroNews] Login successful")

    try:
        # ========================================================================
        # STEP 2: MORNING REPORT EXTRACTION
        # ========================================================================
        # Navigate to the morning reports category page
        # This filters the reports list to show only morning reports
        print("[MacroNews] Navigating to morning reports...")
        await page.act("Click on the 'morning' link or button in the navigation")
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Click the first (most recent) morning report in the list
        # NOTE: This uses act() directly, which relies on Stagehand AI to find the link
        # This could be inconsistent (same issue as research.py had)
        # Consider using observe() + act() pattern for more reliability
        print("[MacroNews] Clicking first morning report...")
        await page.act("Click the first morning report link in the list to open it")
        
        # Wait for the article page to load
        # The 3-second sleep gives time for any JavaScript to render content
        # networkidle ensures all network requests complete
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Extract the date from the URL
        # Vital Knowledge URLs are in format: /article/2025/11/20/...
        # We extract the year/month/day parts and format as YYYY-MM-DD
        morning_url = page.url  # Store full URL for reference/debugging
        try:
            if '/article/' in page.url:
                # Split URL to get date parts: ['2025', '11', '20', ...]
                date_parts = page.url.split('/article/')[1].split('/')[:3]
                morning_date = '-'.join(date_parts)  # Format as '2025-11-20'
            else:
                # Fallback: if URL format is unexpected, use today's date
                morning_date = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            # If date extraction fails for any reason, use today's date as fallback
            morning_date = datetime.now().strftime("%Y-%m-%d")
        print(f"[MacroNews] Morning report date: {morning_date}")
        print(f"[MacroNews] Morning report URL: {morning_url}")
        
        # Extract macro news from the morning report using Stagehand's extract() method
        # This uses AI to read the entire report and extract:
        # 1. A 2-3 sentence summary of macro market-moving news
        # 2. 4-5 detailed bullet points with specific numbers/percentages
        # The instruction focuses on macro-level news (not ticker-specific)
        print("[MacroNews] Extracting morning macro news...")
        morning_result = await page.extract(
            instruction="""
            Read through this Vital Knowledge morning report.

            Extract the MORNING MACRO MARKET MOVING NEWS.

            Focus on:
            - Major market movements and trends (use percentages for any market moves versus $ or bps)
            - Key economic indicators and data releases
            - Central bank actions or policy updates
            - Geopolitical events affecting markets
            - Major sector movements and why
            - Market sentiment and outlook and why 

            Provide:
            - summary: A 2-3 sentence summary of the macro market environment and key moving forces
            - bullets: Exactly 4-5 detailed bullet points of what's driving market moves today. Each bullet should be specific with numbers, percentages, and concrete details where mentioned.
            """,
            schema=MacroExtract,  # Pydantic model that validates the extracted data structure
        )
        
        # Extract the summary and bullets from the result
        # Handle None case in case extraction fails
        morning_summary = morning_result.summary if morning_result else None
        # Limit to 5 bullets max (instruction says 4-5, but we cap at 5)
        morning_bullets = morning_result.bullets[:5] if morning_result and morning_result.bullets else []
        print(f"[MacroNews] Morning: {len(morning_bullets)} bullets extracted")

        # ========================================================================
        # STEP 3: MARKET CLOSE REPORT EXTRACTION
        # ========================================================================
        # Navigate away from morning report to the market close reports category
        # This filters the reports list to show only market close reports
        print("[MacroNews] Navigating to market close reports...")
        await page.act("Click on the 'market close' link or button in the navigation")
        
        # Wait for navigation to complete
        # Using 2-second sleep (different from morning's 3 seconds - inconsistency?)
        await asyncio.sleep(2)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Click the first (most recent) market close report in the list
        # NOTE: Same potential issue as morning - using act() directly
        # Consider using observe() + act() pattern like research.py does
        # Also note: research.py uses page.goto() + observe() for market close
        print("[MacroNews] Clicking first market close report...")
        await page.act("Click the first market close report link in the list to open it")
        
        # Wait for the article page to load
        await asyncio.sleep(3)
        await page.wait_for_load_state("networkidle", timeout=15000)
        
        # Extract the date from the URL (same logic as morning report)
        # Format: /article/2025/11/19/... -> '2025-11-19'
        market_close_url = page.url  # Store full URL for reference/debugging
        try:
            if '/article/' in page.url:
                date_parts = page.url.split('/article/')[1].split('/')[:3]
                market_close_date = '-'.join(date_parts)
            else:
                # Fallback: if URL format is unexpected, use today's date
                market_close_date = datetime.now().strftime("%Y-%m-%d")
        except Exception:
            # If date extraction fails, use today's date as fallback
            market_close_date = datetime.now().strftime("%Y-%m-%d")
        print(f"[MacroNews] Market close report date: {market_close_date}")
        print(f"[MacroNews] Market close report URL: {market_close_url}")
        
        # Extract macro news from the market close report
        # Same extraction logic as morning report, but focuses on market close content
        # The instruction is identical to morning - could be extracted to a constant/helper
        print("[MacroNews] Extracting market close macro news...")
        market_close_result = await page.extract(
            instruction="""
            Read through this Vital Knowledge market close report.

            Extract the MARKET CLOSE MACRO MARKET MOVING NEWS.

            Focus on:
            - Major market movements and trends (use percentages for any market moves versus $ or bps)
            - Key economic indicators and data releases
            - Central bank actions or policy updates
            - Geopolitical events affecting markets
            - Major sector movements and why
            - Market sentiment and outlook and why 

            Provide:
            - summary: A 2-3 sentence summary of the macro market environment and key moving forces
            - bullets: Exactly 4-5 detailed bullet points of what's driving market moves today. Each bullet should be specific with numbers, percentages, and concrete details where mentioned.
            """,
            schema=MacroExtract,  # Same Pydantic model as morning extraction
        )
        
        # Extract the summary and bullets from the result
        # Handle None case in case extraction fails
        market_close_summary = market_close_result.summary if market_close_result else None
        # Limit to 5 bullets max (instruction says 4-5, but we cap at 5)
        market_close_bullets = market_close_result.bullets[:5] if market_close_result and market_close_result.bullets else []
        print(f"[MacroNews] Market close: {len(market_close_bullets)} bullets extracted")

        # ========================================================================
        # STEP 4: BUILD AND RETURN RESULTS
        # ========================================================================
        # Create the MacroNewsSummary object with all extracted data
        # This includes both morning and market close reports separately
        # URLs are included but may not be used in final report
        result = MacroNewsSummary(
            morning_date=morning_date,
            morning_url=morning_url,
            morning_summary=morning_summary,
            morning_bullets=morning_bullets,
            market_close_date=market_close_date,
            market_close_url=market_close_url,
            market_close_summary=market_close_summary,
            market_close_bullets=market_close_bullets,
        )
        
        print("[MacroNews] Complete!")
        return result

    except Exception as e:
        # If any error occurs during the process, catch it and return empty result
        # NOTE: This is a broad catch-all - might want more specific error handling
        # Also note: If morning succeeds but market close fails, we lose morning data
        # Could be improved to return partial results
        print(f"[MacroNews] Failed: {e}")
        return MacroNewsSummary()  # Return empty summary on any error


# =============================================================================
# STANDALONE TEST FUNCTION
# =============================================================================

async def test_macro_news():
    """
    Test the Macro News scraper standalone.

    Usage (from morning_report_copy directory):
        python -m src.skills.vital_knowledge.macro_news
    
    This function:
    1. Creates a browser session using Stagehand
    2. Calls fetch_macro_news() to scrape both reports
    3. Prints the results in a formatted way
    4. Closes the browser session
    """
    from src.core.stagehand_runner import create_stagehand_session

    print(f"\n{'='*60}")
    print("Testing Vital Knowledge Macro News Scraper")
    print(f"{'='*60}\n")

    stagehand = None
    try:
        # Create a new browser session for testing
        # This is separate from the main morning snapshot pipeline
        stagehand, page = await create_stagehand_session()
        
        # Run the macro news scraper
        # This will login, navigate, extract, and return results
        result = await fetch_macro_news(page)

        # ========================================================================
        # PRINT RESULTS FOR REVIEW
        # ========================================================================
        # Display the extracted data in a readable format
        # Shows both morning and market close reports separately
        print(f"\n{'='*60}")
        print("RESULTS")
        print(f"{'='*60}\n")

        # Print morning report results if available
        # Checks for both date and summary to ensure we have valid data
        if result.morning_date and result.morning_summary:
            print(f"--- Morning Report ({result.morning_date}) ---")
            print(f"Summary: {result.morning_summary}\n")
            if result.morning_bullets:
                print("Key Points:")
                # Number each bullet point for readability
                for i, bullet in enumerate(result.morning_bullets, 1):
                    print(f"  {i}. {bullet}")
            # Print URL if available (for debugging/reference)
            if result.morning_url:
                print(f"\nReport Link: {result.morning_url}")
            print()
        else:
            # If morning report extraction failed or returned no data
            print("--- Morning Report: Not available ---\n")

        # Print market close report results if available
        # Same structure as morning report
        if result.market_close_date and result.market_close_summary:
            print(f"--- Market Close Report ({result.market_close_date}) ---")
            print(f"Summary: {result.market_close_summary}\n")
            if result.market_close_bullets:
                print("Key Points:")
                # Number each bullet point for readability
                for i, bullet in enumerate(result.market_close_bullets, 1):
                    print(f"  {i}. {bullet}")
            # Print URL if available (for debugging/reference)
            if result.market_close_url:
                print(f"\nReport Link: {result.market_close_url}")
            print()
        else:
            # If market close report extraction failed or returned no data
            print("--- Market Close Report: Not available ---\n")

        return result

    finally:
        # Always close the browser session, even if an error occurred
        # This ensures resources are cleaned up properly
        if stagehand:
            await stagehand.close()
            print("\n[MacroNews] Browser session closed")


# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    asyncio.run(test_macro_news())
