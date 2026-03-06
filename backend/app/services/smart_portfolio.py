"""
Smart Demo Portfolio — AI-driven autonomous trading with learning.

Brain: Gemini Free API / Rule-Based Engine (fallback).
Capital: $3,000 virtual.
Risk: max 20% per position, 5% daily loss limit, trailing stop, partial TP.
Learning: Post-mortem after each closed trade → adjust AI weights.
"""
import json
import math
from datetime import datetime
from typing import Optional
from pathlib import Path

from app.config import settings

DATA_DIR = Path(__file__).parent.parent.parent / "data"
try:
    DATA_DIR.mkdir(exist_ok=True)
except OSError:
    pass  # read-only או סביבה בענן — נתונים יתאפסו
PORTFOLIO_FILE = DATA_DIR / "smart_portfolio.json"
TRADE_HISTORY_FILE = DATA_DIR / "trade_history.json"
LEARNING_FILE = DATA_DIR / "ai_learning.json"

INITIAL_CAPITAL = 3000.0
MAX_POSITION_PCT = 0.30          # 30% per position — big bets on conviction
DAILY_LOSS_LIMIT_PCT = 0.10      # 10% daily loss limit — room for volatile plays
DEFAULT_STOP_LOSS_PCT = 0.08     # 8% stop loss — wider stops
DEFAULT_TARGET_PCT = 0.20        # 20% target — let winners run big
MAX_POSITIONS = 5                # 5 positions — maximum exposure


def _load_json(path: Path, default=None):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default if default is not None else {}


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, default=str))


