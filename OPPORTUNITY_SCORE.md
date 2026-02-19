# Opportunity Score Algorithm - Technical Specification

## Overview
מנוע ניקוד חכם שמדרג הזדמנויות מסחר על בסיס 6 ממדים עיקריים, תוך התחשבות בסיכונים ספציפיים. הציון הסופי (0-100) משקף את הסבירות לתנועת מחיר משמעותית ב-1-3 ימים הקרובים.

---

## Master Formula

```
Opportunity_Score = (
    Signal_Quality      * 0.25 +
    Impact_Potential    * 0.20 +
    Technical_Conf      * 0.20 +
    Sentiment_Momentum  * 0.15 +
    Volume_Confirmation * 0.10 +
    Historical_WinRate  * 0.10
) * Risk_Multiplier * Recency_Decay

Final_Score = round(Opportunity_Score, 2)

where:
  Risk_Multiplier = max(1 - Risk_Score, 0.2)  // Never zero out completely
  Recency_Decay = 1.0 if age < 15min, else 0.9 if age < 1hr, else 0.7
```

---

## 1. Signal Quality (0-100)

**Purpose**: Оценить надежность и своевременность сигнала

### 1.1 Source Reliability (30 points)
```python
SOURCE_SCORES = {
    'FMP': 30,           # Official SEC filings
    'POLYGON': 30,       # Direct market data
    'NEWSFILTER': 28,    # Verified news stream
    'FINVIZ': 25,        # Aggregated, some lag
    'ALPHAVANTAGE': 22,  # AI sentiment, less reliable
    'FINNHUB': 20,       # Free tier, basic data
}

source_score = SOURCE_SCORES.get(event.source, 15)
```

### 1.2 Timeliness (30 points)
```python
age_minutes = (now() - event.timestamp).total_seconds() / 60

if age_minutes <= 5:
    timeliness = 30      # Fresh news = critical
elif age_minutes <= 15:
    timeliness = 25
elif age_minutes <= 30:
    timeliness = 18
elif age_minutes <= 60:
    timeliness = 10
else:
    timeliness = 5       # Likely priced in
```

### 1.3 Event Type Significance (30 points)
```python
EVENT_IMPORTANCE = {
    # Critical catalysts (30 points)
    'FDA_APPROVAL': 30,
    'FDA_REJECTION': 30,
    'EARNINGS_BEAT': 30,
    'EARNINGS_MISS': 30,
    'MERGER_ACQUISITION': 30,

    # High impact (25 points)
    'FILING_8K': 25,              # Unexpected events
    'INSIDER_BUY_LARGE': 25,      # >$1M purchase
    'ANALYST_UPGRADE_MAJOR': 25,  # PT increase >20%
    'CLINICAL_TRIAL_SUCCESS': 25,

    # Moderate impact (20 points)
    'FILING_10Q': 20,
    'EARNINGS_REPORT': 20,        # General earnings
    'VOLUME_SPIKE': 20,
    'PRICE_BREAKOUT': 20,

    # Low impact (15 points)
    'NEWS_GENERAL': 15,
    'INSIDER_SELL': 15,           # Less actionable
    'ANALYST_DOWNGRADE': 15,
}

event_score = EVENT_IMPORTANCE.get(event.event_type, 10)

# Bonus for multiple simultaneous events
if count_events_last_hour(event.symbol) >= 3:
    event_score = min(event_score + 5, 30)
```

### 1.4 Verification Status (10 points)
```python
verification = 0

# Cross-source confirmation
sources_reporting = count_sources(event.symbol, event.title, window='30min')
if sources_reporting >= 3:
    verification = 10
elif sources_reporting == 2:
    verification = 7
else:
    verification = 3  # Single source = less reliable

# Penalty for unverified rumors
if 'rumor' in event.title.lower() or 'speculation' in event.summary.lower():
    verification -= 5
```

### Final Signal Quality
```python
signal_quality = min(
    source_score + timeliness + event_score + verification,
    100
)
```

---

## 2. Impact Potential (0-100)

**Purpose**: יכולת התנועה הצפויה של המחיר

