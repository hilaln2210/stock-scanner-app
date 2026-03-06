#!/usr/bin/env python3
"""
מריץ סדרת שאלות על הבוט ומדפיס תשובות.
דורש: שרת רץ (localhost:8000), GROQ_API_KEY ב-.env.
הרצה: מהתיקייה backend: python3 scripts/bot_questions.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# אפשר לשנות לרשימה קצרה להרצה מהירה (למשל QUESTIONS[:4])
QUESTIONS = [
    "/start",
    "/top",
    "/market",
    "מי לדעתך המניה שתעלה היום מעל 20 אחוז?",
    "מה יש לי בתיק?",
    "אילו מניות מובילות בסורק כרגע?",
    "מה דעתך על AAPL?",
    "/news AAPL",
    "/ta AAPL",
]


async def main():
    from app.services.telegram_bot import _handle_command, _CHAT_HISTORY

    print("בודק שרת...")
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("http://localhost:8000/api/health", timeout=aiohttp.ClientTimeout(total=3)) as r:
                if r.status != 200:
                    print("שרת לא מחזיר 200. הרץ את הבקאנד (run_server.sh) ונסה שוב.")
                    return
    except Exception as e:
        print(f"שרת לא זמין: {e}. הרץ את הבקאנד ונסה שוב.")
        return
    print("שרת פעיל. שולח שאלות לבוט...\n")

    for i, q in enumerate(QUESTIONS, 1):
        _CHAT_HISTORY.clear()
        print(f"--- שאלה {i}: {q[:60]}{'...' if len(q) > 60 else ''} ---")
        try:
            out, _ = await _handle_command(q)
            # truncate long answers for readability
            display = out[:500] + "..." if len(out) > 500 else out
            print(display)
        except Exception as e:
            print(f"שגיאה: {e}")
        print()
    print("סיום.")


if __name__ == "__main__":
    asyncio.run(main())
