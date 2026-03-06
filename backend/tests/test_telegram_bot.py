"""
מבחנים לבוט הטלגרם — סורק ותיק.
דורש: שרת רץ על localhost:8000, GROQ_API_KEY ב-.env.
הרצה: מהתיקייה backend: pytest tests/test_telegram_bot.py -v
"""
import asyncio
import os
import sys

import pytest

# Backend root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import aiohttp
except ImportError:
    aiohttp = None


async def _server_up() -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8000/api/health",
                timeout=aiohttp.ClientTimeout(total=3),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def server_required():
    """דורש שרת פעיל; מדלג על כל המודול אם השרת לא עולה."""
    loop = asyncio.new_event_loop()
    try:
        up = loop.run_until_complete(_server_up())
        if not up:
            pytest.skip("שרת לא רץ על localhost:8000 — הרץ את הבקאנד והרץ שוב את המבחנים.")
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_cmd_start(server_required):
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/start")
    assert out
    assert "פקודות" in out or "Trading" in out or "אלפא" in out


@pytest.mark.asyncio
async def test_cmd_status(server_required):
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/status")
    assert out
    assert "❌" not in out or "מצב התיק" in out
    assert "תיק" in out or "הון" in out or "פוזיציות" in out or "$" in out


@pytest.mark.asyncio
async def test_cmd_portfolio(server_required):
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/portfolio")
    assert out
    assert "❌" not in out or "פוזיציות" in out
    assert "פוזיציות" in out or "אין פוזיציות" in out


@pytest.mark.asyncio
async def test_cmd_top(server_required):
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/top")
    assert out
    assert "שגיאה" not in out
    assert "Top 5" in out or "מניות" in out or "אין נתונים" in out


@pytest.mark.asyncio
async def test_cmd_market(server_required):
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/market")
    assert out
    assert "שגיאה" not in out
    assert "משטר" in out or "שוק" in out or "רוחב" in out


@pytest.mark.asyncio
async def test_cmd_news(server_required):
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/news")
    assert out
    assert "שגיאה" not in out
    assert "חדשות" in out or "אין" in out or "📰" in out


@pytest.mark.asyncio
async def test_free_text_who_goes_up_20(server_required):
    """שאלה: מי תעלה מעל 20%? — הבוט צריך להתייחס לנתוני הסורק (אין מניה / מובילות)."""
    from app.services.telegram_bot import _handle_command, _CHAT_HISTORY

    _CHAT_HISTORY.clear()
    out, _ = await _handle_command("מי לדעתך המניה שתעלה היום מעל 20 אחוז?")
    assert out
    assert "אין מפתח" not in out
    # תשובה צריכה להתייחס למציאות: או שאין מניה מעל 20%, או לצטט מובילות
    assert any(
        x in out
        for x in [
            "אין מניה",
            "אף מניה",
            "מעל 20",
            "20%",
            "המובילות",
            "כרגע",
            "%",
        ]
    )


@pytest.mark.asyncio
async def test_free_text_what_in_portfolio(server_required):
    """שאלה: מה יש בתיק? — הבוט צריך להתייחס לתיק."""
    from app.services.telegram_bot import _handle_command, _CHAT_HISTORY

    _CHAT_HISTORY.clear()
    out, _ = await _handle_command("מה יש לי בתיק?")
    assert out
    assert "אין מפתח" not in out
    assert any(
        x in out for x in ["תיק", "פוזיציות", "מניה", "מניות", "$", "אין"]
    )


@pytest.mark.asyncio
async def test_free_text_top_scanner(server_required):
    """שאלה על הסורק — מה המובילות / טופ בסורק."""
    from app.services.telegram_bot import _handle_command, _CHAT_HISTORY

    _CHAT_HISTORY.clear()
    out, _ = await _handle_command("אילו מניות מובילות בסורק כרגע?")
    assert out
    assert "אין מפתח" not in out
    assert any(
        x in out for x in ["מניה", "מניות", "%", "עולה", "טופ", "סורק"]
    )


@pytest.mark.asyncio
async def test_ta_ticker(server_required):
    """פקודת /ta עם טיקר — לא קורס, מחזיר ניתוח או הודעה ברורה."""
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/ta AAPL")
    assert out
    assert "❌" in out or "סיגנל" in out or "תמיכה" in out or "טכני" in out or "לא נמצא" in out


@pytest.mark.asyncio
async def test_cmd_help(server_required):
    """פקודת /help — מציגה פקודות."""
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/help")
    assert out
    assert "שגיאה" not in out
    assert any(x in out for x in ["/top", "פקודות", "/ta", "/news"])


@pytest.mark.asyncio
async def test_free_text_which_stock_rises_most(server_required):
    """שאלה: איזו מניה תעלה הכי הרבה? — התייחסות לנתוני הסורק."""
    from app.services.telegram_bot import _handle_command, _CHAT_HISTORY

    _CHAT_HISTORY.clear()
    out, _ = await _handle_command("איזו מניה תעלה הכי הרבה היום?")
    assert out
    assert "אין מפתח" not in out
    assert any(
        x in out
        for x in ["מניה", "מניות", "%", "עולה", "טופ", "סורק", "מובילות", "כרגע"]
    )


@pytest.mark.asyncio
async def test_free_text_whats_the_situation(server_required):
    """שאלה: מה המצב? — הבוט מגיב על שוק/תיק."""
    from app.services.telegram_bot import _handle_command, _CHAT_HISTORY

    _CHAT_HISTORY.clear()
    out, _ = await _handle_command("מה המצב?")
    assert out
    assert "אין מפתח" not in out
    assert any(
        x in out for x in ["תיק", "שוק", "מצב", "מניות", "סורק", "$", "משטר"]
    )


@pytest.mark.asyncio
async def test_news_with_ticker(server_required):
    """פקודת /news עם טיקר — חדשות למניה."""
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/news AAPL")
    assert out
    assert "שגיאה" not in out
    assert "חדשות" in out or "AAPL" in out or "אין" in out or "📰" in out


@pytest.mark.asyncio
async def test_insider(server_required):
    """פקודת /insider — פעילות אנשי פנים."""
    from app.services.telegram_bot import _handle_command

    out, _ = await _handle_command("/insider")
    assert out
    assert "שגיאה" not in out
    assert "פנים" in out or "insider" in out or "אין" in out or "מניה" in out


@pytest.mark.asyncio
async def test_free_text_ticker_question(server_required):
    """שאלה על מניה ספציפית — למשל AAPL."""
    from app.services.telegram_bot import _handle_command, _CHAT_HISTORY

    _CHAT_HISTORY.clear()
    out, _ = await _handle_command("מה דעתך על AAPL?")
    assert out
    assert "אין מפתח" not in out
    assert any(
        x in out for x in ["AAPL", "מניה", "מחיר", "עלייה", "ירידה", "%", "RSI"]
    )
