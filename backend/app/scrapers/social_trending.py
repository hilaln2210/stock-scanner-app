"""
Social Media Trending Stocks Scanner
Aggregates mentions from Reddit, StockTwits, Twitter alternatives, and other sources
"""
from typing import List, Dict
from datetime import datetime, timedelta
import aiohttp
import asyncio
from collections import defaultdict
import re


class SocialTrendingScanner:
    """
    Scans social media for trending stock mentions
    Sources: Reddit, StockTwits, and other public APIs
    """

    def __init__(self):
        self.session = None
        self.ticker_pattern = re.compile(r'\$([A-Z]{1,5})\b')

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
        return self.session

    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract stock tickers from text (e.g., $AAPL, $TSLA)"""
        if not text:
            return []
        matches = self.ticker_pattern.findall(text)
        # Filter out common false positives
        filtered = [t for t in matches if t not in ['USD', 'SPY', 'QQQ', 'DIA', 'IWM']]
        return filtered

    async def scrape_reddit_wallstreetbets(self) -> List[Dict]:
        """
        Scrape Reddit r/wallstreetbets for trending stocks
        Uses Reddit's public JSON API (no auth needed)
        """
        try:
            session = await self._get_session()
            url = 'https://www.reddit.com/r/wallstreetbets/hot.json?limit=100'

            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    print(f"Reddit WSB returned status {response.status}")
                    return []

                data = await response.json()
                posts = data.get('data', {}).get('children', [])

                ticker_mentions = defaultdict(lambda: {
                    'count': 0,
                    'posts': [],
                    'sentiment_scores': [],
                    'upvotes': 0
                })

                for post in posts:
                    post_data = post.get('data', {})
                    title = post_data.get('title', '')
                    selftext = post_data.get('selftext', '')
                    text = f"{title} {selftext}"
                    upvotes = post_data.get('ups', 0)
                    url = f"https://reddit.com{post_data.get('permalink', '')}"

                    # Extract tickers
                    tickers = self._extract_tickers(text)

                    for ticker in tickers:
                        ticker_mentions[ticker]['count'] += 1
                        ticker_mentions[ticker]['upvotes'] += upvotes

                        # Estimate sentiment (simple heuristic)
                        sentiment = 0
                        text_lower = text.lower()
                        if any(word in text_lower for word in ['buy', 'calls', 'moon', 'rocket', 'bullish', 'long']):
                            sentiment += 1
                        if any(word in text_lower for word in ['sell', 'puts', 'crash', 'bearish', 'short']):
                            sentiment -= 1

                        ticker_mentions[ticker]['sentiment_scores'].append(sentiment)
                        ticker_mentions[ticker]['posts'].append({
                            'text': title[:200],
                            'url': url,
                            'author': post_data.get('author', 'Anonymous'),
                            'upvotes': upvotes
                        })

                return [
                    {
                        'ticker': ticker,
                        'mention_count': data['count'],
                        'source': 'reddit',
                        'posts': data['posts'][:5],  # Top 5 posts
                        'avg_sentiment': sum(data['sentiment_scores']) / len(data['sentiment_scores']) if data['sentiment_scores'] else 0,
                        'total_upvotes': data['upvotes']
                    }
                    for ticker, data in ticker_mentions.items()
                    if data['count'] >= 2  # At least 2 mentions
                ]

        except Exception as e:
            print(f"Error scraping Reddit WSB: {e}")
            return []

    async def scrape_stocktwits(self) -> List[Dict]:
        """
        Scrape StockTwits trending stocks
        Uses StockTwits public API
        """
        try:
            session = await self._get_session()

            # Get trending tickers from StockTwits
            url = 'https://api.stocktwits.com/api/2/trending/symbols.json'

            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    print(f"StockTwits returned status {response.status}")
                    return []

                data = await response.json()
                symbols = data.get('symbols', [])

                trending_stocks = []
                for symbol in symbols[:20]:  # Top 20
                    ticker = symbol.get('symbol', '').upper()
                    if not ticker:
                        continue

                    # Get recent messages for this ticker
                    messages_url = f'https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json'

                    try:
                        async with session.get(messages_url, timeout=5) as msg_response:
                            if msg_response.status == 200:
                                msg_data = await msg_response.json()
                                messages = msg_data.get('messages', [])

                                posts = []
                                sentiment_scores = []

                                for msg in messages[:10]:  # Top 10 messages
                                    body = msg.get('body', '')
                                    sentiment = msg.get('entities', {}).get('sentiment', {})
                                    sentiment_basic = sentiment.get('basic', 'neutral')

                                    sentiment_score = 0
                                    if sentiment_basic == 'bullish':
                                        sentiment_score = 1
                                    elif sentiment_basic == 'bearish':
                                        sentiment_score = -1

                                    sentiment_scores.append(sentiment_score)

                                    posts.append({
                                        'text': body[:200],
                                        'url': f"https://stocktwits.com/symbol/{ticker}",
                                        'author': msg.get('user', {}).get('username', 'Anonymous'),
                                        'sentiment': sentiment_basic
                                    })

                                trending_stocks.append({
                                    'ticker': ticker,
                                    'mention_count': len(messages),
                                    'source': 'stocktwits',
                                    'posts': posts[:5],
                                    'avg_sentiment': sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
                                })

                    except Exception as e:
                        print(f"Error fetching StockTwits messages for {ticker}: {e}")
                        continue

                return trending_stocks

        except Exception as e:
            print(f"Error scraping StockTwits: {e}")
            return []

    async def scrape_reddit_stocks(self) -> List[Dict]:
        """
        Scrape Reddit r/stocks for trending mentions
        """
        try:
            session = await self._get_session()
            url = 'https://www.reddit.com/r/stocks/hot.json?limit=50'

            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return []

                data = await response.json()
                posts = data.get('data', {}).get('children', [])

                ticker_mentions = defaultdict(lambda: {
                    'count': 0,
                    'posts': [],
                    'sentiment_scores': []
                })

                for post in posts:
                    post_data = post.get('data', {})
                    title = post_data.get('title', '')
                    selftext = post_data.get('selftext', '')
                    text = f"{title} {selftext}"

                    tickers = self._extract_tickers(text)

                    for ticker in tickers:
                        ticker_mentions[ticker]['count'] += 1

                        sentiment = 0
                        text_lower = text.lower()
                        if any(word in text_lower for word in ['bullish', 'buy', 'long', 'calls']):
                            sentiment += 1
                        if any(word in text_lower for word in ['bearish', 'sell', 'short', 'puts']):
                            sentiment -= 1

                        ticker_mentions[ticker]['sentiment_scores'].append(sentiment)
                        ticker_mentions[ticker]['posts'].append({
                            'text': title[:200],
                            'url': f"https://reddit.com{post_data.get('permalink', '')}",
                            'author': post_data.get('author', 'Anonymous')
                        })

                return [
                    {
                        'ticker': ticker,
                        'mention_count': data['count'],
                        'source': 'reddit_stocks',
                        'posts': data['posts'][:3],
                        'avg_sentiment': sum(data['sentiment_scores']) / len(data['sentiment_scores']) if data['sentiment_scores'] else 0
                    }
                    for ticker, data in ticker_mentions.items()
                    if data['count'] >= 2
                ]

        except Exception as e:
            print(f"Error scraping r/stocks: {e}")
            return []

    async def aggregate_trending_stocks(self) -> List[Dict]:
        """
        Aggregate trending stocks from all sources
        Returns consolidated list with mention counts and sentiment
        """
        try:
            # Scrape all sources in parallel
            results = await asyncio.gather(
                self.scrape_reddit_wallstreetbets(),
                self.scrape_stocktwits(),
                self.scrape_reddit_stocks(),
                return_exceptions=True
            )

            # Flatten results and aggregate by ticker
            ticker_data = defaultdict(lambda: {
                'ticker': '',
                'mention_count': 0,
                'sources': defaultdict(int),
                'top_snippets': [],
                'sentiment_scores': [],
                'total_score': 0
            })

            for result in results:
                if isinstance(result, Exception):
                    print(f"Error in scraping: {result}")
                    continue

                if not result:
                    continue

                for stock in result:
                    ticker = stock['ticker']
                    source = stock['source']
                    mentions = stock['mention_count']

                    ticker_data[ticker]['ticker'] = ticker
                    ticker_data[ticker]['mention_count'] += mentions
                    ticker_data[ticker]['sources'][source] += mentions

                    # Add snippets
                    for post in stock.get('posts', [])[:3]:
                        ticker_data[ticker]['top_snippets'].append({
                            'text': post.get('text', ''),
                            'url': post.get('url', ''),
                            'author': post.get('author', 'Anonymous'),
                            'source': source
                        })

                    # Aggregate sentiment
                    if 'avg_sentiment' in stock:
                        ticker_data[ticker]['sentiment_scores'].append(stock['avg_sentiment'])

                    # Calculate total score (mentions + sentiment boost)
                    ticker_data[ticker]['total_score'] = ticker_data[ticker]['mention_count']

            # Convert to list and calculate final sentiment
            trending_stocks = []
            for ticker, data in ticker_data.items():
                sentiment_scores = data['sentiment_scores']
                avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0

                # Boost score for positive sentiment
                final_score = data['total_score'] + (avg_sentiment * 10)

                trending_stocks.append({
                    'ticker': ticker,
                    'mention_count': data['mention_count'],
                    'sources': dict(data['sources']),
                    'top_snippets': data['top_snippets'][:5],  # Top 5 snippets
                    'sentiment_score': round(avg_sentiment, 2),
                    'trending_score': int(final_score),
                    'published_at': datetime.now().isoformat()
                })

            # Sort by trending score
            trending_stocks.sort(key=lambda x: x['trending_score'], reverse=True)

            # Return top 50
            return trending_stocks[:50]

        except Exception as e:
            print(f"Error aggregating trending stocks: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_trending_stocks(self, limit: int = 30) -> List[Dict]:
        """
        Main method to get trending stocks
        Returns enriched data ready for API response
        """
        trending = await self.aggregate_trending_stocks()
        return trending[:limit]