### 2.1 Historical Price Reaction (40 points)
```python
# Find similar events in same sector + market cap range
similar_events = query_historical_events(
    event_type=event.event_type,
    sector=event.sector,
    market_cap_range=(event.market_cap * 0.5, event.market_cap * 2),
    lookback_days=365
)

# Calculate average price movement 1-3 days after event
price_movements = []
for past_event in similar_events:
    price_before = get_price_at(past_event.symbol, past_event.timestamp)
    price_after_1d = get_price_at(past_event.symbol, past_event.timestamp + 1day)
    price_after_3d = get_price_at(past_event.symbol, past_event.timestamp + 3days)

    max_move = max(
        abs(price_after_1d - price_before) / price_before,
        abs(price_after_3d - price_before) / price_before
    )
    price_movements.append(max_move)

avg_movement = mean(price_movements)

# Score based on average movement
if avg_movement >= 0.15:       # 15%+ move
    historical_score = 40
elif avg_movement >= 0.10:     # 10-15%
    historical_score = 35
elif avg_movement >= 0.07:     # 7-10%
    historical_score = 28
elif avg_movement >= 0.05:     # 5-7%
    historical_score = 20
else:
    historical_score = 10      # <5% move
```

### 2.2 Market Cap Impact (30 points)
```python
# Smaller stocks = higher potential impact
if market_cap < 100_000_000:        # <$100M (micro)
    cap_score = 30
elif market_cap < 500_000_000:      # $100M-$500M (small)
    cap_score = 25
elif market_cap < 2_000_000_000:    # $500M-$2B (mid)
    cap_score = 20
elif market_cap < 10_000_000_000:   # $2B-$10B (large)
    cap_score = 12
else:                                # >$10B (mega)
    cap_score = 5

# Penalty for extremely low cap (penny stocks)
if market_cap < 10_000_000:  # <$10M
    cap_score *= 0.5         # Too risky/illiquid
```

### 2.3 Sector Volatility (30 points)
```python
SECTOR_VOLATILITY = {
    'Healthcare': 30,      # Biotech = wild swings
    'Technology': 25,
    'Energy': 22,
    'Financial': 18,
    'Consumer Cyclical': 15,
    'Utilities': 8,        # Stable, boring
    'Consumer Defensive': 10,
}

sector_score = SECTOR_VOLATILITY.get(event.sector, 15)

# Bonus for hot sectors (recent high momentum)
sector_momentum = calculate_sector_momentum(event.sector, days=7)
if sector_momentum > 0.05:  # Sector up 5%+ this week
    sector_score += 5
```

### Final Impact Potential
```python
impact_potential = min(
    historical_score + cap_score + sector_score,
    100
)
```

---

## 3. Technical Confluence (0-100)

**Purpose**: אישור טכני לכיוון הסיגנל

### 3.1 Price at Key Level (25 points)
```python
# Get support/resistance levels
levels = calculate_pivot_points(symbol, period='3months')
current_price = get_live_price(symbol)

distance_to_nearest = min([
    abs(current_price - level) / current_price
    for level in levels['support'] + levels['resistance']
])

if distance_to_nearest < 0.01:    # Within 1% of key level
    level_score = 25
elif distance_to_nearest < 0.02:  # Within 2%
    level_score = 18
elif distance_to_nearest < 0.05:  # Within 5%
    level_score = 10
else:
    level_score = 5

# Bonus if breaking OUT of consolidation
if is_breakout(symbol):
    level_score += 10
```

### 3.2 RSI Alignment (20 points)
```python
rsi_14 = calculate_rsi(symbol, period=14)

if event.direction == 'BULLISH':
    if rsi_14 < 30:          # Oversold + bullish catalyst
        rsi_score = 20
    elif rsi_14 < 40:
        rsi_score = 15
    elif rsi_14 < 50:
        rsi_score = 10
    else:
        rsi_score = 5        # Already extended

elif event.direction == 'BEARISH':
    if rsi_14 > 70:          # Overbought + bearish catalyst
        rsi_score = 20
    elif rsi_14 > 60:
        rsi_score = 15
    else:
        rsi_score = 5
```

