import math

import pytest

from routing_app.risk import (
    HIGH,
    LOW,
    MODERATE,
    NO_TRAVEL,
    SEVERE,
    UNKNOWN,
    classify_base_wind,
    classify_rain,
    classify_snow,
    classify_wind,
    compute_segment_lengths,
    evaluate_checkpoint_risk,
    rank_route_summaries,
    summarize_route,
)


class TestWindBoundaries:
    @pytest.mark.parametrize(
        "wind_mph,expected",
        [
            (0.0, LOW),
            (12.5, LOW),
            (24.99, LOW),
            (25.0, MODERATE),
            (34.0, MODERATE),
            (34.99, MODERATE),
            (35.0, HIGH),
            (44.0, HIGH),
            (44.99, HIGH),
            (45.0, SEVERE),
            (54.0, SEVERE),
            (54.99, SEVERE),
            (55.0, NO_TRAVEL),
            (75.0, NO_TRAVEL),
            (None, UNKNOWN),
            (float("nan"), UNKNOWN),
            (-1.0, UNKNOWN),
        ],
    )
    def test_base_wind_thresholds(self, wind_mph, expected):
        assert classify_base_wind(wind_mph) == expected

    @pytest.mark.parametrize(
        "wind_mph,load_lb,expected_level,expects_reason",
        [
            # >= 55 mph is No Travel for any load
            (55.0, 0.0, NO_TRAVEL, True),
            (55.0, 10000.0, NO_TRAVEL, True),
            (60.0, 45000.0, NO_TRAVEL, True),
            # 45-54 mph ([45, 55)) and load > 30,000 lb -> No Travel (strict >)
            (45.0, 29999.0, SEVERE, False),
            (45.0, 30000.0, SEVERE, False),  # Strict > 30,000 lb
            (45.0, 30000.1, NO_TRAVEL, True),
            (54.9, 30001.0, NO_TRAVEL, True),
            # 35-44 mph ([35, 45)) and load > 40,000 lb -> Severe (strict >)
            (35.0, 35000.0, HIGH, False),
            (35.0, 40000.0, HIGH, False),  # Strict > 40,000 lb
            (35.0, 40000.1, SEVERE, True),
            (44.9, 45000.0, SEVERE, True),
            # Below 35 mph unaffected by heavy load
            (34.9, 50000.0, MODERATE, False),
            (24.9, 80000.0, LOW, False),
            # Missing wind
            (None, 45000.0, UNKNOWN, False),
        ],
    )
    def test_wind_load_rules(self, wind_mph, load_lb, expected_level, expects_reason):
        level, reason = classify_wind(wind_mph, load_lb)
        assert level == expected_level
        if expects_reason:
            assert reason is not None and len(reason) > 0
        else:
            assert reason is None


class TestRainBoundaries:
    @pytest.mark.parametrize(
        "rain_in_hr,expected",
        [
            (0.0, LOW),
            (0.099, LOW),
            (0.10, MODERATE),
            (0.249, MODERATE),
            (0.25, HIGH),
            (0.499, HIGH),
            (0.50, SEVERE),
            (0.75, SEVERE),
            (1.00, SEVERE),  # [0.50, 1.00] is Severe; > 1.00 is No Travel
            (1.001, NO_TRAVEL),
            (2.50, NO_TRAVEL),
            (None, UNKNOWN),
            (float("nan"), UNKNOWN),
            (-0.01, UNKNOWN),
        ],
    )
    def test_rain_thresholds(self, rain_in_hr, expected):
        assert classify_rain(rain_in_hr) == expected


class TestSnowBoundaries:
    @pytest.mark.parametrize(
        "snow_in_hr,expected",
        [
            (0.0, LOW),
            (0.499, LOW),
            (0.5, MODERATE),
            (0.999, MODERATE),
            (1.0, HIGH),
            (1.999, HIGH),
            (2.0, SEVERE),
            (2.5, SEVERE),
            (3.0, SEVERE),  # [2.0, 3.0] is Severe; > 3.0 is No Travel
            (3.001, NO_TRAVEL),
            (5.0, NO_TRAVEL),
            (None, UNKNOWN),
            (float("nan"), UNKNOWN),
            (-0.1, UNKNOWN),
        ],
    )
    def test_snow_thresholds(self, snow_in_hr, expected):
        assert classify_snow(snow_in_hr) == expected


