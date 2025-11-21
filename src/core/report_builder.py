from datetime import date
from typing import Iterable, Tuple, Optional

from src.skills.yahoo.quote import YahooQuoteSnapshot
from src.skills.yahoo.research import YahooAIAnalysis
from src.skills.marketwatch.research import MarketWatchTopStories, MarketWatchStory
from src.skills.googlenews.research import GoogleNewsTopStories
from src.skills.vital_knowledge.research import VitalKnowledgeReport
from src.skills.vital_knowledge.macro_news import MacroNewsSummary


def _fmt_pct(x) -> str:
    """Format a percentage value with proper sign."""
    if x is None:
        return "n/a"
    try:
        val = float(x)
    except (TypeError, ValueError):
        return "n/a"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def _fmt_number(x, decimals: int = 2) -> str:
    """Format a number with commas for thousands."""
    if x is None:
        return "n/a"
    try:
        val = float(x)
        return f"{val:,.{decimals}f}".rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return "n/a"


def _determine_sentiment(
    quote: YahooQuoteSnapshot,
    analysis: YahooAIAnalysis,
    googlenews: Optional[GoogleNewsTopStories] = None,
    vital_knowledge: Optional[VitalKnowledgeReport] = None,
) -> tuple[str, str]:
    """
    Determine if the news is bullish or bearish and generate a brief summary.
    
    Returns: (sentiment_label, brief_summary)
    """
    # Analyze price movement
    price_change = quote.change_pct if quote.change_pct is not None else 0.0
    premarket_change = quote.premarket_change_pct if quote.premarket_change_pct is not None else 0.0
    after_hours_change = quote.after_hours_change_pct if quote.after_hours_change_pct is not None else 0.0
    
    # Collect sentiment indicators
    indicators = []
    
    # Price-based sentiment
    if price_change > 1.0:
        indicators.append("strongly bullish price action")
    elif price_change > 0.3:
        indicators.append("bullish price action")
    elif price_change < -1.0:
        indicators.append("strongly bearish price action")
    elif price_change < -0.3:
        indicators.append("bearish price action")
    else:
        indicators.append("neutral price action")
    
    # Extended hours sentiment
    if premarket_change is not None and abs(premarket_change) > 0.5:
        if premarket_change > 0:
            indicators.append("positive pre-market momentum")
        else:
            indicators.append("negative pre-market momentum")
    
    if after_hours_change is not None and abs(after_hours_change) > 0.5:
        if after_hours_change > 0:
            indicators.append("positive after-hours momentum")
        else:
            indicators.append("negative after-hours momentum")
    
    # News-based sentiment
    if analysis and analysis.summary:
        summary_lower = analysis.summary.lower()
        if any(word in summary_lower for word in ["positive", "bullish", "optimistic", "strong", "growth", "upgrade", "beat"]):
            indicators.append("positive analyst sentiment")
        elif any(word in summary_lower for word in ["negative", "bearish", "concern", "weak", "decline", "downgrade", "miss"]):
            indicators.append("negative analyst sentiment")
    
    if googlenews and googlenews.news_summary:
        if googlenews.news_summary.overall_sentiment:
            sentiment = googlenews.news_summary.overall_sentiment.lower()
            if sentiment in ["bullish", "positive"]:
                indicators.append("positive news sentiment")
            elif sentiment in ["bearish", "negative"]:
                indicators.append("negative news sentiment")
    
    if vital_knowledge and vital_knowledge.summary:
        if vital_knowledge.summary.overall_sentiment:
            sentiment = vital_knowledge.summary.overall_sentiment.lower()
            if sentiment == "bullish":
                indicators.append("bullish macro news")
            elif sentiment == "bearish":
                indicators.append("bearish macro news")
    
    # Determine overall sentiment
    bullish_count = sum(1 for ind in indicators if "bullish" in ind or "positive" in ind)
    bearish_count = sum(1 for ind in indicators if "bearish" in ind or "negative" in ind)
    
    if bullish_count > bearish_count and price_change > 0.3:
        sentiment_label = "**Bullish**"
        summary = f"Price is up {_fmt_pct(price_change)} with {bullish_count} positive indicator(s). " + \
                 f"Key drivers include: {', '.join(indicators[:2])}."
    elif bearish_count > bullish_count and price_change < -0.3:
        sentiment_label = "**Bearish**"
        summary = f"Price is down {_fmt_pct(price_change)} with {bearish_count} negative indicator(s). " + \
                 f"Key concerns include: {', '.join(indicators[:2])}."
    elif price_change > 0:
        sentiment_label = "**Slightly Bullish**"
        summary = f"Price is up {_fmt_pct(price_change)} with mixed signals. " + \
                 f"Notable factors: {', '.join(indicators[:2]) if indicators else 'limited news flow'}."
    elif price_change < 0:
        sentiment_label = "**Slightly Bearish**"
        summary = f"Price is down {_fmt_pct(price_change)} with mixed signals. " + \
                 f"Notable factors: {', '.join(indicators[:2]) if indicators else 'limited news flow'}."
    else:
        sentiment_label = "**Neutral**"
        summary = f"Price is flat with {len(indicators)} indicator(s). " + \
                 f"Market factors: {', '.join(indicators[:2]) if indicators else 'limited activity'}."
    
    return sentiment_label, summary


