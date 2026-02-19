from deep_translator import GoogleTranslator
from typing import Dict, List, Optional
import asyncio
import aiohttp
from functools import lru_cache


class TranslationService:
    """Translates stock data and news to Hebrew"""

    def __init__(self):
        self.translator_en_to_he = GoogleTranslator(source='en', target='iw')  # 'iw' is Hebrew in Google Translate
        self.cache = {}

    async def batch_translate_parallel(self, texts: List[str], target_lang: str = 'he') -> List[str]:
        """Fast parallel batch translation using Google Translate free API.
        Translates all texts concurrently with caching."""
        if not texts or target_lang == 'en':
            return texts

        tl = 'iw' if target_lang == 'he' else target_lang
        url = 'https://translate.googleapis.com/translate_a/single'
        sem = asyncio.Semaphore(20)

        results = [''] * len(texts)
        uncached_indices = []
        uncached_texts = []

        # Check cache first
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = text or ''
                continue
            cache_key = f"{text}_{target_lang}"
            if cache_key in self.cache:
                results[i] = self.cache[cache_key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if not uncached_texts:
            return results

        async def translate_one(session, text, local_idx):
            async with sem:
                try:
                    params = {
                        'client': 'gtx',
                        'sl': 'en',
                        'tl': tl,
                        'dt': 't',
                        'q': text,
                    }
                    async with session.get(url, params=params) as resp:
                        data = await resp.json(content_type=None)
                        if data and isinstance(data[0], list):
                            translated = ''.join(
                                part[0] for part in data[0] if part and part[0]
                            )
                            return local_idx, translated
                except Exception as e:
                    print(f"Batch translate error for item {local_idx}: {e}")
                return local_idx, text

        async with aiohttp.ClientSession() as session:
            tasks = [
                translate_one(session, text, j)
                for j, text in enumerate(uncached_texts)
            ]
            done = await asyncio.gather(*tasks)

            for local_idx, translated in done:
                real_idx = uncached_indices[local_idx]
                results[real_idx] = translated
                # Cache the result
                cache_key = f"{uncached_texts[local_idx]}_{target_lang}"
                self.cache[cache_key] = translated

        return results

    @lru_cache(maxsize=500)
    def translate_text(self, text: str, target_lang: str = 'he') -> str:
        """Translate text with caching to avoid repeated translations"""
        if not text or target_lang == 'en':
            return text

        try:
            # Check cache first
            cache_key = f"{text}_{target_lang}"
            if cache_key in self.cache:
                return self.cache[cache_key]

            # Translate
            translated = self.translator_en_to_he.translate(text)

            # Cache result
            self.cache[cache_key] = translated
            return translated
        except Exception as e:
            print(f"Translation error: {e}")
            return text  # Return original text on error

    async def translate_stock(self, stock: Dict, target_lang: str = 'he') -> Dict:
        """Translate a single stock's fields"""
        if target_lang == 'en':
            return stock

        translated_stock = stock.copy()

        # Translate title
        if 'title' in stock and stock['title']:
            translated_stock['title'] = self.translate_text(stock['title'], target_lang)

        # Translate live_data fields if present
        if 'live_data' in stock and stock['live_data']:
            live_data = stock['live_data'].copy()

            # Translate sector
            if 'sector' in live_data and live_data['sector'] != 'Unknown':
                live_data['sector_en'] = live_data['sector']  # Keep English version
                live_data['sector'] = self.translate_text(live_data['sector'], target_lang)

            # Translate industry
            if 'industry' in live_data and live_data['industry'] != 'Unknown':
                live_data['industry_en'] = live_data['industry']
                live_data['industry'] = self.translate_text(live_data['industry'], target_lang)

            # Translate company name (keep original for reference)
            if 'company_name' in live_data and live_data['company_name']:
                live_data['company_name_en'] = live_data['company_name']
                # Don't translate company name, keep it in English

            # Translate business summary
            if 'business_summary' in live_data and live_data['business_summary']:
                live_data['business_summary'] = self.translate_text(
                    live_data['business_summary'],
                    target_lang
                )

            translated_stock['live_data'] = live_data

        # Translate top_snippets for trending stocks
        if 'top_snippets' in stock and stock['top_snippets']:
            translated_snippets = []
            for snippet in stock['top_snippets']:
                translated_snippet = snippet.copy()
                if 'text' in snippet and snippet['text']:
                    translated_snippet['text'] = self.translate_text(snippet['text'], target_lang)
                translated_snippets.append(translated_snippet)
            translated_stock['top_snippets'] = translated_snippets

        # Translate business_summary (top-level, from VWAP screener)
        if 'business_summary' in stock and stock['business_summary']:
            translated_stock['business_summary'] = self.translate_text(
                stock['business_summary'], target_lang
            )

        # Translate news items (top-level, from VWAP screener)
        if 'news' in stock and stock['news']:
            translated_news = []
            for item in stock['news']:
                translated_item = item.copy()
                if 'title' in item and item['title']:
                    translated_item['title'] = self.translate_text(item['title'], target_lang)
                translated_news.append(translated_item)
            translated_stock['news'] = translated_news

        return translated_stock

    async def translate_stocks(self, stocks: List[Dict], target_lang: str = 'he') -> List[Dict]:
        """Translate a list of stocks"""
        if target_lang == 'en':
            return stocks

        # Translate all stocks in parallel for speed
        tasks = [self.translate_stock(stock, target_lang) for stock in stocks]
        translated_stocks = await asyncio.gather(*tasks)

        return list(translated_stocks)

    async def translate_news_item(self, news_item: Dict, target_lang: str = 'he') -> Dict:
        """Translate a news item"""
        if target_lang == 'en':
            return news_item

        translated_item = news_item.copy()

        # Translate title
        if 'title' in news_item and news_item['title']:
            translated_item['title'] = self.translate_text(news_item['title'], target_lang)

        # Translate description/summary if present
        if 'description' in news_item and news_item['description']:
            translated_item['description'] = self.translate_text(
                news_item['description'],
                target_lang
            )

        if 'summary' in news_item and news_item['summary']:
            translated_item['summary'] = self.translate_text(
                news_item['summary'],
                target_lang
            )

        return translated_item

    async def translate_news(self, news: List[Dict], target_lang: str = 'he') -> List[Dict]:
        """Translate a list of news items"""
        if target_lang == 'en':
            return news

        # Translate all news items in parallel for speed
        tasks = [self.translate_news_item(item, target_lang) for item in news]
        translated_news = await asyncio.gather(*tasks)

        return list(translated_news)


# Global instance
translation_service = TranslationService()