class TestCheckpointRiskEvaluation:
    def test_takes_highest_severity_across_conditions(self):
        res = evaluate_checkpoint_risk(
            wind_mph=20.0,  # Low
            rain_in_hr=0.30,  # High
            snow_in_hr=0.60,  # Moderate
            load_lb=25000.0,
        )
        assert res.wind_level == LOW
        assert res.rain_level == HIGH
        assert res.snow_level == MODERATE
        assert res.level == HIGH
        assert res.score == 3
        assert not res.load_rule_triggered
        assert any("Rain 0.30 in/hr → High" in f for f in res.factors)

    def test_load_rule_escalates_overall_checkpoint_risk(self):
        res = evaluate_checkpoint_risk(
            wind_mph=47.0,  # Base Severe, + >30,000 lb -> No Travel
            rain_in_hr=0.0,
            snow_in_hr=0.0,
            load_lb=42000.0,
        )
        assert res.wind_level == NO_TRAVEL
        assert res.level == NO_TRAVEL
        assert res.score == 5
        assert res.load_rule_triggered
        assert any("42,000 lb" in f for f in res.factors)

    def test_missing_weather_never_treated_as_low(self):
        res = evaluate_checkpoint_risk(
            wind_mph=None,
            rain_in_hr=0.0,
            snow_in_hr=0.0,
            load_lb=35000.0,
        )
        assert res.level == UNKNOWN
        assert res.score is None
        assert any("unavailable" in f.lower() for f in res.factors)


