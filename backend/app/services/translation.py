from deep_translator import GoogleTranslator
from typing import Dict, Optional
import hashlib
import json
import os


class TranslationService:
    """Service for translating content to Hebrew"""

    def __init__(self):
        self.translator = GoogleTranslator(source='en', target='iw')  # 'iw' is the code for Hebrew
        self.cache_file = 'translation_cache.json'
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, str]:
        """Load translation cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_cache(self):
        """Save translation cache to file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key from text"""
        return hashlib.md5(text.encode()).hexdigest()

    def translate_to_hebrew(self, text: str) -> str:
        """
        Translate text to Hebrew with caching
        Returns: Hebrew translation or original text if translation fails
        """
        if not text or not text.strip():
            return text

        # Check cache first
        cache_key = self._get_cache_key(text)
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # Translate
            translated = self.translator.translate(text)

            # Cache the result
            self.cache[cache_key] = translated

            # Save cache periodically (every 10 translations)
            if len(self.cache) % 10 == 0:
                self._save_cache()

            return translated

        except Exception as e:
            print(f"Translation error: {e}")
            return text  # Return original if translation fails

    def translate_batch(self, texts: list) -> list:
        """
        Translate a list of texts to Hebrew
        Returns: List of Hebrew translations
        """
        translations = []
        for text in texts:
            translations.append(self.translate_to_hebrew(text))

        # Save cache after batch
        self._save_cache()

        return translations

    def translate_news_event(self, news: Dict) -> Dict:
        """
        Translate a news event dict to Hebrew
        Returns: Dict with Hebrew translations
        """
        hebrew_news = news.copy()

        try:
            if news.get('title'):
                hebrew_news['title_he'] = self.translate_to_hebrew(news['title'])

            if news.get('summary'):
                hebrew_news['summary_he'] = self.translate_to_hebrew(news['summary'])
        except:
            pass

        return hebrew_news

    def translate_signal(self, signal: Dict) -> Dict:
        """
        Translate a signal dict to Hebrew
        Returns: Dict with Hebrew translations
        """
        hebrew_signal = signal.copy()

        try:
            if signal.get('reason'):
                hebrew_signal['reason_he'] = self.translate_to_hebrew(signal['reason'])

            if signal.get('signal_type'):
                # Translate signal type
                signal_type_readable = signal['signal_type'].replace('_', ' ').title()
                hebrew_signal['signal_type_he'] = self.translate_to_hebrew(signal_type_readable)
        except:
            pass

        return hebrew_signal

    def translate_mover(self, mover: Dict) -> Dict:
        """
        Translate a top mover dict to Hebrew
        Returns: Dict with Hebrew translations
        """
        hebrew_mover = mover.copy()

        try:
            if mover.get('name'):
                hebrew_mover['name_he'] = self.translate_to_hebrew(mover['name'])

            if mover.get('reason'):
                hebrew_mover['reason_he'] = self.translate_to_hebrew(mover['reason'])
        except:
            pass

        return hebrew_mover

    def translate_ipo(self, ipo: Dict) -> Dict:
        """
        Translate an IPO dict to Hebrew
        Returns: Dict with Hebrew translations
        """
        hebrew_ipo = ipo.copy()

        try:
            if ipo.get('company'):
                hebrew_ipo['company_he'] = self.translate_to_hebrew(ipo['company'])

            if ipo.get('insights'):
                hebrew_ipo['insights_he'] = self.translate_batch(ipo['insights'])
        except:
            pass

        return hebrew_ipo

    def translate_momentum_stock(self, stock: Dict) -> Dict:
        """
        Translate a momentum stock dict to Hebrew
        Returns: Dict with Hebrew translations
        """
        hebrew_stock = stock.copy()

        try:
            if stock.get('title'):
                hebrew_stock['title_he'] = self.translate_to_hebrew(stock['title'])

            if stock.get('reason'):
                hebrew_stock['reason_he'] = self.translate_to_hebrew(stock['reason'])

            if stock.get('catalysts') and isinstance(stock['catalysts'], list):
                hebrew_stock['catalysts_he'] = self.translate_batch(stock['catalysts'])
        except:
            pass

        return hebrew_stock

    def __del__(self):
        """Save cache when service is destroyed"""
        self._save_cache()
