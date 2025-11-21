# src/skills/googlenews/research.py
#
# This script scrapes Google News for stock-related articles using Stagehand
# (AI-powered browser automation). It navigates through Google Search,
# filters by recent/sorted by date, visits each article, and extracts summaries.

# =============================================================================
# IMPORTS
# =============================================================================

from typing import List, Optional, Literal
from datetime import datetime, timedelta
import asyncio

# Pydantic is used for data validation and creating structured models
# that Stagehand's AI can populate from web page content
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# DATA MODELS (Pydantic)
# =============================================================================
# These models define the structure of data we want to extract.
# Maintains same patterns as yahoo/research.py for seamless integration.

class GoogleNewsStory(BaseModel):
    """
    Represents one news article with its URL and summary.
    Each story contains the article URL and a brief summary of content.
    """

    # Core article info
    headline: str = Field(..., description="Article headline/title")
    url: str = Field(..., description="Full URL to the article")
    source: Optional[str] = Field(default=None, description="Publisher/source name")
    age: Optional[str] = Field(default=None, description="Time indicator like '2 hours ago'")

    # Content summary - extracted by visiting the article
    summary: Optional[str] = Field(
        default=None,
        description="Brief summary of why the stock is moving based on article content",
    )

    # AI-analyzed fields
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = Field(
        default=None,
        description="Sentiment of the article (positive, negative, or neutral)",
    )


class GoogleNewsSummary(BaseModel):
    """
    AI-generated summary across ALL stories for a ticker.
    Provides a high-level view of the news narrative.
    """
    
    model_config = ConfigDict(populate_by_name=True)

    overall_sentiment: Optional[Literal["bullish", "bearish", "mixed", "neutral"]] = Field(
        default=None,
        alias="overallSentiment",
        description="Overall sentiment across all stories",
    )
    bullet_points: List[str] = Field(
        default_factory=list,
        alias="bulletPoints",
        description="4 bullet points of the most important, current market news for the ticker",
    )


class GoogleNewsTopStories(BaseModel):
    """
    Container that holds all extracted data for a single stock ticker.
    This is the main object returned by fetch_google_news_stories().
    """

    ticker: str
    stories: List[GoogleNewsStory] = Field(default_factory=list)
    news_summary: Optional[GoogleNewsSummary] = Field(default=None)


# Helper model for extracting article links from search results
class ArticleLink(BaseModel):
    """Temporary model for extracting article links before visiting them."""
    headline: str
    url: str
    source: Optional[str] = None
    age: Optional[str] = None


class ArticleLinks(BaseModel):
    """Container for extracted article links."""
    articles: List[ArticleLink] = Field(default_factory=list)


# =============================================================================
# MAIN SCRAPING FUNCTION
# =============================================================================