class TestSegmentLengthsAndRanking:
    @pytest.mark.parametrize(
        "miles,total_dist",
        [
            ([0.0, 25.0, 50.0, 75.0, 100.0], 100.0),
            ([0.0, 25.0, 50.0, 62.3], 62.3),
            ([0.0], 18.4),
            ([0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 53.7], 53.7),
        ],
    )
    def test_segment_lengths_sum_to_total_distance(self, miles, total_dist):
        lengths = compute_segment_lengths(miles, total_dist)
        assert len(lengths) == len(miles)
        assert all(l >= 0.0 for l in lengths)
        assert math.isclose(sum(lengths), total_dist, rel_tol=1e-9, abs_tol=1e-9)

    def test_ranking_tie_breakers_follow_Hierarchy(self):
        # 1. No Travel miles -> 2. Severe miles -> 3. High miles -> 4. Avg risk -> 5. Travel time
        r_no_travel = summarize_route(
            route_id="r_no_travel",
            route_name="Route With No Travel",
            interval_mi=25,
            total_distance_mi=100.0,
            duration_s=5000.0,
            checkpoints=[
                {"mile": 0.0, "level": NO_TRAVEL, "score": 5},
                {"mile": 50.0, "level": LOW, "score": 1},
                {"mile": 100.0, "level": LOW, "score": 1},
            ],
        )
        r_severe = summarize_route(
            route_id="r_severe",
            route_name="Route With Severe",
            interval_mi=25,
            total_distance_mi=100.0,
            duration_s=5500.0,
            checkpoints=[
                {"mile": 0.0, "level": SEVERE, "score": 4},
                {"mile": 50.0, "level": LOW, "score": 1},
                {"mile": 100.0, "level": LOW, "score": 1},
            ],
        )
        r_high = summarize_route(
            route_id="r_high",
            route_name="Route With High",
            interval_mi=25,
            total_distance_mi=100.0,
            duration_s=6000.0,
            checkpoints=[
                {"mile": 0.0, "level": HIGH, "score": 3},
                {"mile": 50.0, "level": LOW, "score": 1},
                {"mile": 100.0, "level": LOW, "score": 1},
            ],
        )
        r_mod_slow = summarize_route(
            route_id="r_mod_slow",
            route_name="Route Moderate Slow",
            interval_mi=25,
            total_distance_mi=100.0,
            duration_s=7200.0,
            checkpoints=[
                {"mile": 0.0, "level": MODERATE, "score": 2},
                {"mile": 50.0, "level": LOW, "score": 1},
                {"mile": 100.0, "level": LOW, "score": 1},
            ],
        )
        r_low_slow = summarize_route(
            route_id="r_low_slow",
            route_name="Route Low Slow",
            interval_mi=25,
            total_distance_mi=100.0,
            duration_s=7000.0,
            checkpoints=[
                {"mile": 0.0, "level": LOW, "score": 1},
                {"mile": 50.0, "level": LOW, "score": 1},
                {"mile": 100.0, "level": LOW, "score": 1},
            ],
        )
        r_low_fast = summarize_route(
            route_id="r_low_fast",
            route_name="Route Low Fast",
            interval_mi=25,
            total_distance_mi=100.0,
            duration_s=6200.0,
            checkpoints=[
                {"mile": 0.0, "level": LOW, "score": 1},
                {"mile": 50.0, "level": LOW, "score": 1},
                {"mile": 100.0, "level": LOW, "score": 1},
            ],
        )

        ranked = rank_route_summaries(
            [r_no_travel, r_severe, r_high, r_mod_slow, r_low_slow, r_low_fast]
        )
        assert [r["route_id"] for r in ranked] == [
            "r_low_fast",
            "r_low_slow",
            "r_mod_slow",
            "r_high",
            "r_severe",
            "r_no_travel",
        ]
        assert ranked[0]["recommended"] is True
        assert all(not r["recommended"] for r in ranked[1:])

    def test_incomplete_weather_coverage_cannot_be_recommended(self):
        # Route A has 50% coverage (1 of 2 segments Unknown), Route B has 100% coverage with Moderate
        r_incomplete = summarize_route(
            route_id="r_incomplete",
            route_name="Route Incomplete",
            interval_mi=50,
            total_distance_mi=100.0,
            duration_s=5000.0,
            checkpoints=[
                {"mile": 0.0, "level": LOW, "score": 1},
                {"mile": 100.0, "level": UNKNOWN, "score": None},
            ],
        )
        r_complete = summarize_route(
            route_id="r_complete",
            route_name="Route Complete",
            interval_mi=50,
            total_distance_mi=100.0,
            duration_s=6000.0,
            checkpoints=[
                {"mile": 0.0, "level": MODERATE, "score": 2},
                {"mile": 100.0, "level": MODERATE, "score": 2},
            ],
        )

        ranked = rank_route_summaries([r_incomplete, r_complete], coverage_threshold_pct=90.0)
        assert ranked[0]["route_id"] == "r_complete"
        assert ranked[0]["recommended"] is True
        assert ranked[1]["route_id"] == "r_incomplete"
        assert ranked[1]["recommended"] is False

    def test_no_route_recommended_when_all_below_90_percent_coverage(self):
        r1 = summarize_route(
            route_id="r1",
            route_name="Route 1",
            interval_mi=50,
            total_distance_mi=100.0,
            duration_s=5000.0,
            checkpoints=[
                {"mile": 0.0, "level": UNKNOWN, "score": None},
                {"mile": 100.0, "level": LOW, "score": 1},
            ],
        )
        ranked = rank_route_summaries([r1], coverage_threshold_pct=90.0)
        assert ranked[0]["recommended"] is False
        assert ranked[0]["deciding_criterion"] == "insufficient_weather_coverage"

    def test_non_recommended_reasons_read_from_losing_route_perspective(self):
        r_fast = summarize_route(
            route_id="r_fast",
            route_name="Route A (Primary Direct)",
            interval_mi=25,
            total_distance_mi=521.0,
            duration_s=32340.0,  # 8h 59m
            checkpoints=[{"mile": 0.0, "level": LOW, "score": 1}],
        )
        r_slow = summarize_route(
            route_id="r_slow",
            route_name="Route C (Southern Corridor II)",
            interval_mi=25,
            total_distance_mi=527.0,
            duration_s=44700.0,  # 12h 25m
            checkpoints=[{"mile": 0.0, "level": LOW, "score": 1}],
        )
        ranked = rank_route_summaries([r_slow, r_fast])
        assert ranked[0]["reasons"] == [
            "Shortest travel time (8h 59m vs 12h 25m on Route C (Southern Corridor II))"
        ]
        assert ranked[1]["reasons"] == [
            "Ranked #2: Longer travel time (12h 25m vs 8h 59m on Route A (Primary Direct))"
        ]