### 3.3 Volume Surge (25 points)
```python
current_volume = get_today_volume(symbol)
avg_volume_20d = get_avg_volume(symbol, days=20)

volume_ratio = current_volume / avg_volume_20d

if volume_ratio > 5:       # 5x average
    volume_score = 25
elif volume_ratio > 3:     # 3x average
    volume_score = 20
elif volume_ratio > 2:     # 2x average
    volume_score = 15
elif volume_ratio > 1.5:   # 1.5x average
    volume_score = 10
else:
    volume_score = 5       # No confirmation
```

### 3.4 Moving Average Alignment (30 points)
```python
price = get_live_price(symbol)
sma_20 = get_sma(symbol, 20)
sma_50 = get_sma(symbol, 50)
sma_200 = get_sma(symbol, 200)

ma_score = 0

if event.direction == 'BULLISH':
    if price > sma_20 > sma_50 > sma_200:  # Perfect bullish alignment
        ma_score = 30
    elif price > sma_20 > sma_50:          # Above short + mid term
        ma_score = 20
    elif price > sma_20:                   # Above short term only
        ma_score = 10
    else:
        ma_score = 5                       # Fighting downtrend

elif event.direction == 'BEARISH':
    if price < sma_20 < sma_50 < sma_200:  # Perfect bearish alignment
        ma_score = 30
    elif price < sma_20 < sma_50:
        ma_score = 20
    else:
        ma_score = 10
```

### Final Technical Confluence
```python
technical_confluence = min(
    level_score + rsi_score + volume_score + ma_score,
    100
)
```

---

## 4. Sentiment Momentum (0-100)

**Purpose**: מדידת תחושת השוק סביב המניה

### 4.1 News Sentiment (40 points)
```python
# Aggregate sentiment from all news in last 24 hours
news_items = get_recent_news(symbol, hours=24)
sentiments = [item.sentiment_score for item in news_items]  # -1 to +1

avg_sentiment = mean(sentiments) if sentiments else 0

# Convert to score
if event.direction == 'BULLISH':
    if avg_sentiment > 0.5:       # Strong positive sentiment
        news_sentiment = 40
    elif avg_sentiment > 0.2:
        news_sentiment = 30
    elif avg_sentiment > 0:
        news_sentiment = 20
    else:
        news_sentiment = 10       # Fighting negative sentiment

elif event.direction == 'BEARISH':
    if avg_sentiment < -0.5:      # Strong negative sentiment
        news_sentiment = 40
    elif avg_sentiment < -0.2:
        news_sentiment = 30
    elif avg_sentiment < 0:
        news_sentiment = 20
    else:
        news_sentiment = 10

# Bonus for sentiment acceleration
sentiment_change = avg_sentiment - get_sentiment(symbol, hours=48, offset=24)
if abs(sentiment_change) > 0.3:
    news_sentiment += 10
```

### 4.2 Social Media Buzz (30 points)
```python
# Optional: If integrating Twitter/Reddit/StockTwits
mentions_today = get_social_mentions(symbol, hours=24)
mentions_baseline = get_avg_mentions(symbol, days=30)

buzz_ratio = mentions_today / mentions_baseline if mentions_baseline > 0 else 1

if buzz_ratio > 5:         # 5x normal buzz
    social_score = 30
elif buzz_ratio > 3:
    social_score = 25
elif buzz_ratio > 2:
    social_score = 18
else:
    social_score = 10

# If social data not available
if not SOCIAL_ENABLED:
    social_score = 15      # Neutral assumption
```

### 4.3 Sector Sentiment (30 points)
```python
# Overall sector mood
sector_returns_1w = get_sector_return(event.sector, days=7)
sector_returns_1m = get_sector_return(event.sector, days=30)

# Momentum scoring
if sector_returns_1w > 0.03 and sector_returns_1m > 0.05:  # Hot sector
    sector_sentiment = 30
elif sector_returns_1w > 0:
    sector_sentiment = 20
elif sector_returns_1w > -0.03:
    sector_sentiment = 15
else:
    sector_sentiment = 5   # Sector in downtrend
```

