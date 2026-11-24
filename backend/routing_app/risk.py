from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

LOW = "Low"
MODERATE = "Moderate"
HIGH = "High"
SEVERE = "Severe"
NO_TRAVEL = "No Travel"
UNKNOWN = "Unknown"

RISK_LEVELS = (LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL)
ALL_LEVELS = (LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL, UNKNOWN)

RISK_SCORE: dict[str, int] = {
    LOW: 1,
    MODERATE: 2,
    HIGH: 3,
    SEVERE: 4,
    NO_TRAVEL: 5,
}

SCORE_TO_LEVEL: dict[int, str] = {v: k for k, v in RISK_SCORE.items()}


def _is_valid_non_negative(value: float | None) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return False
    return not math.isnan(fval) and not math.isinf(fval) and fval >= 0.0


def classify_base_wind(wind_mph: float | None) -> str:
    """Classify wind speed (mph) without load adjustments per AGENTS.md §2.1.

    Boundaries:
    [0, 25) -> Low
    [25, 35) -> Moderate
    [35, 45) -> High
    [45, 55) -> Severe
    >= 55 -> No Travel
    """
    if not _is_valid_non_negative(wind_mph):
        return UNKNOWN
    w = float(wind_mph)  # type: ignore[arg-type]
    if w < 25.0:
        return LOW
    if w < 35.0:
        return MODERATE
    if w < 45.0:
        return HIGH
    if w < 55.0:
        return SEVERE
    return NO_TRAVEL


def classify_wind(wind_mph: float | None, load_lb: float) -> tuple[str, str | None]:
    """Classify wind speed (mph) with load rules applied per AGENTS.md §2.1 & §2.2.

    Returns (level, load_override_reason_or_None).
    Load rules:
    - Wind >= 55 mph -> No Travel for any load
    - Wind 45-54 ([45, 55)) mph and load > 30,000 lb -> No Travel
    - Wind 35-44 ([35, 45)) mph and load > 40,000 lb -> Severe
    - Load comparisons are strict (>).
    """
    base = classify_base_wind(wind_mph)
    if base == UNKNOWN:
        return UNKNOWN, None

    w = float(wind_mph)  # type: ignore[arg-type]
    load = float(load_lb)

    if w >= 55.0:
        return NO_TRAVEL, f"Wind {w:.1f} mph ≥ 55 mph (No Travel for any load)"
    if 45.0 <= w < 55.0 and load > 30000.0:
        return (
            NO_TRAVEL,
            f"Wind {w:.1f} mph (45–54 mph) + {load:,.0f} lb load (>30,000 lb) → No Travel",
        )
    if 35.0 <= w < 45.0 and load > 40000.0:
        return (
            SEVERE,
            f"Wind {w:.1f} mph (35–44 mph) + {load:,.0f} lb load (>40,000 lb) → Severe",
        )
    return base, None


def classify_rain(rain_in_hr: float | None) -> str:
    """Classify rainfall rate (in/hr) per AGENTS.md §2.1.

    Boundaries:
    [0, 0.10) -> Low
    [0.10, 0.25) -> Moderate
    [0.25, 0.50) -> High
    [0.50, 1.00] -> Severe
    > 1.00 -> No Travel
    """
    if not _is_valid_non_negative(rain_in_hr):
        return UNKNOWN
    r = float(rain_in_hr)  # type: ignore[arg-type]
    if r < 0.10:
        return LOW
    if r < 0.25:
        return MODERATE
    if r < 0.50:
        return HIGH
    if r <= 1.00:
        return SEVERE
    return NO_TRAVEL


def classify_snow(snow_in_hr: float | None) -> str:
    """Classify snowfall rate (in/hr) per AGENTS.md §2.1.

    Boundaries:
    [0, 0.5) -> Low
    [0.5, 1.0) -> Moderate
    [1.0, 2.0) -> High
    [2.0, 3.0] -> Severe
    > 3.0 -> No Travel
    """
    if not _is_valid_non_negative(snow_in_hr):
        return UNKNOWN
    s = float(snow_in_hr)  # type: ignore[arg-type]
    if s < 0.5:
        return LOW
    if s < 1.0:
        return MODERATE
    if s < 2.0:
        return HIGH
    if s <= 3.0:
        return SEVERE
    return NO_TRAVEL