def _combine_news_bullets(
    analysis: YahooAIAnalysis,
    googlenews: Optional[GoogleNewsTopStories] = None,
    vital_knowledge: Optional[VitalKnowledgeReport] = None,
    max_bullets: int = 4,
) -> list[str]:
    """
    Combine news from Yahoo Analysis, Google News, and Vital Knowledge into exactly 4 bullet points.
    Prioritizes the most important information from each source.
    
    Returns: List of exactly max_bullets bullet points (or fewer if not enough data)
    """
    all_bullets = []
    
    # Yahoo AI Analysis - take first 2 bullets (usually most important)
    if analysis and analysis.bullets:
        all_bullets.extend([b.strip() for b in analysis.bullets[:2] if b.strip()])
    
    # Google News - take first 2 bullet points
    if googlenews and googlenews.news_summary and googlenews.news_summary.bullet_points:
        all_bullets.extend([b.strip() for b in googlenews.news_summary.bullet_points[:2] if b.strip()])
    
    # Vital Knowledge - use summary bullets if available, otherwise use headlines
    if vital_knowledge:
        if vital_knowledge.summary and vital_knowledge.summary.key_themes:
            # Use key themes as bullets
            all_bullets.extend([f"Vital Knowledge: {theme.strip()}" for theme in vital_knowledge.summary.key_themes[:2] if theme.strip()])
        elif vital_knowledge.headlines:
            # Fall back to headlines
            all_bullets.extend([f"Vital Knowledge: {h.headline.strip()}" for h in vital_knowledge.headlines[:2] if h.headline and h.headline.strip()])
    
    # Return exactly max_bullets (or fewer if not enough data)
    return all_bullets[:max_bullets]


