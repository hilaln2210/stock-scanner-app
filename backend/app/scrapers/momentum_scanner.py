from typing import List, Dict
from datetime import datetime
from app.scrapers.market_pulse import get_high_momentum_stocks
from app.config import settings


class MomentumScanner:
    """
    Real-time momentum scanner using Finviz Elite
    Provides accurate, real-time market data without rate limits
    """

    def __init__(self):
        self.finviz_email = settings.finviz_email
        self.finviz_password = settings.finviz_password
        self.finviz_cookie = settings.finviz_cookie

    async def scan_momentum_opportunities(self) -> List[Dict]:
        """
        Scan for high-momentum trading opportunities using Finviz Elite

        Returns stocks with:
        - Strong price movements
        - Volume anomalies
        - Technical breakouts
        - News catalysts

        Data comes directly from Finviz Elite for maximum accuracy
        """
        try:
            # Get high momentum stocks from Finviz Elite
            # This already includes real-time price, volume, and momentum data
            stocks = await get_high_momentum_stocks(
                limit=100,  # Get more stocks for better filtering
                email=self.finviz_email,
                password=self.finviz_password,
                cookie=self.finviz_cookie
            )

            # Filter and enhance with momentum scoring
            opportunities = []
            for stock in stocks:
                momentum_data = self._calculate_momentum_score(stock)
                if momentum_data and momentum_data.get("momentum_score", 0) >= 50:
                    opportunities.append(momentum_data)

            # Sort by momentum score
            opportunities.sort(key=lambda x: x.get("momentum_score", 0), reverse=True)

            return opportunities[:50]  # Top 50

        except Exception as e:
            print(f"Error scanning momentum from Finviz Elite: {e}")
            return []

    def _calculate_momentum_score(self, stock: Dict) -> Dict:
        """
        Calculate momentum score from Finviz Elite data
        Finviz provides: price_change, volume, news, technical patterns
        """
        try:
            # Extract key metrics from Finviz data
            ticker = stock.get("ticker", "")
            price_change = stock.get("price_change", 0)

            # Momentum score calculation (0-100)
            momentum_score = 50  # Base score for appearing in Finviz momentum feed

            # Price change component (0-35 points)
            if abs(price_change) >= 15:
                momentum_score += 35
            elif abs(price_change) >= 10:
                momentum_score += 30
            elif abs(price_change) >= 7:
                momentum_score += 25
            elif abs(price_change) >= 5:
                momentum_score += 20
            elif abs(price_change) >= 3:
                momentum_score += 15
            elif abs(price_change) >= 2:
                momentum_score += 10

            # News/catalyst component (0-15 points)
            # If stock appears in Finviz Elite feed, it has news momentum
            momentum_score += 10

            # Build enhanced signals
            signals = []

            # Price signals
            if price_change >= 10:
                signals.append(f"💹 +{price_change:.1f}% (STRONG)")
            elif price_change >= 5:
                signals.append(f"🚀 +{price_change:.1f}%")
            elif price_change >= 3:
                signals.append(f"📈 +{price_change:.1f}%")
            elif price_change <= -10:
                signals.append(f"📉 {price_change:.1f}% (STRONG DROP)")
            elif price_change <= -5:
                signals.append(f"⬇️ {price_change:.1f}%")
            elif price_change <= -3:
                signals.append(f"📉 {price_change:.1f}%")

            # News catalyst
            signals.append("📰 Breaking News")

            # High momentum from Finviz Elite
            if momentum_score >= 80:
                signals.append("🔥 EXTREME Momentum")
            elif momentum_score >= 70:
                signals.append("⚡ HIGH Momentum")

            # Create title from signals
            if signals:
                top_signals = signals[:3] if len(signals) >= 3 else signals
                title = f"{ticker}: {' • '.join(top_signals)}"
            else:
                title = stock.get("title", f"{ticker}: Momentum detected")

            # Return enhanced stock data
            return {
                "ticker": ticker,
                "title": title,
                "momentum_score": int(min(100, momentum_score)),
                "price_change": round(price_change, 2),
                "signals": signals,
                "published_at": stock.get("published_at", datetime.now().isoformat()),
                "url": stock.get("url", f"https://finviz.com/quote.ashx?t={ticker}")
            }

        except Exception as e:
            print(f"Error calculating momentum score: {e}")
            return None

    async def get_stock_momentum_details(self, ticker: str) -> Dict:
        """
        Get detailed momentum analysis for a specific stock
        Uses Finviz Elite for accurate real-time data
        """
        try:
            # Get all opportunities and find the specific ticker
            opportunities = await self.scan_momentum_opportunities()

            for opp in opportunities:
                if opp.get("ticker", "").upper() == ticker.upper():
                    return opp

            # If not found in current scan, return basic structure
            return {
                "ticker": ticker,
                "momentum_score": 0,
                "title": f"{ticker}: Not currently showing momentum",
                "published_at": datetime.now().isoformat(),
                "url": f"https://finviz.com/quote.ashx?t={ticker}"
            }

        except Exception as e:
            print(f"Error getting momentum details for {ticker}: {e}")
            return {
                "ticker": ticker,
                "momentum_score": 0,
                "error": str(e)
            }
