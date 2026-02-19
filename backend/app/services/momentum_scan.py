from datetime import datetime
from uuid import uuid4
from typing import Tuple

from app.schemas.scan_models import PriceVolSummary, FundamentalsSummary, ScanResult


def _calc_momentum_score(pv: PriceVolSummary) -> int:
    """Compute a 0-100 momentum score from price-change inputs."""
    score = 50

    # recent vs 1w/1m/3m
    def pct_change(a, b):
        try:
            return (a - b) / b * 100 if b and b != 0 else 0
        except Exception:
            return 0

    if pv.price_1w:
        score += max(-30, min(30, pct_change(pv.price_last, pv.price_1w)))
    if pv.price_1m:
        score += max(-20, min(20, pct_change(pv.price_last, pv.price_1m) * 0.6))
    if pv.price_3m:
        score += max(-10, min(10, pct_change(pv.price_last, pv.price_3m) * 0.3))

    # volume relative to adv20
    if pv.adv20 and pv.volume_last:
        try:
            vol_ratio = pv.volume_last / pv.adv20
            if vol_ratio > 3:
                score += 10
            elif vol_ratio > 1.5:
                score += 6
            elif vol_ratio < 0.5:
                score -= 6
        except Exception:
            pass

    return int(max(0, min(100, score)))


def _calc_risk_score(f: FundamentalsSummary) -> int:
    """Compute a 0-100 risk score (higher = more risky)."""
    score = 30

    # short interest
    if f.short_interest_pct is not None:
        score += min(40, int(f.short_interest_pct * 1.5))

    # small market cap increases risk
    if f.market_cap is not None:
        # thresholds: <200M high risk, <2B medium, else lower
        if f.market_cap < 200e6:
            score += 25
        elif f.market_cap < 2e9:
            score += 12

    # very low liquidity (float/shares) increases risk
    if f.float_shares is not None and f.float_shares < 5e6:
        score += 12

    # revenue growth negative
    if f.revenue_yoy_pct is not None and f.revenue_yoy_pct < 0:
        score += min(15, int(abs(f.revenue_yoy_pct) * 0.5))

    return int(max(0, min(100, score)))


def _choose_status(momentum: int, risk: int) -> Tuple[str, str]:
    """Return (status, final_tag)"""
    if momentum >= 70 and risk <= 50:
        return "HealthyMomentum", "Long"
    if momentum >= 55 and risk <= 65:
        return "Watchlist", "Consider"
    if momentum < 40 and risk > 60:
        return "RiskFlag", "Short/ Avoid"
    return "Neutral", "Monitor"


def scan_ticker(pv: PriceVolSummary, f: FundamentalsSummary) -> ScanResult:
    """Public scanner function used by API. Returns a `ScanResult` model."""
    mom = _calc_momentum_score(pv)
    risk = _calc_risk_score(f)
    status, final_tag = _choose_status(mom, risk)

    # short explanation
    expl = []
    expl.append(f"Momentum {mom}/100; Risk {risk}/100.")
    if mom >= 70:
        expl.append("Strong short-term momentum.")
    elif mom < 40:
        expl.append("Weak momentum.")
    if risk > 60:
        expl.append("Elevated fundamental / liquidity risk.")

    result = ScanResult(
        id=str(uuid4()),
        ticker=pv.ticker,
        generated_at=datetime.utcnow(),
        status=status,
        score_momentum=mom,
        score_risk=risk,
        final_tag=final_tag,
        short_explanation=" ".join(expl),
        top_risk=("High short interest" if f.short_interest_pct and f.short_interest_pct > 15 else None),
        components={"momentum": mom, "risk": risk},
        key_metrics={
            "price_last": pv.price_last,
            "adv20": pv.adv20,
            "market_cap": f.market_cap,
            "short_interest_pct": f.short_interest_pct,
        },
        related_events=None,
        ttl_seconds=3600,
    )

    return result
from __future__ import annotations
from datetime import datetime
from typing import Dict, Any
from . import __name__
from ..schemas.scan_models import PriceVolSummary, FundamentalsSummary, ScanResult


def _pct(a: float, b: float) -> float:
    if b == 0 or b is None:
        return 0.0
    try:
        return (a / b - 1.0) * 100.0
    except Exception:
        return 0.0


def _clamp01(x: float) -> float:
    if x is None:
        return 0.0
    if x != x:
        return 0.0
    return max(0.0, min(1.0, x))


def _sigmoid(x: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-x))