@dataclass(frozen=True)
class CheckpointRiskResult:
    """Evaluated risk classification, numeric score, and factor explanations for one checkpoint."""

    wind_level: str
    rain_level: str
    snow_level: str
    level: str
    score: int | None
    load_rule_triggered: bool
    factors: list[str]


def evaluate_checkpoint_risk(
    wind_mph: float | None,
    rain_in_hr: float | None,
    snow_in_hr: float | None,
    load_lb: float,
) -> CheckpointRiskResult:
    """Evaluate overall checkpoint risk and contributing explanations.

    Never treats missing weather as Low: if any metric is Unknown, the overall
    checkpoint level is Unknown (score=None).
    """
    wind_level, load_reason = classify_wind(wind_mph, load_lb)
    base_wind_level = classify_base_wind(wind_mph)
    rain_level = classify_rain(rain_in_hr)
    snow_level = classify_snow(snow_in_hr)

    factors: list[str] = []
    missing: list[str] = []

    if wind_level == UNKNOWN:
        missing.append("wind")
    elif load_reason is not None:
        factors.append(load_reason)
    elif wind_level != LOW:
        factors.append(f"Wind {float(wind_mph):.1f} mph → {wind_level}")  # type: ignore[arg-type]

    if rain_level == UNKNOWN:
        missing.append("rain")
    elif rain_level != LOW:
        factors.append(f"Rain {float(rain_in_hr):.2f} in/hr → {rain_level}")  # type: ignore[arg-type]

    if snow_level == UNKNOWN:
        missing.append("snow")
    elif snow_level != LOW:
        factors.append(f"Snow {float(snow_in_hr):.2f} in/hr → {snow_level}")  # type: ignore[arg-type]

    load_rule_triggered = (
        wind_level != UNKNOWN
        and base_wind_level != UNKNOWN
        and wind_level != base_wind_level
    )

    if missing:
        factors.insert(0, f"Weather data unavailable ({', '.join(missing)})")
        return CheckpointRiskResult(
            wind_level=wind_level,
            rain_level=rain_level,
            snow_level=snow_level,
            level=UNKNOWN,
            score=None,
            load_rule_triggered=False,
            factors=factors,
        )

    max_score = max(
        RISK_SCORE[wind_level],
        RISK_SCORE[rain_level],
        RISK_SCORE[snow_level],
    )
    overall_level = SCORE_TO_LEVEL[max_score]

    if not factors:
        factors.append(
            f"Calm conditions (Wind {float(wind_mph):.1f} mph, Rain {float(rain_in_hr):.2f} in/hr, Snow {float(snow_in_hr):.2f} in/hr)"  # type: ignore[arg-type]
        )

    return CheckpointRiskResult(
        wind_level=wind_level,
        rain_level=rain_level,
        snow_level=snow_level,
        level=overall_level,
        score=max_score,
        load_rule_triggered=load_rule_triggered,
        factors=factors,
    )


def compute_segment_lengths(
    checkpoint_miles: list[float], total_distance_mi: float
) -> list[float]:
    """Compute the segment length (miles) represented by each checkpoint.

    Each checkpoint covers from the midpoint to the previous checkpoint up to
    the midpoint to the next checkpoint, clamped to [0, total_distance_mi].
    The sum of segment lengths always equals total_distance_mi.
    """
    total = max(0.0, float(total_distance_mi))
    n = len(checkpoint_miles)
    if n == 0:
        return []
    if n == 1:
        return [total]

    clamped = [min(max(0.0, float(m)), total) for m in checkpoint_miles]
    boundaries = [0.0]
    for i in range(n - 1):
        mid = 0.5 * (clamped[i] + clamped[i + 1])
        mid = min(max(boundaries[-1], mid), total)
        boundaries.append(mid)
    boundaries.append(total)

    return [boundaries[i + 1] - boundaries[i] for i in range(n)]