async def fetch_google_news_stories(
    page,                          # Stagehand page object (browser tab)
    ticker: str,                   # Stock ticker symbol (e.g., "AAPL")
    max_stories: int = 5,          # How many articles to visit (default: 5)
    max_days: int = 2,             # Only get news from last N days
) -> GoogleNewsTopStories:
    """
    Fetch top news stories from Google News for a given stock ticker.

    This function:
    1. Navigates directly to Google News search with date filter and sort by date
    2. Extracts article links (limited to last N days)
    3. Visits each article and extracts a summary
    4. Returns structured data with URLs and summaries

    Args:
        page: A StagehandPage instance (the browser tab to use)
        ticker: Stock ticker symbol (e.g., "AAPL")
        max_stories: Maximum number of articles to visit (default: 5)
        max_days: Only include articles from last N days (default: 2)

    Returns:
        GoogleNewsTopStories with list of stories containing URLs and summaries
    """

    search_query = f"{ticker} stock news"
    
    # Build Google News URL with filters directly in query parameters:
    # - tbm=nws: News tab
    # - tbs=qdr:d{max_days}: Filter to last N days (qdr:d1 = 1 day, qdr:d2 = 2 days, etc.)
    # - tbs=sbd:1: Sort by date (newest first)
    url = (
        f"https://www.google.com/search?"
        f"q={search_query.replace(' ', '+')}"
        f"&tbm=nws"
        f"&tbs=qdr:d{max_days},sbd:1"
    )

    print(f"[GoogleNews] Navigating to Google News for '{search_query}'")
    print(f"[GoogleNews] URL: {url}")

    # Initialize stories list before try block so it's available in exception handler
    stories: List[GoogleNewsStory] = []

    try:
        # Navigate directly to filtered Google News results
        await page.goto(url, wait_until="networkidle", timeout=30000)
        print(f"[GoogleNews] News results loaded")

        # ---------------------------------------------------------------------
        # Extract article links from search results
        # ---------------------------------------------------------------------
        # Use a hybrid approach: Stagehand extract() for content, observe() for URLs

        print(f"[GoogleNews] Extracting article links...")

        # First, use Stagehand to identify and extract article metadata
        # This works well for visible content like headlines, sources, ages
        article_metadata = await page.extract(
            instruction=f"""
            Find the top {max_stories} news article headlines from Google News search results.

            For each article, extract:
            - headline: The article title/headline text
            - source: The publisher name (e.g., "Reuters", "CNBC", "Yahoo Finance")
            - age: How old the article is (e.g., "2 hours ago", "1 day ago")

            ONLY extract articles that are within the last {max_days} days.
            Do NOT include older articles.

            Return the articles in order of relevance and recency.
            """,
            schema=ArticleLinks,
        )

        # Now use JavaScript to get ALL links and match them to headlines
        # This works around Stagehand's difficulty with href extraction
        all_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a').forEach(link => {
                    const href = link.href;
                    const text = link.textContent.trim();
                    if (href && href.startsWith('http') && text.length > 15) {
                        links.push({ url: href, text: text });
                    }
                });
                return links;
            }
        """)

        # Match extracted headlines with actual URLs
        articles = []
        for article in article_metadata.articles:
            # Find matching URL by headline text
            matching_link = None
            for link in all_links:
                # Check if link text contains significant portion of headline
                if article.headline[:30].lower() in link['text'].lower():
                    matching_link = link['url']
                    break

            if matching_link:
                articles.append(ArticleLink(
                    headline=article.headline,
                    url=matching_link,
                    source=article.source,
                    age=article.age
                ))

        article_links = ArticleLinks(articles=articles)
        print(f"[GoogleNews] Found {len(article_links.articles)} articles to visit")

        # ---------------------------------------------------------------------
        # Visit each article and extract summary (SEQUENTIALLY)
        # ---------------------------------------------------------------------
        # Note: Browserbase doesn't support concurrent tabs well, so we process
        # articles sequentially. This is still faster than the old approach because
        # we removed the back-and-forth navigation and observe/click overhead.

        print(f"\n[GoogleNews] Processing {min(len(article_links.articles), max_stories)} articles sequentially...")

        for i, article in enumerate(article_links.articles[:max_stories]):
            print(f"\n[GoogleNews] [{i+1}/{min(len(article_links.articles), max_stories)}] Visiting: {article.headline[:60]}...")
            print(f"[GoogleNews] URL: {article.url}")

            try:
                # Navigate directly to article URL (no clicking, no going back)
                await page.goto(article.url, wait_until="load", timeout=30000)
                print(f"[GoogleNews] [{i+1}] Page loaded")

                # Extract summary
                summary_data = await page.extract(
                    instruction=f"""
                    Read this news article about {ticker} stock.
                    Write a brief 2-3 sentence summary explaining:
                    - What is the main news/event?
                    - Why is this causing {ticker} stock to move?
                    - Is this positive, negative, or neutral for the stock?
                    Be factual and concise. Only use information from this article.
                    Return:
                    - summary: Your 2-3 sentence summary
                    - sentiment: "positive", "negative", or "neutral"
                    """,
                    schema=GoogleNewsStory,
                )

                # Create the story object
                story = GoogleNewsStory(
                    headline=article.headline,
                    url=page.url,  # Use final URL after any redirects
                    source=article.source,
                    age=article.age,
                    summary=summary_data.summary if hasattr(summary_data, 'summary') else None,
                    sentiment=summary_data.sentiment if hasattr(summary_data, 'sentiment') else None,
                )

                stories.append(story)
                print(f"[GoogleNews] OK Summary: {story.summary[:80] if story.summary else 'N/A'}...")

            except Exception as e:
                print(f"[GoogleNews] ERROR processing article: {e}")
                # Still add article with basic info
                stories.append(GoogleNewsStory(
                    headline=article.headline,
                    url=article.url,
                    source=article.source,
                    age=article.age,
                    summary=None,
                    sentiment=None,
                ))

        print(f"\n[GoogleNews] Processed {len(stories)} articles ({len([s for s in stories if s.summary])} with summaries)")

        # ---------------------------------------------------------------------
        # Generate overall summary
        # ---------------------------------------------------------------------

        overall = None
        try:
            print(f"\n[GoogleNews] Generating overall summary...")

            # Combine all summaries for analysis
            all_summaries = "\n".join([
                f"- {s.headline}: {s.summary}"
                for s in stories
                if s.summary and not s.summary.startswith("Error")
            ])

            if all_summaries:
                # Navigate to a simple page for the AI to think
                # Wrap in try/except in case browser crashes during summary generation
                try:
                    overall = await page.extract(
                        instruction=f"""
                        Based on these {len([s for s in stories if s.summary and not s.summary.startswith("Error")])} news articles about {ticker} stock:

                        {all_summaries}

                        Provide:
                        - overall_sentiment: Is the overall news "bullish", "bearish", "mixed", or "neutral"?
                        - bullet_points: Provide exactly 4 bullet points of the most important, current market news for {ticker}. Each bullet should be concise (1-2 sentences) and focus on actionable market-moving information.
                        """,
                        schema=GoogleNewsSummary,
                    )
                except Exception as summary_error:
                    print(f"[GoogleNews] Error generating summary (continuing with stories): {summary_error}")
                    overall = None
        except Exception as e:
            print(f"[GoogleNews] Error in summary generation section (continuing with stories): {e}")
            overall = None

        # ---------------------------------------------------------------------
        # Return results - always return stories we successfully collected
        # ---------------------------------------------------------------------

        result = GoogleNewsTopStories(
            ticker=ticker.upper(),
            stories=stories,
            news_summary=overall,
        )

        successful_count = len([s for s in stories if s.summary and not s.summary.startswith("Error")])
        print(f"\n[GoogleNews] Complete! {len(stories)} stories collected, {successful_count} with summaries")

        return result

    except Exception as e:
        print(f"[GoogleNews] Fatal error for {ticker}: {e}")
        # Return whatever stories we managed to collect before the fatal error
        # This ensures we don't lose all the work if something crashes late
        if stories:
            successful_count = len([s for s in stories if s.summary and not s.summary.startswith("Error")])
            print(f"[GoogleNews] Returning {len(stories)} stories collected ({successful_count} with summaries) before error")
            return GoogleNewsTopStories(
                ticker=ticker.upper(),
                stories=stories,
                news_summary=None,
            )
        else:
            print(f"[GoogleNews] No stories collected, returning empty result")
            return GoogleNewsTopStories(ticker=ticker.upper(), stories=[])


# =============================================================================
# STANDALONE TEST FUNCTION
# =============================================================================

async def test_google_news(ticker: str = "AAPL"):
    """
    Test the Google News scraper standalone.

    Usage (from morning_report_copy directory):
        python -m src.skills.googlenews.research

    This will:
    1. Create a Browserbase browser session
    2. Search Google News for the ticker
    3. Visit top articles and extract summaries
    4. Print URLs and summaries
    5. Close the browser
    """
    import json
    from src.core.stagehand_runner import create_stagehand_session

    print(f"\n{'='*60}")
    print(f"Testing Google News scraper for {ticker}")
    print(f"{'='*60}\n")

    stagehand = None
    try:
        stagehand, page = await create_stagehand_session()

        result = await fetch_google_news_stories(
            page,
            ticker,
            max_stories=5,
            max_days=2,
        )

        # Print results
        print(f"\n{'='*60}")
        print("RESULTS")
        print(f"{'='*60}\n")

        print(f"Ticker: {result.ticker}")

        if result.news_summary:
            print(f"\n--- Google News Summary ---")
            print(f"Articles Analyzed: {len([s for s in result.stories if s.summary and not s.summary.startswith('Error')])}")
            print(f"Sentiment: {result.news_summary.overall_sentiment}")
            if result.news_summary.bullet_points:
                print(f"\nKey Market News:")
                for bullet in result.news_summary.bullet_points:
                    print(f"  • {bullet}")
        else:
            print(f"\nNo summary available. Stories found: {len(result.stories)}")

        return result

    finally:
        if stagehand:
            await stagehand.close()
            print(f"\n[GoogleNews] Browser session closed")


# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()
    asyncio.run(test_google_news("AAPL"))
