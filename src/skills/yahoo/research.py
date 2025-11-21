# src/skills/yahoo/research.py

from typing import Optional, List

from pydantic import BaseModel, Field


class YahooAIAnalysis(BaseModel):
    """
    Structured view of Yahoo's AI / 'Why is this stock moving?' analysis.
    """

    ticker: str

    title: Optional[str] = None
    updated_at: Optional[str] = Field(default=None, alias="updatedAt")
    summary: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)


async def fetch_yahoo_ai_analysis(page, ticker: str) -> YahooAIAnalysis:
    """
    Use Stagehand to open the AI analysis / 'Why is this stock moving?'
    card for `ticker` and extract a compact summary plus bullet points.
    """
    url = f"https://finance.yahoo.com/quote/{ticker}"
    
    # Always navigate to ensure clean page state (in case we're already on the page from quote extraction)
    # This ensures we start with a fresh page load
    await page.goto(url, wait_until="load", timeout=30000)
    
    # Give the page a moment to fully render dynamic content
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        # If networkidle times out, that's okay - page might still be usable
        pass
    await page.wait_for_timeout(2000)  # Additional wait for dynamic content

    # Try to open the AI Analysis / Why it's moving card if there is a toggle/tab.
    # We keep this atomic and let Stagehand plan the click.
    panel_opened = False
    try:
        results = await page.observe(
            instruction=f"""
            If the page has a tab, button, or link labeled something like
            'AI Analysis', 'Why is this stock moving?', or
            'Why is {ticker} moving today?', select the best element to open
            that analysis card.
            """
        )
        if results:
            await page.act(results[0])
            panel_opened = True
            # Wait for the AI analysis content to fully load after clicking
            # Increased to 5 seconds to ensure content is fully rendered
            await page.wait_for_timeout(5000)
            # Try to wait for any dynamic content to settle
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # Networkidle timeout is okay
    except Exception as e:
        # If observe/act fails, we still try to extract text from whatever is visible
        print(f"[YahooAI] Could not open AI analysis panel (will try to extract anyway): {e}")

    # Extract the analysis with better error handling
    # Wrap the entire extraction in a try/except to catch any API errors
    try:
        # Add a small delay before extraction to ensure page is stable
        await page.wait_for_timeout(1000)
        
        analysis = await page.extract(
            instruction=f"""
            On this Yahoo Finance page for {ticker}, locate the AI-driven analysis
            or 'Why is this stock moving?' style explanation.

            Extract:
            - title: the heading of the AI / why-it's-moving panel, if present
            - updated_at: any 'Updated ...' or similar timestamp text, without extra labels
            - summary: 2–4 sentence plain-language explanation of why the stock is
              moving today. Paraphrase from the visible text, do not invent facts.
            - bullets: 3–5 short bullet points capturing concrete drivers (news,
              earnings, macro events, analyst actions, etc).

            Focus on today's drivers and short-term context. Avoid long-term
            backtests, generic product descriptions, and DCF/valuation breakdowns.
            Use only text visible on this page; do not make up information.
            
            If the AI analysis panel is not visible or not yet loaded, return empty values.
            """,
            schema=YahooAIAnalysis,
        )
        analysis.ticker = ticker.upper()
        return analysis
    except Exception as e:
        # If extraction fails, return an empty analysis object rather than crashing
        # This catches API errors, timeout errors, and any other extraction failures
        error_msg = str(e)
        print(f"[YahooAI] Extraction failed for {ticker}: {error_msg}")
        # Return empty analysis - the calling code handles this gracefully
        return YahooAIAnalysis(
            ticker=ticker.upper(),
            title=None,
            updated_at=None,
            summary=None,
            bullets=[],
        )