### Final Sentiment Momentum
```python
sentiment_momentum = min(
    news_sentiment + social_score + sector_sentiment,
    100
)
```

---

## 5. Volume Confirmation (0-100)

**Purpose**: אישור עניין מוסדי/קמעונאי

### 5.1 Volume Ratio (60 points)
```python
current_volume = get_today_volume(symbol)
avg_volume_20d = get_avg_volume(symbol, days=20)

volume_ratio = current_volume / avg_volume_20d

if volume_ratio > 10:      # Extreme spike
    ratio_score = 60
elif volume_ratio > 5:
    ratio_score = 50
elif volume_ratio > 3:
    ratio_score = 40
elif volume_ratio > 2:
    ratio_score = 30
elif volume_ratio > 1.5:
    ratio_score = 20
else:
    ratio_score = 10       # Low conviction
```

### 5.2 Intraday Volume Pattern (40 points)
```python
# Check if volume came AFTER news (better) vs BEFORE (leaked/priced in)
news_time = event.timestamp
volume_before_news = get_volume(symbol, start=today_open, end=news_time)
volume_after_news = get_volume(symbol, start=news_time, end=now())

if volume_after_news > volume_before_news * 2:  # Volume spiked POST-news
    pattern_score = 40
elif volume_after_news > volume_before_news:
    pattern_score = 30
else:
    pattern_score = 10  # Volume came before = already priced in
```

### Final Volume Confirmation
```python
volume_confirmation = min(ratio_score + pattern_score, 100)
```

---

## 6. Historical Win Rate (0-100)

**Purpose**: אימות אמפירי של האסטרטגיה

### 6.1 Event Type Win Rate (70 points)
```python
# Backtest: Find all similar events in last 1 year
historical_signals = query_signals(
    event_type=event.event_type,
    sector=event.sector,
    direction=event.direction,
    min_signal_quality=60,
    lookback_days=365
)

# Calculate how many "won" (moved favorably >5% within 3 days)
wins = 0
for signal in historical_signals:
    price_at_signal = signal.entry_price
    price_3d_later = get_price_at(signal.symbol, signal.timestamp + 3days)

    if signal.direction == 'BULLISH':
        if price_3d_later > price_at_signal * 1.05:  # 5%+ gain
            wins += 1
    elif signal.direction == 'BEARISH':
        if price_3d_later < price_at_signal * 0.95:  # 5%+ drop
            wins += 1

win_rate = wins / len(historical_signals) if historical_signals else 0.5

# Convert to score
if win_rate >= 0.70:       # 70%+ win rate
    wr_score = 70
elif win_rate >= 0.60:
    wr_score = 60
elif win_rate >= 0.50:
    wr_score = 50
elif win_rate >= 0.40:
    wr_score = 35
else:
    wr_score = 20          # <40% win rate = weak strategy
```

### 6.2 Recent Performance Adjustment (30 points)
```python
# More weight to last 30 days (market regime changes)
recent_signals = [s for s in historical_signals if s.timestamp > (now() - 30days)]

if recent_signals:
    recent_wins = count_wins(recent_signals)
    recent_win_rate = recent_wins / len(recent_signals)

    if recent_win_rate >= 0.65:
        recent_score = 30
    elif recent_win_rate >= 0.50:
        recent_score = 20
    else:
        recent_score = 10
else:
    recent_score = 15      # No recent data
```

### Final Historical Win Rate
```python
historical_win_rate = min(wr_score + recent_score, 100)
```

---

## 7. Risk Multiplier (0.2 - 1.0)

**Purpose**: הפחתת ציון בהתאם לסיכונים זוהים

