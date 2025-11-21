# src/skills/marketwatch/research.py

from typing import List, Optional

from pydantic import BaseModel, Field


class NewsLink(BaseModel):
    """Simple model for extracting just the link information (before visiting the article)."""

    headline: str = Field(..., description="Article headline/title")
    url: Optional[str] = Field(default=None, description="Link to the full article")
    source: Optional[str] = Field(default=None, description="Publisher/source if visible")
    age: Optional[str] = Field(default=None, description="Time indicator like '2 hours ago'")


class MarketWatchStory(BaseModel):
    """One story from MarketWatch about the stock (with full article content)."""

    headline: str = Field(..., description="Article headline/title")
    url: Optional[str] = Field(default=None, description="Link to the full article")
    source: Optional[str] = Field(default=None, description="Publisher/source if visible")
    age: Optional[str] = Field(default=None, description="Time indicator like '2 hours ago'")
    summary: Optional[str] = Field(
        default=None,
        description="2-3 sentence summary of what the article says about this stock",
    )
    keyPoints: List[str] = Field(
        default_factory=list,
        description="3-5 short bullet points with key takeaways for the stock",
    )


class MarketWatchTopStories(BaseModel):
    """Container for MarketWatch top stories for a given ticker."""

    ticker: str
    stories: List[MarketWatchStory] = Field(default_factory=list)


async def fetch_marketwatch_top_stories(
    page,
    ticker: str,
    max_cards: int = 3,
) -> MarketWatchTopStories:
    """
    Attempt to fetch top stories from MarketWatch for a given ticker.
    
    NOTE: MarketWatch uses DataDome bot protection which blocks automated access
    even with Basic Stealth Mode. This function attempts to navigate and extract
    content, but typically returns empty results due to blocking.
    
    What we tried to make it work:
    - Basic Stealth Mode (enabled automatically on Startup+ plans)
    - Proxies enabled (recommended for CAPTCHA solving)
    - Waiting up to 60 seconds for DataDome/blocking to complete
    - Listening for CAPTCHA solving events (browserbase-solving-started/finished)
    - Extracting with iframes=True to access DataDome iframe content
    - Checking for URL redirects after blocking completes
    - Checking for page content loading after blocking
    
    Result: DataDome protection is too aggressive for Basic Stealth Mode.
    MarketWatch consistently blocks access with a DataDome Device Check iframe.
    
    Potential solutions (not implemented):
    - Advanced Stealth Mode (requires Scale Plan) - might help but not guaranteed
    - Browserbase Identity (requires Scale Plan, beta) - if MarketWatch uses Cloudflare
    - Focus on Yahoo Finance instead (works with Basic Stealth)
    """
    url = f"https://www.marketwatch.com/investing/stock/{ticker.lower()}"
    print(f"[MarketWatch] Navigating to {url}")
    
    try:
        # Navigate to MarketWatch
        await page.goto(url, wait_until="networkidle", timeout=30000)
        print(f"[MarketWatch] Navigation completed")
        
        # Attempt to extract any text from the page
        # Note: This typically fails because MarketWatch shows a DataDome Device Check iframe
        # that blocks access. The page body is empty (0 characters) and contains only
        # the DataDome iframe which is not accessible for extraction.
        print(f"[MarketWatch] Attempting to extract content...")
        text = await page.extract(
            "Extract any visible text from this page, including content in iframes.",
            iframes=True,  # Try to access DataDome iframe (usually doesn't work)
        )
        
        # Check if we got any content
        if text and hasattr(text, 'extraction') and text.extraction:
            print(f"[MarketWatch] Successfully extracted content")
            # TODO: Parse extracted content into MarketWatchStory objects
        else:
            print(f"[MarketWatch] No content extracted - likely blocked by DataDome")
        
        return MarketWatchTopStories(ticker=ticker.upper(), stories=[])
        
    except Exception as e:
        print(f"[MarketWatch] Failed: {e}")
        return MarketWatchTopStories(ticker=ticker.upper(), stories=[])