def compute_scores(pv: PriceVolSummary, f: FundamentalsSummary) -> Dict[str, Any]:
    # primitives
    price_now = pv.price_last
    price_1w = pv.price_1w or price_now
    price_1m = pv.price_1m or price_now
    price_3m = pv.price_3m or price_now

    pchg_7d = _pct(price_now, price_1w)
    pchg_1m = _pct(price_now, price_1m)
    pchg_3m = _pct(price_now, price_3m)

    adv20 = pv.adv20 or 1.0
    vol_last = pv.volume_last or 0.0
    vol_ratio = vol_last / adv20 if adv20 and adv20 > 0 else 0.0

    revenue_yoy = (f.revenue_yoy_pct or 0.0)
    short_interest = (f.short_interest_pct or 0.0)
    ps = f.ps if f.ps is not None else None
    inst_flow = (f.institutional_flow or 0.0)

    # feature normalization
    # price momentum feature: map 3m change percentile-ish via logistic
    price_mom = _clamp01(_sigmoid((pchg_3m / 100.0 - 0.15) * 10.0))

    # volume feature: cap at 5x
    vol_cap = 5.0
    vol_feature = _clamp01((min(vol_ratio, vol_cap) - 1.0) / (vol_cap - 1.0))

    # fundamental health: simple composite of revenue growth and profitability trend
    rev_norm = _clamp01((revenue_yoy or 0.0) / 100.0)  # treat 100% as full
    eps_trend = 1.0 if (f.eps_ttm and f.eps_ttm > 0) else 0.3
    fundamental_health = _clamp01(0.6 * rev_norm + 0.4 * eps_trend)

    # institutional feature: normalize by a heuristic
    inst_feature = _clamp01(min(abs(inst_flow) / max((f.market_cap or 1.0) / 1e9, 1.0), 1.0))

    # short risk
    short_risk = _clamp01(short_interest / 50.0)

    # valuation penalty via P/S
    if ps is None:
        val_penalty = 0.3
    else:
        val_penalty = _clamp01(_sigmoid((ps - 10.0) / 5.0))

    # iv spike not available here; set to 0
    iv_spike = 0.0

    # raw scores
    score_momentum_raw = 0.40 * price_mom + 0.30 * vol_feature + 0.15 * inst_feature + 0.15 * 0.0
    score_risk_raw = 0.35 * vol_feature + 0.30 * (1.0 - fundamental_health) + 0.20 * short_risk + 0.10 * val_penalty + 0.05 * iv_spike

    score_momentum = int(round(_clamp01(score_momentum_raw) * 100))
    score_risk = int(round(_clamp01(score_risk_raw) * 100))

    # emergency flags
    emergency_risk = False
    if pchg_7d >= 50.0 or pchg_1m >= 100.0:
        # allow override by strong fundamentals & institutional
        if not (0.6 <= fundamental_health and inst_feature >= 0.4):
            emergency_risk = True
    if vol_ratio >= 5.0:
        emergency_risk = True

    # classification
    if emergency_risk or score_risk >= 70:
        status = "RiskFlag"
    elif score_momentum >= 65 and score_risk < 40 and fundamental_health >= 0.5:
        status = "HealthyMomentum"
    elif 40 <= score_momentum < 65:
        status = "Watchlist"
    else:
        status = "Neutral"

    # explanation (short)
    triggers = []
    if pchg_7d >= 50.0:
        triggers.append(f"+{int(pchg_7d)}% in 7d")
    elif pchg_1m >= 15.0:
        triggers.append(f"+{int(pchg_1m)}% in 1m")

    if vol_ratio >= 2.0:
        triggers.append(f"vol {vol_ratio:.1f}x ADV20")

    if revenue_yoy and revenue_yoy >= 20:
        triggers.append(f"rev {revenue_yoy:.0f}% YoY")

    if not triggers:
        triggers = ["no strong on-chain trigger"]

    top_risk = None
    if emergency_risk:
        top_risk = "sudden run / volume spike (possible pump)"
    elif short_risk >= 0.5:
        top_risk = "high short interest (volatile)"
    elif val_penalty >= 0.7:
        top_risk = "valuation stretched (high P/S)"
    else:
        top_risk = "liquidity / execution risk"

    explanation = f"Trigger: { '; '.join(triggers) }. Fundamentals: rev {revenue_yoy:.0f}% YoY; P/S: {ps or 'n/a'}."

    components = {
        "price": round(float(price_mom), 3),
        "volume": round(float(vol_feature), 3),
        "fundamentals": round(float(fundamental_health), 3),
        "institutional": round(float(inst_feature), 3),
        "short_risk": round(float(short_risk), 3),
        "valuation_penalty": round(float(val_penalty), 3),
    }

    key_metrics = {
        "1w_pct": round(pchg_7d, 2),
        "1m_pct": round(pchg_1m, 2),
        "3m_pct": round(pchg_3m, 2),
        "adv20": adv20,
        "vol_ratio": round(vol_ratio, 2),
        "revenue_yoy": revenue_yoy,
        "pe": f.pe,
        "ps": f.ps,
        "short_interest_pct": f.short_interest_pct,
    }

    result = {
        "id": f"scan:{datetime.utcnow().date()}:{pv.ticker}",
        "ticker": pv.ticker,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "status": status,
        "score_momentum": score_momentum,
        "score_risk": score_risk,
        "final_tag": status,
        "short_explanation": explanation,
        "top_risk": top_risk,
        "components": components,
        "key_metrics": key_metrics,
        "ttl_seconds": 7200,
    }

    return result


def scan_ticker(pv: PriceVolSummary, f: FundamentalsSummary) -> ScanResult:
    raw = compute_scores(pv, f)
    return ScanResult(**raw)