def _format_duration_hm(duration_s: float) -> str:
    total_mins = round(duration_s / 60.0)
    hours, mins = divmod(total_mins, 60)
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def summarize_route(
    route_id: str,
    route_name: str,
    interval_mi: int,
    total_distance_mi: float,
    duration_s: float,
    checkpoints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize segment miles by risk level, average risk score, and coverage for a route."""
    cp_miles = [float(cp["mile"]) for cp in checkpoints]
    seg_lengths = compute_segment_lengths(cp_miles, total_distance_mi)

    miles_by_level: dict[str, float] = {lvl: 0.0 for lvl in ALL_LEVELS}
    weighted_score_sum = 0.0
    known_miles = 0.0

    for cp, seg_len in zip(checkpoints, seg_lengths):
        lvl = cp.get("level", UNKNOWN)
        if lvl not in miles_by_level:
            lvl = UNKNOWN
        miles_by_level[lvl] += seg_len
        score = cp.get("score")
        if lvl != UNKNOWN and score is not None:
            known_miles += seg_len
            weighted_score_sum += float(score) * seg_len

    total = max(0.0, float(total_distance_mi))
    if total > 0.0:
        coverage_pct = round(100.0 * known_miles / total, 1)
    else:
        coverage_pct = 100.0 if checkpoints and known_miles >= 0 else 0.0

    avg_score: float | None
    if known_miles > 0.0:
        avg_score = round(weighted_score_sum / known_miles, 3)
    elif total == 0.0 and checkpoints and all(cp.get("score") is not None for cp in checkpoints):
        avg_score = round(
            sum(float(cp["score"]) for cp in checkpoints) / len(checkpoints), 3
        )
        coverage_pct = 100.0
    else:
        avg_score = None

    rounded_miles = {k: round(v, 2) for k, v in miles_by_level.items()}
    has_no_travel = rounded_miles[NO_TRAVEL] > 0.0

    warnings: list[str] = []
    if has_no_travel:
        warnings.append(
            f"NO TRAVEL HAZARD: Route crosses {rounded_miles[NO_TRAVEL]:.1f} mi of No Travel conditions."
        )
    if rounded_miles[SEVERE] > 0.0:
        warnings.append(
            f"Severe weather along {rounded_miles[SEVERE]:.1f} mi of route."
        )
    if coverage_pct < 90.0:
        warnings.append(
            f"Weather data incomplete ({coverage_pct:.1f}% route coverage < 90% threshold)."
        )

    return {
        "route_id": route_id,
        "route_name": route_name,
        "interval_mi": interval_mi,
        "distance_mi": round(total, 2),
        "duration_s": round(float(duration_s), 1),
        "miles_by_level": rounded_miles,
        "avg_score": avg_score,
        "coverage_pct": coverage_pct,
        "has_no_travel": has_no_travel,
        "warnings": warnings,
    }


def _explain_comparison(
    winner: dict[str, Any],
    other: dict[str, Any],
    coverage_threshold_pct: float,
    from_other_perspective: bool = False,
) -> tuple[str, str]:
    """Explain the deciding criterion that ranked winner ahead of other."""
    winner_name = winner.get("route_name") or winner["route_id"]
    other_name = other.get("route_name") or other["route_id"]
    w_cov = winner["coverage_pct"] >= coverage_threshold_pct
    o_cov = other["coverage_pct"] >= coverage_threshold_pct
    if w_cov and not o_cov:
        if from_other_perspective:
            return (
                "weather_coverage",
                f"Incomplete weather coverage ({other['coverage_pct']:.0f}% vs {winner['coverage_pct']:.0f}% on {winner_name})",
            )
        return (
            "weather_coverage",
            f"Complete weather coverage ({winner['coverage_pct']:.0f}% vs {other['coverage_pct']:.0f}% on {other_name})",
        )

    w_m = winner["miles_by_level"]
    o_m = other["miles_by_level"]

    if round(w_m[NO_TRAVEL], 2) != round(o_m[NO_TRAVEL], 2):
        if from_other_perspective:
            return (
                "no_travel_miles",
                f"More No Travel miles ({o_m[NO_TRAVEL]:.1f} mi vs {w_m[NO_TRAVEL]:.1f} mi on {winner_name})",
            )
        return (
            "no_travel_miles",
            f"Fewest No Travel miles ({w_m[NO_TRAVEL]:.1f} mi vs {o_m[NO_TRAVEL]:.1f} mi on {other_name})",
        )
    if round(w_m[SEVERE], 2) != round(o_m[SEVERE], 2):
        if from_other_perspective:
            return (
                "severe_miles",
                f"More Severe miles ({o_m[SEVERE]:.1f} mi vs {w_m[SEVERE]:.1f} mi on {winner_name})",
            )
        return (
            "severe_miles",
            f"Fewest Severe miles ({w_m[SEVERE]:.1f} mi vs {o_m[SEVERE]:.1f} mi on {other_name})",
        )
    if round(w_m[HIGH], 2) != round(o_m[HIGH], 2):
        if from_other_perspective:
            return (
                "high_miles",
                f"More High-risk miles ({o_m[HIGH]:.1f} mi vs {w_m[HIGH]:.1f} mi on {winner_name})",
            )
        return (
            "high_miles",
            f"Fewest High-risk miles ({w_m[HIGH]:.1f} mi vs {o_m[HIGH]:.1f} mi on {other_name})",
        )

    w_avg = winner["avg_score"] if winner["avg_score"] is not None else float("inf")
    o_avg = other["avg_score"] if other["avg_score"] is not None else float("inf")
    if round(w_avg, 3) != round(o_avg, 3):
        if from_other_perspective:
            return (
                "avg_score",
                f"Higher average risk score ({o_avg:.2f} vs {w_avg:.2f} on {winner_name})",
            )
        return (
            "avg_score",
            f"Lower average risk score ({w_avg:.2f} vs {o_avg:.2f} on {other_name})",
        )

    if from_other_perspective:
        return (
            "travel_time",
            f"Longer travel time ({_format_duration_hm(other['duration_s'])} vs {_format_duration_hm(winner['duration_s'])} on {winner_name})",
        )
    return (
        "travel_time",
        f"Shortest travel time ({_format_duration_hm(winner['duration_s'])} vs {_format_duration_hm(other['duration_s'])} on {other_name})",
    )


def rank_route_summaries(
    summaries: list[dict[str, Any]],
    coverage_threshold_pct: float = 90.0,
) -> list[dict[str, Any]]:
    """Rank route summaries according to AGENTS.md §2.5.

    Sorting order:
    0. Eligible weather coverage (>= coverage_threshold_pct) before incomplete coverage
    1. Fewest No Travel miles
    2. Fewest Severe miles
    3. Fewest High miles
    4. Lowest distance-weighted average risk score
    5. Shortest travel time (duration_s)
    """
    if not summaries:
        return []

    def _sort_key(s: dict[str, Any]) -> tuple[Any, ...]:
        eligible = s["coverage_pct"] >= coverage_threshold_pct
        m = s["miles_by_level"]
        avg = s["avg_score"] if s["avg_score"] is not None else float("inf")
        return (
            0 if eligible else 1,
            round(m[NO_TRAVEL], 2),
            round(m[SEVERE], 2),
            round(m[HIGH], 2),
            round(avg, 3),
            round(s["duration_s"], 1),
        )

    ordered = sorted([dict(s) for s in summaries], key=_sort_key)
    any_eligible = any(s["coverage_pct"] >= coverage_threshold_pct for s in ordered)

    for idx, summary in enumerate(ordered):
        rank = idx + 1
        summary["rank"] = rank
        is_recommended = rank == 1 and any_eligible
        summary["recommended"] = is_recommended
        reasons: list[str] = []
        deciding_criterion = "none"

        if is_recommended:
            if len(ordered) > 1:
                deciding_criterion, primary_reason = _explain_comparison(
                    summary, ordered[1], coverage_threshold_pct
                )
                reasons.append(primary_reason)
                for other in ordered[2:]:
                    _, extra_reason = _explain_comparison(
                        summary, other, coverage_threshold_pct
                    )
                    if extra_reason not in reasons:
                        reasons.append(extra_reason)
            else:
                deciding_criterion = "only_route"
                reasons.append("Only available route option")

            if summary["has_no_travel"]:
                reasons.append(
                    "Warning: All available routes contain No Travel weather segments; delay departure if possible."
                )
        else:
            if not any_eligible:
                deciding_criterion = "insufficient_weather_coverage"
                reasons.append(
                    "No route recommended because weather forecast coverage is below 90% on all routes."
                )
            else:
                deciding_criterion, reason_vs_winner = _explain_comparison(
                    ordered[0],
                    summary,
                    coverage_threshold_pct,
                    from_other_perspective=True,
                )
                reasons.append(f"Ranked #{rank}: {reason_vs_winner}")

        summary["deciding_criterion"] = deciding_criterion
        summary["reasons"] = reasons

    return ordered
