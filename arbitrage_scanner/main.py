"""
CLI entry point: run scanner, paper-trading simulator, and dashboard.
Educational use only; no real trading.
"""

import argparse
import logging
from datetime import date
from pathlib import Path

from .config import Config
from .scanner import Scanner
from .simulator import PaperTradingSimulator
from .utils import setup_logging

logger = logging.getLogger(__name__)


def _print_dashboard(
    config: Config,
    opportunities: list,
    simulator: PaperTradingSimulator,
) -> None:
    """Print a simple CLI dashboard: opportunities, entries, exits, PnL."""
    print("\n" + "=" * 60)
    print("  PREDICTION MARKET ARBITRAGE SCANNER (Paper Trading)")
    print("=" * 60)

    print("\n--- DETECTED OPPORTUNITIES ---")
    if not opportunities:
        print("  (none)")
    else:
        for o in opportunities:
            q = o.question[:50] + "..." if len(o.question) > 50 else o.question
            print(
                f"  [{o.market_id}] {q} | "
                f"edge={o.expected_profit_pct:.2f}% | cost={o.total_cost:.4f}"
            )

    print("\n--- SIMULATED ENTRIES ---")
    for e in simulator.entries:
        print(
            f"  {e.entry_date} | {e.market_id} | {e.capital_used:.2f} | "
            f"expected edge={e.expected_profit_pct:.2f}%"
        )
    if not simulator.entries:
        print("  (none)")

    print("\n--- SIMULATED EXITS ---")
    for x in simulator.exits:
        print(
            f"  {x.exit_date} | {x.market_id} | pnl={x.realized_pnl:.2f} ({x.realized_pnl_pct:.2f}%)"
        )
    if not simulator.exits:
        print("  (none)")

    print("\n--- VIRTUAL PnL ---")
    print(f"  Initial balance: {simulator.initial_balance:.2f}")
    print(f"  Current balance: {simulator.balance:.2f}")
    print(f"  Realized PnL:    {simulator.total_realized_pnl():.2f}")
    print(f"  Total PnL:       {simulator.total_pnl():.2f} ({simulator.total_pnl_pct():.2f}%)")
    print(f"  Open positions:  {len(simulator.open_positions)}")
    print("=" * 60 + "\n")


def main() -> int:
    """Run scanner, optionally simulate entries, and show dashboard."""
    parser = argparse.ArgumentParser(
        description="Prediction-market arbitrage scanner (paper trading, educational only)"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory containing binary_markets.json and multi_outcome_markets.json",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run paper-trading: enter first N opportunities and close them",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=3,
        help="Max number of simulated entries when --simulate (default: 3)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    config = Config()
    if args.data_dir is not None:
        config.data_dir = args.data_dir

    scanner = Scanner(config)
    opportunities = scanner.run()
    simulator = PaperTradingSimulator(config)

    if args.simulate and opportunities:
        today = date.today()
        for o in opportunities[: args.max_entries]:
            ok, msg = simulator.try_enter(o, as_of_date=today)
            if not ok:
                logger.warning("Skip entry %s: %s", o.market_id, msg)
        # Simulate closing all open positions
        for pos in list(simulator.open_positions):
            simulator.close_position(pos.market_id, as_of_date=today)

    _print_dashboard(config, opportunities, simulator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