class SmartPortfolio:
    def __init__(self):
        self._load()

    def _load(self):
        state = _load_json(PORTFOLIO_FILE, {
            'cash': INITIAL_CAPITAL,
            'positions': {},
            'equity_history': [{'date': datetime.now().isoformat(), 'equity': INITIAL_CAPITAL}],
            'daily_pnl': 0,
            'last_reset_date': datetime.now().strftime('%Y-%m-%d'),
            'total_trades': 0,
            'winning_trades': 0,
            'total_pnl': 0,
            'peak_equity': INITIAL_CAPITAL,
        })
        self.cash = state.get('cash', INITIAL_CAPITAL)
        self.positions = state.get('positions', {})
        self.equity_history = state.get('equity_history', [])
        self.daily_pnl = state.get('daily_pnl', 0)
        self.last_reset_date = state.get('last_reset_date', '')
        self.total_trades = state.get('total_trades', 0)
        self.winning_trades = state.get('winning_trades', 0)
        self.total_pnl = state.get('total_pnl', 0)
        self.peak_equity = state.get('peak_equity', INITIAL_CAPITAL)

    def _save(self):
        try:
            DATA_DIR.mkdir(exist_ok=True)
            _save_json(PORTFOLIO_FILE, {
                'cash': self.cash,
                'positions': self.positions,
                'equity_history': self.equity_history[-500:],
                'daily_pnl': self.daily_pnl,
                'last_reset_date': self.last_reset_date,
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'total_pnl': self.total_pnl,
                'peak_equity': self.peak_equity,
            })
        except OSError:
            pass  # סביבה read-only (למשל בענן בלי volume)

    def _check_daily_reset(self):
        today = datetime.now().strftime('%Y-%m-%d')
        if self.last_reset_date != today:
            self.daily_pnl = 0
            self.last_reset_date = today

    def get_total_equity(self, live_prices: dict) -> float:
        equity = self.cash
        for ticker, pos in self.positions.items():
            current_price = live_prices.get(ticker, pos['entry_price'])
            if pos['side'] == 'long':
                equity += pos['qty'] * current_price
            else:
                equity += pos['qty'] * (2 * pos['entry_price'] - current_price)
        return equity

    def can_open_position(self, live_prices: dict) -> bool:
        self._check_daily_reset()
        equity = self.get_total_equity(live_prices)
        if self.daily_pnl < -equity * DAILY_LOSS_LIMIT_PCT:
            return False
        return True

    def open_position(self, ticker: str, side: str, price: float, qty: int,
                      stop_loss: float, target: float, reason: str) -> dict:
        equity = self.cash
        cost = price * qty
        if cost > equity * MAX_POSITION_PCT:
            qty = int((equity * MAX_POSITION_PCT) / price)
            cost = price * qty
        if qty <= 0 or cost > self.cash:
            return {'success': False, 'error': 'Insufficient funds or zero quantity'}

        self.cash -= cost
        self.positions[ticker] = {
            'side': side, 'qty': qty,
            'entry_price': price, 'entry_time': datetime.now().isoformat(),
            'stop_loss': stop_loss, 'target': target,
            'highest_price': price, 'lowest_price': price,
            'trailing_active': False,
            'partial_taken': False,
            'reason': reason,
        }
        self._save()
        return {'success': True, 'ticker': ticker, 'qty': qty, 'price': price}

    def close_position(self, ticker: str, price: float, reason: str = '', partial_pct: float = 0) -> dict:
        pos = self.positions.get(ticker)
        if not pos:
            return {'success': False, 'error': 'No position'}

        close_qty = pos['qty']
        if 0 < partial_pct < 1:
            close_qty = max(1, int(pos['qty'] * partial_pct))

        pnl = 0
        if pos['side'] == 'long':
            pnl = (price - pos['entry_price']) * close_qty
        else:
            pnl = (pos['entry_price'] - price) * close_qty

        self.cash += pos['entry_price'] * close_qty + pnl
        self.daily_pnl += pnl
        self.total_pnl += pnl
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1

        trade_record = {
            'ticker': ticker, 'side': pos['side'],
            'entry_price': pos['entry_price'], 'exit_price': price,
            'qty': close_qty, 'pnl': round(pnl, 2),
            'pnl_pct': round(pnl / (pos['entry_price'] * close_qty) * 100, 2),
            'entry_time': pos['entry_time'],
            'exit_time': datetime.now().isoformat(),
            'entry_reason': pos.get('reason', ''),
            'exit_reason': reason,
            'holding_minutes': 0,
            'was_partial': partial_pct > 0,
        }
        try:
            entry_dt = datetime.fromisoformat(pos['entry_time'])
            trade_record['holding_minutes'] = int((datetime.now() - entry_dt).total_seconds() / 60)
        except Exception:
            pass

        history = _load_json(TRADE_HISTORY_FILE, [])
        history.append(trade_record)
        _save_json(TRADE_HISTORY_FILE, history[-1000:])

        remaining_qty = pos['qty'] - close_qty
        if remaining_qty > 0:
            self.positions[ticker] = {**pos, 'qty': remaining_qty, 'partial_taken': True}
        else:
            del self.positions[ticker]
        self._save()
        return {'success': True, 'pnl': round(pnl, 2), 'trade': trade_record}

    def check_stops(self, live_prices: dict, stock_data: dict = None) -> list:
        """Auto-close positions hitting SL/TP, with ATR-adaptive trailing stop."""
        closed = []
        stock_data = stock_data or {}

        for ticker in list(self.positions.keys()):
            pos = self.positions[ticker]
            price = live_prices.get(ticker)
            if not price:
                continue

            is_long = pos['side'] == 'long'

            if is_long:
                if price > pos.get('highest_price', price):
                    pos['highest_price'] = price
                if price < pos.get('lowest_price', price):
                    pos['lowest_price'] = price
            else:
                if price < pos.get('lowest_price', price):
                    pos['lowest_price'] = price
                if price > pos.get('highest_price', price):
                    pos['highest_price'] = price

            entry = pos['entry_price']
            pnl_pct = ((price - entry) / entry * 100) if is_long else ((entry - price) / entry * 100)

            # ATR-based trail distance (adaptive to volatility)
            sd = stock_data.get(ticker, {})
            atr_val = 0
            try:
                atr_val = float(str(sd.get('atr', '0')).replace(',', ''))
            except (ValueError, TypeError):
                pass
            # ATR trail = 2x ATR, bounded between 3% and 12%
            if atr_val > 0 and price > 0:
                atr_trail_pct = min(12, max(3, (atr_val * 2 / price) * 100))
            else:
                atr_trail_pct = 5  # fallback

            # Partial take-profit: close 40% at +7% (only once) — let more ride
            if pnl_pct >= 7 and not pos.get('partial_taken') and pos['qty'] >= 2:
                r = self.close_position(ticker, price, f'Partial TP at +{pnl_pct:.1f}%', partial_pct=0.4)
                if r.get('success'):
                    closed.append(r['trade'])
                    pos = self.positions.get(ticker)
                    if not pos:
                        continue

            # Trailing stop activation at +4%
            if pnl_pct >= 4 and not pos.get('trailing_active'):
                pos['trailing_active'] = True
                pos['atr_trail_pct'] = atr_trail_pct
                if is_long:
                    new_sl = max(pos['stop_loss'], entry * 1.01)
                    pos['stop_loss'] = round(new_sl, 2)
                else:
                    new_sl = min(pos['stop_loss'], entry * 0.99)
                    pos['stop_loss'] = round(new_sl, 2)

            # ATR-adaptive trailing stop
            trail_pct = pos.get('atr_trail_pct', atr_trail_pct) / 100
            if pos.get('trailing_active'):
                if is_long:
                    trail_sl = pos['highest_price'] * (1 - trail_pct)
                    if trail_sl > pos['stop_loss']:
                        pos['stop_loss'] = round(trail_sl, 2)
                else:
                    trail_sl = pos['lowest_price'] * (1 + trail_pct)
                    if trail_sl < pos['stop_loss']:
                        pos['stop_loss'] = round(trail_sl, 2)

            # Check stop loss
            if is_long and price <= pos['stop_loss']:
                reason = 'Trailing stop' if pos.get('trailing_active') else 'Stop loss'
                r = self.close_position(ticker, price, reason)
                if r.get('success'):
                    closed.append(r['trade'])
                continue
            if not is_long and price >= pos['stop_loss']:
                reason = 'Trailing stop' if pos.get('trailing_active') else 'Stop loss'
                r = self.close_position(ticker, price, reason)
                if r.get('success'):
                    closed.append(r['trade'])
                continue

            # Check target
            if is_long and price >= pos['target']:
                r = self.close_position(ticker, price, 'Target reached')
                if r.get('success'):
                    closed.append(r['trade'])
            elif not is_long and price <= pos['target']:
                r = self.close_position(ticker, price, 'Target reached')
                if r.get('success'):
                    closed.append(r['trade'])

            self._save()
        return closed

    def record_equity(self, live_prices: dict):
        equity = self.get_total_equity(live_prices)
        if equity > self.peak_equity:
            self.peak_equity = equity
        self.equity_history.append({
            'date': datetime.now().isoformat(),
            'equity': round(equity, 2),
        })
        self._save()

    def get_stats(self, live_prices: dict) -> dict:
        equity = self.get_total_equity(live_prices)
        if equity > self.peak_equity:
            self.peak_equity = equity
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        history = _load_json(TRADE_HISTORY_FILE, [])
        wins = [t for t in history if t.get('pnl', 0) > 0]
        losses = [t for t in history if t.get('pnl', 0) <= 0]
        avg_win = (sum(t['pnl'] for t in wins) / len(wins)) if wins else 0
        avg_loss = (sum(t['pnl'] for t in losses) / len(losses)) if losses else 0
        profit_factor = abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else 0
        avg_holding = (sum(t.get('holding_minutes', 0) for t in history) / len(history)) if history else 0
        best_trade = max(history, key=lambda t: t.get('pnl', 0)) if history else None
        worst_trade = min(history, key=lambda t: t.get('pnl', 0)) if history else None

        # Max drawdown
        drawdown = ((self.peak_equity - equity) / self.peak_equity * 100) if self.peak_equity > 0 else 0
        max_dd = drawdown
        eq_hist = [p.get('equity', INITIAL_CAPITAL) for p in self.equity_history]
        if len(eq_hist) > 1:
            peak = eq_hist[0]
            for e in eq_hist:
                if e > peak:
                    peak = e
                dd = (peak - e) / peak * 100
                if dd > max_dd:
                    max_dd = dd

        # Sharpe ratio (simplified: daily returns)
        sharpe = 0
        if len(eq_hist) > 2:
            daily_returns = [(eq_hist[i] - eq_hist[i - 1]) / eq_hist[i - 1] for i in range(1, len(eq_hist)) if eq_hist[i - 1] > 0]
            if daily_returns:
                mean_r = sum(daily_returns) / len(daily_returns)
                std_r = math.sqrt(sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)) if len(daily_returns) > 1 else 1
                sharpe = round((mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0, 2)

        return {
            'cash': round(self.cash, 2),
            'equity': round(equity, 2),
            'total_pnl': round(self.total_pnl, 2),
            'total_pnl_pct': round(self.total_pnl / INITIAL_CAPITAL * 100, 2),
            'daily_pnl': round(self.daily_pnl, 2),
            'positions': self.positions,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': round(win_rate, 1),
            'equity_history': self.equity_history[-200:],
            'initial_capital': INITIAL_CAPITAL,
            'peak_equity': round(self.peak_equity, 2),
            'max_drawdown': round(max_dd, 2),
            'sharpe_ratio': sharpe,
            'profit_factor': round(profit_factor, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'avg_holding_minutes': round(avg_holding, 1),
            'best_trade': best_trade,
            'worst_trade': worst_trade,
        }

    def get_trade_history(self) -> list:
        return _load_json(TRADE_HISTORY_FILE, [])

    def reset(self):
        self.cash = INITIAL_CAPITAL
        self.positions = {}
        self.equity_history = [{'date': datetime.now().isoformat(), 'equity': INITIAL_CAPITAL}]
        self.daily_pnl = 0
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0
        self.peak_equity = INITIAL_CAPITAL
        self._save()
        _save_json(TRADE_HISTORY_FILE, [])


smart_portfolio = SmartPortfolio()