def format_ticker_block(
    quote: YahooQuoteSnapshot,
    analysis: YahooAIAnalysis,
    mw: Optional[MarketWatchTopStories] = None,
    googlenews: Optional[GoogleNewsTopStories] = None,
    vital_knowledge: Optional[VitalKnowledgeReport] = None,
) -> str:
    """
    Render one ticker block in Markdown with:
    1. Detailed Yahoo Quote statistics
    2. Bullish/Bearish sentiment summary
    3. Four key bullet points from Yahoo Analysis, Google News, and Vital Knowledge
    """
    lines: list[str] = []

    lines.append(f"### {quote.ticker.upper()}")
    lines.append("")

    # ========================================================================
    # SECTION 1: YAHOO QUOTE STATISTICS
    # ========================================================================
    lines.append("**Statistics:**")
    
    # Price and change
    if quote.last_price is not None:
        today_pct = _fmt_pct(quote.change_pct)
        change_abs = quote.change_abs if quote.change_abs is not None else 0.0
        lines.append(f"- Price: **{quote.last_price:.2f}** ({change_abs:+.2f}, {today_pct})")
    
    # Previous close and open
    if quote.previous_close is not None:
        lines.append(f"- Previous Close: {quote.previous_close:.2f}")
    if quote.open_price is not None:
        lines.append(f"- Open: {quote.open_price:.2f}")
    
    # Day range
    if quote.day_low is not None and quote.day_high is not None:
        lines.append(f"- Day Range: {quote.day_low:.2f} - {quote.day_high:.2f}")
    
    # Volume
    if quote.volume is not None:
        volume_str = _fmt_number(quote.volume, decimals=0)
        if quote.avg_volume is not None:
            avg_volume_str = _fmt_number(quote.avg_volume, decimals=0)
            lines.append(f"- Volume: {volume_str} (Avg: {avg_volume_str})")
        else:
            lines.append(f"- Volume: {volume_str}")
    
    # Extended hours
    extended_hours = []
    if quote.premarket_change_pct is not None:
        pre_pct = _fmt_pct(quote.premarket_change_pct)
        extended_hours.append(f"Pre-market: {pre_pct}")
    if quote.after_hours_change_pct is not None:
        after_pct = _fmt_pct(quote.after_hours_change_pct)
        extended_hours.append(f"After-hours: {after_pct}")
    
    if extended_hours:
        lines.append(f"- {' | '.join(extended_hours)}")

    # ========================================================================
    # SECTION 2: BULLISH/BEARISH SENTIMENT SUMMARY
    # ========================================================================
    lines.append("")
    sentiment_label, sentiment_summary = _determine_sentiment(
        quote, analysis, googlenews, vital_knowledge
    )
    lines.append(f"{sentiment_label}: {sentiment_summary}")

    # ========================================================================
    # SECTION 3: FOUR KEY BULLET POINTS
    # ========================================================================
    key_bullets = _combine_news_bullets(analysis, googlenews, vital_knowledge, max_bullets=4)
    
    if key_bullets:
        lines.append("")
        lines.append("**Key Points:**")
        for bullet in key_bullets:
            lines.append(f"- {bullet}")

    return "\n".join(lines).strip()


def build_morning_report(
    as_of: date,
    items: Iterable[Tuple[YahooQuoteSnapshot, YahooAIAnalysis, Optional[MarketWatchTopStories], Optional[GoogleNewsTopStories], Optional[VitalKnowledgeReport]]],
    macro_news: Optional[MacroNewsSummary] = None,
) -> str:
    """
    Build the full Morning Snapshot report in Markdown.
    """
    lines: list[str] = []

    lines.append(f"# Morning Snapshot — {as_of.isoformat()}")
    lines.append("")
    lines.append("_Auto-generated from Yahoo Finance, Google News, MarketWatch, Vital Knowledge, and Macro News_")
    lines.append("")

    # Add very short macro news summary at the top if available
    if macro_news:
        # Prioritize market close summary (most recent), fallback to morning
        macro_summary = None
        if macro_news.market_close_summary:
            macro_summary = macro_news.market_close_summary
        elif macro_news.morning_summary:
            macro_summary = macro_news.morning_summary
        
        if macro_summary:
            lines.append("## Market Overview")
            lines.append("")
            lines.append(macro_summary)
            lines.append("")
            lines.append("---")
            lines.append("")

    # Add detailed macro news section if available
    if macro_news:
        lines.append("## Market Macro Overview")
        lines.append("")
        
        # Morning report
        if macro_news.morning_date and macro_news.morning_summary:
            lines.append(f"### Morning Report ({macro_news.morning_date})")
            lines.append("")
            lines.append(macro_news.morning_summary)
            lines.append("")
            if macro_news.morning_bullets:
                lines.append("**Key Points:**")
                for bullet in macro_news.morning_bullets:
                    lines.append(f"- {bullet}")
                lines.append("")
        
        # Market close report
        if macro_news.market_close_date and macro_news.market_close_summary:
            lines.append(f"### Market Close Report ({macro_news.market_close_date})")
            lines.append("")
            lines.append(macro_news.market_close_summary)
            lines.append("")
            if macro_news.market_close_bullets:
                lines.append("**Key Points:**")
                for bullet in macro_news.market_close_bullets:
                    lines.append(f"- {bullet}")
                lines.append("")
        
        lines.append("---")
        lines.append("")

    # Individual ticker sections
    first = True
    for quote, analysis, mw, googlenews, vital_knowledge in items:
        if not first:
            lines.append("")
        first = False
        lines.append(format_ticker_block(quote, analysis, mw, googlenews, vital_knowledge))

    lines.append("")
    return "\n".join(lines)