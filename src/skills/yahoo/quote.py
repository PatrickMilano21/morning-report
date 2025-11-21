# src/skills/yahoo/quote.py

from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class YahooQuoteSnapshot(BaseModel):
    """
    Structured snapshot of the main Yahoo Finance quote panel.
    """
    
    model_config = ConfigDict(populate_by_name=True)

    ticker: str

    # Regular session
    last_price: Optional[float] = Field(default=None, alias="lastPrice")
    change_abs: Optional[float] = Field(default=None, alias="changeAbs")
    change_pct: Optional[float] = Field(default=None, alias="changePct")

    currency: Optional[str] = None

    open_price: Optional[float] = Field(default=None, alias="openPrice")
    previous_close: Optional[float] = Field(default=None, alias="previousClose")

    day_low: Optional[float] = Field(default=None, alias="dayLow")
    day_high: Optional[float] = Field(default=None, alias="dayHigh")

    volume: Optional[int] = None
    avg_volume: Optional[int] = Field(default=None, alias="avgVolume")

    # Extended-hours session
    premarket_change_pct: Optional[float] = None
    after_hours_change_pct: Optional[float] = None


async def fetch_yahoo_quote(page, ticker: str) -> YahooQuoteSnapshot:
    """
    Use Stagehand extract to pull a structured quote snapshot for `ticker`
    from the Yahoo Finance quote page.

    `page` is a StagehandPage (stagehand.page) instance.
    """
    url = f"https://finance.yahoo.com/quote/{ticker}"
    await page.goto(url)

    snapshot = await page.extract(
        instruction=f"""
        You are on the Yahoo Finance quote page for the stock symbol {ticker}.

        From the main quote panel, extract:
        - last_price: the current regular-session last traded price
        - change_abs: today's absolute price change vs previous close
        - change_pct: today's percentage change vs previous close (e.g. -1.82 for -1.82%)
        - currency: the trading currency, such as "USD"
        - open_price: today's official open
        - previous_close: yesterday's close
        - day_low and day_high: today's regular-session intraday low and high
        - volume: today's regular-session volume
        - avg_volume: the average daily volume if shown

        If extended-hours data is visible, also extract:
        - premarket_change_pct: percentage move during pre-market trading
        - after_hours_change_pct: percentage move during after-hours trading

        Return numeric values where possible instead of strings with symbols or commas.
        """,
        schema=YahooQuoteSnapshot,
    )

    snapshot.ticker = ticker.upper()
    return snapshot