```python
risk_score = 0.0

### 7.1 Liquidity Risk
if avg_daily_volume < 50_000:          # Very low liquidity
    risk_score += 0.40
elif avg_daily_volume < 100_000:
    risk_score += 0.30
elif avg_daily_volume < 500_000:
    risk_score += 0.15

### 7.2 Spread Risk
bid_ask_spread = (ask - bid) / mid_price
if bid_ask_spread > 0.05:              # >5% spread
    risk_score += 0.20
elif bid_ask_spread > 0.02:
    risk_score += 0.10

### 7.3 Dilution Risk (Biotech/Small Caps)
if sector == 'Healthcare' and market_cap < 500_000_000:
    balance_sheet = get_financials(symbol)
    if balance_sheet.get('cash', 0) < 10_000_000:  # <$10M cash
        risk_score += 0.25  # High risk of dilutive financing

### 7.4 Already Priced In
price_move_before_news = (
    get_price_before(symbol, minutes=30) - get_price_before(symbol, hours=24)
) / get_price_before(symbol, hours=24)

if abs(price_move_before_news) > 0.10:  # Already moved 10%+ before news
    risk_score += 0.30
elif abs(price_move_before_news) > 0.05:
    risk_score += 0.15

### 7.5 News Verification
sources_reporting = count_sources(event.symbol, event.title, window='1hour')
if sources_reporting < 2:              # Single source only
    risk_score += 0.20
elif sources_reporting < 3:
    risk_score += 0.10

### 7.6 Gap Risk (After Hours)
if is_market_closed():
    if current_volatility(symbol) > 0.05:  # High volatility stock
        risk_score += 0.15  # Gap risk overnight

### 7.7 Penny Stock Flag
if price < 1.0:
    risk_score += 0.35  # SEC penny stock rules, manipulation risk

### 7.8 Earnings Lock-Up
days_to_earnings = get_days_until_earnings(symbol)
if 0 < days_to_earnings < 5:
    risk_score += 0.10  # Earnings uncertainty

### Final Risk Multiplier
risk_multiplier = max(1.0 - min(risk_score, 0.80), 0.20)
# Never drop below 0.2 (keep some signal even with risks)
```

---

## 8. Recency Decay

```python
age_minutes = (now() - event.timestamp).total_seconds() / 60

if age_minutes <= 15:
    recency = 1.0      # Peak freshness
elif age_minutes <= 60:
    recency = 0.9      # Still relevant
elif age_minutes <= 120:
    recency = 0.75     # Getting stale
else:
    recency = 0.5      # Likely priced in
```

---

## 9. Final Score Calculation

```python
def calculate_opportunity_score(event: MarketEvent) -> OpportunityScore:
    # 1. Calculate all components
    sq = calculate_signal_quality(event)
    ip = calculate_impact_potential(event)
    tc = calculate_technical_confluence(event)
    sm = calculate_sentiment_momentum(event)
    vc = calculate_volume_confirmation(event)
    hw = calculate_historical_win_rate(event)

    # 2. Weighted sum
    raw_score = (
        sq * 0.25 +
        ip * 0.20 +
        tc * 0.20 +
        sm * 0.15 +
        vc * 0.10 +
        hw * 0.10
    )

    # 3. Apply risk multiplier
    risk_mult = calculate_risk_multiplier(event)
    risk_adjusted = raw_score * risk_mult

    # 4. Apply recency decay
    recency = calculate_recency_decay(event)
    final_score = risk_adjusted * recency

    # 5. Round and clamp
    final_score = round(min(max(final_score, 0), 100), 2)

    return OpportunityScore(
        final_score=final_score,
        components={
            'signal_quality': sq,
            'impact_potential': ip,
            'technical_confluence': tc,
            'sentiment_momentum': sm,
            'volume_confirmation': vc,
            'historical_win_rate': hw,
        },
        risk_multiplier=risk_mult,
        recency_decay=recency,
        confidence=calculate_confidence(event, final_score)
    )
```

---

## 10. Confidence Score

**Purpose**: עד כמה אנחנו בטוחים בציון הזה?

```python
def calculate_confidence(event: MarketEvent, final_score: float) -> float:
    confidence = 0.5  # Baseline

    # More historical data = higher confidence
    sample_size = count_similar_historical_events(event)
    if sample_size > 50:
        confidence += 0.25
    elif sample_size > 20:
        confidence += 0.15
    elif sample_size > 5:
        confidence += 0.05

    # Multiple data sources = higher confidence
    if event.sources_reporting >= 3:
        confidence += 0.15
    elif event.sources_reporting == 2:
        confidence += 0.08

    # High signal quality = higher confidence
    if event.signal_quality > 80:
        confidence += 0.10

    return min(confidence, 1.0)
```

---

## 11. Score Interpretation Guide

| Score Range | Label | Action | Expected Win Rate |
|------------|-------|--------|-------------------|
| 85-100 | 🚀 **Exceptional** | Strong buy/short | 65-75% |
| 70-84 | 🔥 **Strong** | Buy/short with tight stop | 55-65% |
| 55-69 | ✅ **Good** | Consider position | 50-55% |
| 40-54 | ⚠️ **Watchlist** | Monitor, don't trade | 45-50% |
| 0-39 | ❌ **Weak** | Ignore | <45% |

---

## 12. Real-World Example Calculation

### Scenario: Biotech FDA Approval

**Event:**
```json
{
  "symbol": "ABCD",
  "event_type": "FDA_APPROVAL",
  "source": "FMP",
  "timestamp": "2026-02-05T14:30:00Z",
  "title": "FDA Approves ABCD's Cancer Drug",
  "sector": "Healthcare",
  "market_cap": 250000000,  // $250M
  "price": 5.80,
  "direction": "BULLISH"
}
```

**Calculations:**

1. **Signal Quality** = 30 (source) + 30 (5 min old) + 30 (FDA approval) + 7 (2 sources) = **97**

2. **Impact Potential** = 35 (historical 12% avg move) + 25 (small cap) + 30 (healthcare volatility) = **90**

3. **Technical Confluence**:
   - Price near support: 18
   - RSI = 35 (oversold + bullish): 15
   - Volume 4x average: 20
   - Price > SMA20 > SMA50: 20
   - **Total: 73**

4. **Sentiment Momentum** = 30 (positive news sentiment) + 25 (3x social mentions) + 20 (sector up this week) = **75**

5. **Volume Confirmation** = 50 (5x volume) + 40 (spike after news) = **90**

6. **Historical Win Rate** = 60 (58% historical win rate) + 20 (60% recent) = **80**

**Weighted Sum:**
```
Raw = 97*0.25 + 90*0.20 + 73*0.20 + 75*0.15 + 90*0.10 + 80*0.10
    = 24.25 + 18 + 14.6 + 11.25 + 9 + 8
    = 85.1
```

**Risk Multiplier:**
- Liquidity: avg volume 200K → risk = 0.15
- Cash: $8M → risk = 0.25
- Spread: 2% → risk = 0
- **Total risk = 0.40 → multiplier = 0.60**

**Risk Adjusted:** 85.1 * 0.60 = **51.06**

**Recency:** 5 minutes → 1.0

**Final Score:** 51.06 * 1.0 = **51.06**

**Result:** ⚠️ **Watchlist** - Despite strong signal, high dilution risk and low liquidity drop it to "monitor" status. Wait for volume confirmation or risk reduction.

---

## 13. Calibration & Backtesting

### Monthly Review Process
1. Pull all signals from last 30 days
2. Calculate actual outcomes (% move in 1-3 days)
3. Group by score ranges (e.g., 80-100, 60-79, etc.)
4. Measure actual win rate per group
5. If deviation > 10% from expected, retune weights

### A/B Testing Framework
- Split traffic 80/20 (current algo / experimental)
- Track metrics: win rate, avg return, max drawdown
- Promote experimental if outperforms by >5% over 2 weeks

---

## 14. Future Enhancements

1. **Machine Learning Layer**
   - Train gradient boosting model (XGBoost) on historical signals
   - Use ML score as 7th component (10% weight)

2. **Options Flow Integration**
   - Unusual options activity = +15 points to Impact Potential

3. **Institutional Holdings**
   - Recent 13F filings showing increased positions = +10 to Sentiment

4. **Correlation Analysis**
   - If correlated stocks also moving = higher confidence

5. **News NLP Extraction**
   - Extract specific numbers from press releases (revenue, drug efficacy %)
   - Compare to expectations for more nuanced scoring

---

**Last Updated:** 2026-02-05
**Version:** 1.0
