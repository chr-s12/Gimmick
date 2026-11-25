import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta
from unittest.mock import call, patch

from progress import analytics
from progress.analytics import (
    ExerciseDailyProgress,
    ExercisePersonalRecords,
    ExerciseProgression,
    PersonalBest,
    RepetitionRecord,
    StudentProgressAnalytics,
    WeeklyConsistency,
    calculate_exercise_progression,
    calculate_personal_records,
    calculate_student_analytics,
    calculate_weekly_consistency,
)
from progress.models import LoggedExercise, WorkoutLog


class WeeklyConsistencyTests(unittest.TestCase):
    as_of = datetime.fromisoformat("2026-11-25T12:00:00-05:00")

    def workout(self, timestamp, *, workout_id="W001", weight=42.5):
        return WorkoutLog(
            workout_id, "ST001", "RT001", "Upper Body", datetime.fromisoformat(timestamp),
            [LoggedExercise("EX001", "Bench Press", 3, 8, weight)],
        )

    def calculate(self, *workouts):
        return calculate_weekly_consistency(workouts, self.as_of)

    def test_empty_history_returns_no_weeks(self):
        self.assertEqual(self.calculate(), [])

    def test_one_workout_reports_local_date_and_current_week_boundaries(self):
        history = self.calculate(self.workout("2026-11-25T08:00:00-05:00"))
        self.assertEqual(history, [
            WeeklyConsistency(date(2026, 11, 23), date(2026, 11, 29), (date(2026, 11, 25),), True)
        ])
        self.assertEqual(history[0].active_days, 1)

    def test_multiple_sessions_on_one_day_count_once(self):
        week, = self.calculate(
            self.workout("2026-11-24T07:00:00-05:00"),
            self.workout("2026-11-24T18:00:00-05:00", workout_id="W002"),
        )
        self.assertEqual(week.active_days, 1)
        self.assertEqual(week.active_dates, (date(2026, 11, 24),))

    def test_different_training_days_increase_count(self):
        week, = self.calculate(
            self.workout("2026-11-25T08:00:00-05:00"),
            self.workout("2026-11-23T18:00:00-05:00", workout_id="W002"),
        )
        self.assertEqual(week.active_days, 2)
        self.assertEqual(week.active_dates, (date(2026, 11, 23), date(2026, 11, 25)))

    def test_seven_distinct_dates_count_as_seven(self):
        workouts = [
            self.workout(f"2026-11-{day}T08:00:00-05:00", workout_id=f"W{day}")
            for day in range(16, 23)
        ]
        full_week, current_week = self.calculate(*workouts)
        self.assertEqual(full_week.active_days, 7)
        self.assertFalse(full_week.is_current_week)
        self.assertTrue(current_week.is_current_week)

    def test_unsorted_workouts_include_zero_day_gap_and_current_week(self):
        history = self.calculate(
            self.workout("2026-11-16T09:00:00-05:00"),
            self.workout("2026-11-02T09:00:00-05:00", workout_id="W002"),
        )
        self.assertEqual([week.week_start.day for week in history], [2, 9, 16, 23])
        self.assertEqual([week.active_days for week in history], [1, 0, 1, 0])
        self.assertEqual([week.is_current_week for week in history], [False, False, False, True])
        for week in history:
            self.assertEqual(week.week_start.weekday(), 0)
            self.assertEqual(week.week_end, week.week_start + timedelta(days=6))

    def test_utc_midnight_and_different_offsets_use_jamaica_dates(self):
        past, current = self.calculate(
            self.workout("2026-11-23T00:15:00+00:00"),
            self.workout("2026-11-23T05:00:00+00:00", workout_id="W002"),
            self.workout("2026-11-23T06:30:00+02:00", workout_id="W003"),
        )
        self.assertEqual(past.active_dates, (date(2026, 11, 22),))
        self.assertEqual(current.active_dates, (date(2026, 11, 23),))

    def test_week_can_span_calendar_month_and_year(self):
        history = calculate_weekly_consistency(
            [
                self.workout("2026-12-31T20:00:00-05:00"),
                self.workout("2027-01-01T08:00:00-05:00", workout_id="W002"),
            ],
            datetime.fromisoformat("2027-01-04T04:59:00+00:00"),
        )
        self.assertEqual(history, [
            WeeklyConsistency(
                date(2026, 12, 28), date(2027, 1, 3),
                (date(2026, 12, 31), date(2027, 1, 1)), True,
            )
        ])

    def test_reference_instant_is_inclusive_and_future_sessions_are_excluded(self):
        current, = self.calculate(
            self.workout("2026-11-23T08:00:00-05:00"),
            self.workout("2026-11-25T17:00:00+00:00", workout_id="W002"),
            self.workout("2026-11-25T12:00:00.000001-05:00", workout_id="W003"),
            self.workout("2026-11-26T00:00:00-05:00", workout_id="W004"),
        )
        self.assertEqual(current.active_dates, (date(2026, 11, 23), date(2026, 11, 25)))
        later_today = self.workout("2026-11-25T12:01:00-05:00")
        self.assertEqual(self.calculate(later_today), [])

    def test_unweighted_workouts_count_without_mutating_records(self):
        workouts = [self.workout("2026-11-24T08:00:00-05:00", weight=0.0)]
        original = workouts[0].to_dict()
        week, = calculate_weekly_consistency(workouts, self.as_of)
        self.assertEqual(week.active_days, 1)
        self.assertEqual([workout.to_dict() for workout in workouts], [original])

    def test_invalid_reference_and_naive_workout_raise_clear_errors(self):
        for reference in (date(2026, 11, 25), datetime(2026, 11, 25), "2026-11-25"):
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(ValueError, "as_of.*timezone-aware"):
                    calculate_weekly_consistency([], reference)
        with self.assertRaisesRegex(ValueError, "W001 completed_at.*timezone-aware"):
            self.calculate(self.workout("2026-11-24T08:00:00"))

    def test_unsupported_jamaica_conversion_reports_the_record(self):
        workout = self.workout("0001-01-01T00:00:00+01:00")
        with self.assertRaisesRegex(ValueError, "W001 completed_at.*supported datetime range"):
            self.calculate(workout)

    def test_unsupported_reference_conversion_reports_as_of(self):
        reference = datetime.fromisoformat("0001-01-01T00:00:00+01:00")
        with self.assertRaisesRegex(ValueError, "as_of.*supported datetime range"):
            calculate_weekly_consistency([], reference)

    def test_current_week_with_unrepresentable_sunday_is_rejected(self):
        workout = self.workout("9999-12-30T10:00:00+00:00")
        reference = datetime.fromisoformat("9999-12-31T12:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "Sunday.*supported date range"):
            calculate_weekly_consistency([workout], reference)

    def test_unsupported_local_timestamp_is_ignored_when_it_is_future(self):
        workout = self.workout("9999-12-31T23:59:59-12:00")
        self.assertEqual(self.calculate(workout), [])


class ExerciseProgressionTests(unittest.TestCase):
    as_of = datetime.fromisoformat("2026-11-25T12:00:00-05:00")

    def workout(self, workout_id, timestamp, *entries, routine_id="RT001"):
        return WorkoutLog(
            workout_id, "ST001", routine_id, "Saved routine",
            datetime.fromisoformat(timestamp), list(entries),
        )

    def calculate(self, *workouts, **dates):
        return calculate_exercise_progression(workouts, as_of=self.as_of, **dates)

    def test_no_workouts_or_eligible_exercises_returns_empty(self):
        self.assertEqual(self.calculate(), [])
        self.assertEqual(self.calculate(self.workout("W1", "2026-11-24T09:00:00-05:00")), [])

    def test_single_decimal_performance_returns_expected_totals(self):
        workout = self.workout(
            "W1", "2026-11-24T09:00:00-05:00",
            LoggedExercise("E1", "Press", 3, 7, 12.35),
        )
        series, = self.calculate(workout)
        self.assertEqual((series.exercise_id, series.exercise_name), ("E1", "Press"))
        point, = series.daily_history
        self.assertEqual((point.date, point.max_weight_kg, point.max_reps),
                         (date(2026, 11, 24), 12.35, 7))
        self.assertAlmostEqual(point.total_volume_kg, 259.35)

    def test_grouping_uses_ids_across_routines_and_keeps_matching_names_separate(self):
        early = self.workout(
            "W1", "2026-11-20T10:00:00-05:00",
            LoggedExercise("E1", "Old Press", 2, 8, 10.0),
            LoggedExercise("E2", "Press", 1, 4, 30.0),
        )
        later = self.workout(
            "W2", "2026-11-24T10:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 6, 20.0), routine_id="RT002",
        )
        expected = [
            ExerciseProgression("E1", "Press", (
                ExerciseDailyProgress(date(2026, 11, 20), 10.0, 8, 160.0),
                ExerciseDailyProgress(date(2026, 11, 24), 20.0, 6, 120.0),
            )),
            ExerciseProgression("E2", "Press", (
                ExerciseDailyProgress(date(2026, 11, 20), 30.0, 4, 120.0),
            )),
        ]
        self.assertEqual(self.calculate(later, early), expected)
        self.assertEqual(self.calculate(early, later), expected)
        series, _ = self.calculate(early, later, end_date=date(2026, 11, 20))
        self.assertEqual(series.exercise_name, "Old Press")

    def test_day_merges_sessions_and_repeated_entries_with_independent_maxima(self):
        first = self.workout(
            "W1", "2026-11-24T07:00:00-05:00",
            LoggedExercise("E1", "Press", 3, 5, 42.5),
            LoggedExercise("E1", "Press", 2, 12, 30.0),
        )
        second = self.workout(
            "W2", "2026-11-24T17:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 8, 40.0),
        )
        series, = self.calculate(second, first)
        self.assertEqual(series.daily_history, (
            ExerciseDailyProgress(date(2026, 11, 24), 42.5, 12, 1677.5),
        ))

    def test_equal_instants_choose_name_by_workout_id_then_entry_position(self):
        first = self.workout(
            "W1", "2026-11-24T10:00:00-05:00",
            LoggedExercise("E1", "Z variation", 1, 5, 10.0),
        )
        second = self.workout(
            "W2", "2026-11-24T15:00:00+00:00",
            LoggedExercise("E1", "B variation", 1, 5, 10.0),
            LoggedExercise("E1", "A variation", 1, 5, 10.0),
        )
        self.assertEqual(self.calculate(first, second), self.calculate(second, first))
        self.assertEqual(self.calculate(second, first)[0].exercise_name, "A variation")

    def test_zero_weight_keeps_reps_and_conversion_leaves_input_untouched(self):
        workout = self.workout(
            "W1", "2026-11-24T10:00:00-05:00",
            LoggedExercise("E1", "Push-ups", 3, 12, 0.0),
        )
        original = workout.to_dict()
        series, = self.calculate(workout)
        self.assertEqual(series.daily_history, (
            ExerciseDailyProgress(date(2026, 11, 24), 0.0, 12, 0.0),
        ))
        self.assertEqual(workout.to_dict(), original)

    def test_local_midnight_and_inclusive_or_open_ended_date_filters(self):
        exercise = LoggedExercise("E1", "Press", 2, 6, 15.0)
        workouts = (
            self.workout("W1", "2026-11-24T04:59:00+00:00", exercise),
            self.workout("W2", "2026-11-24T05:00:00+00:00", exercise),
            self.workout("W3", "2026-11-25T06:00:00+00:00", exercise),
        )
        for bounds, days in (
            ({"start_date": date(2026, 11, 24)}, [24, 25]),
            ({"end_date": date(2026, 11, 24)}, [23, 24]),
            ({"start_date": date(2026, 11, 24), "end_date": date(2026, 11, 24)}, [24]),
        ):
            with self.subTest(bounds=bounds):
                series, = self.calculate(*workouts, **bounds)
                self.assertEqual([point.date.day for point in series.daily_history], days)
        self.assertEqual(self.calculate(*workouts, end_date=date(2026, 11, 22)), [])

    def test_reversed_or_non_calendar_date_ranges_raise_clear_errors(self):
        with self.assertRaisesRegex(ValueError, "start_date.*on or before"):
            self.calculate(start_date=date(2026, 11, 25), end_date=date(2026, 11, 24))
        for field, value in (
            ("start_date", "2026-11-24"),
            ("end_date", datetime(2026, 11, 25, 0, 0)),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, f"{field}.*calendar date"):
                    self.calculate(**{field: value})

    def test_future_workouts_do_not_change_points_or_display_name(self):
        cutoff = self.workout(
            "W1", "2026-11-25T17:00:00+00:00",
            LoggedExercise("E1", "Current Press", 1, 5, 10.0),
        )
        future = self.workout(
            "W2", "2026-11-25T12:00:00.000001-05:00",
            LoggedExercise("E1", "Future Press", 2, 10, 20.0),
        )
        self.assertEqual(self.calculate(future), [])
        self.assertEqual(self.calculate(future, cutoff), self.calculate(cutoff))

    def test_naive_and_unsupported_timestamps_raise_shared_errors(self):
        exercise = LoggedExercise("E1", "Press", 1, 5, 10.0)
        for timestamp, message in (
            ("2026-11-24T08:00:00", "timezone-aware"),
            ("0001-01-01T00:00:00+01:00", "supported datetime range"),
        ):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(ValueError, f"W1 completed_at.*{message}"):
                    self.calculate(self.workout("W1", timestamp, exercise))
        with self.assertRaisesRegex(ValueError, "as_of.*timezone-aware"):
            calculate_exercise_progression([], as_of=datetime(2026, 11, 25))

    def test_per_entry_and_aggregate_volume_overflow_raise_clear_errors(self):
        huge = LoggedExercise("E1", "Press", 1, 1, 1e308)
        for entries in ((LoggedExercise("E1", "Press", 1, 2, 1e308),), (huge, huge)):
            with self.subTest(entries=entries):
                workout = self.workout("W1", "2026-11-24T08:00:00-05:00", *entries)
                with self.assertRaisesRegex(ValueError, "E1 volume on 2026-11-24.*finite"):
                    self.calculate(workout)


class PersonalRecordsTests(unittest.TestCase):
    as_of = datetime.fromisoformat("2026-11-25T12:00:00-05:00")

    def workout(self, workout_id, timestamp, *entries, routine_id="RT001"):
        return WorkoutLog(
            workout_id, "ST001", routine_id, "Saved routine",
            datetime.fromisoformat(timestamp), list(entries),
        )

    def calculate(self, *workouts):
        return calculate_personal_records(workouts, as_of=self.as_of)

    def test_empty_and_future_only_history_produce_no_records(self):
        future = self.workout(
            "W1", "2026-11-25T17:00:00.000001+00:00",
            LoggedExercise("E1", "Press", 1, 50, 100.0),
        )
        self.assertEqual(self.calculate(), [])
        self.assertEqual(self.calculate(future), [])

    def test_first_performances_establish_independent_records_and_keep_input(self):
        workout = self.workout(
            "W1", "2026-11-24T04:59:00+00:00",
            LoggedExercise("E1", "Press", 2, 7, 42.5),
            LoggedExercise("E2", "Press", 1, 3, 10.0),
        )
        before = workout.to_dict()
        day = date(2026, 11, 23)
        achieved = (workout.completed_at, day, "W1")
        self.assertEqual(self.calculate(workout), [
            ExercisePersonalRecords(
                "E1", "Press", PersonalBest(42.5, *achieved),
                (RepetitionRecord(42.5, 7, *achieved),), PersonalBest(595.0, *achieved),
            ),
            ExercisePersonalRecords(
                "E2", "Press", PersonalBest(10.0, *achieved),
                (RepetitionRecord(10.0, 3, *achieved),), PersonalBest(30.0, *achieved),
            ),
        ])
        self.assertEqual(workout.to_dict(), before)

    def test_renamed_exercise_keeps_earliest_heaviest_weight_across_routines(self):
        initial = self.workout(
            "W1", "2026-11-21T08:00:00-05:00",
            LoggedExercise("E1", "Old Name", 1, 3, 20.5),
        )
        heaviest = self.workout(
            "W2", "2026-11-22T08:00:00-05:00",
            LoggedExercise("E1", "Old Name", 1, 2, 42.75), routine_id="RT002",
        )
        tied = self.workout(
            "W3", "2026-11-23T08:00:00-05:00",
            LoggedExercise("E1", "New Name", 1, 2, 42.75),
        )
        lower = self.workout(
            "W4", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E1", "New Name", 1, 3, 40.0),
        )
        records, = self.calculate(lower, initial, tied, heaviest)
        self.assertEqual(records.exercise_name, "New Name")
        self.assertEqual(records.heaviest_weight, PersonalBest(
            42.75, heaviest.completed_at, date(2026, 11, 22), "W2",
        ))

    def test_repetition_records_use_exact_weight_and_reps_per_set(self):
        early = self.workout(
            "W1", "2026-11-23T08:00:00-05:00",
            LoggedExercise("E1", "Press", 10, 6, 40),
            LoggedExercise("E1", "Press", 1, 5, 40.0001),
        )
        improved = self.workout(
            "W2", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 7, 40.0),
        )
        tied = self.workout(
            "W3", "2026-11-25T08:00:00-05:00",
            LoggedExercise("E1", "Press", 2, 7, 40.0),
        )
        records, = self.calculate(tied, early, improved)
        self.assertEqual(
            [(record.weight_kg, record.reps, record.workout_id)
             for record in records.repetition_records],
            [(40.0, 7, "W2"), (40.0001, 5, "W1")],
        )

    def test_session_volume_combines_repeated_entries_and_separates_same_day_workouts(self):
        earlier = self.workout(
            "W9", "2026-11-24T15:00:00+02:00",
            LoggedExercise("E1", "Press", 2, 5, 12.35),
            LoggedExercise("E1", "Press", 1, 4, 12.35),
            LoggedExercise("E2", "Curls", 4, 10, 99.0),
        )
        tied = self.workout(
            "W1", "2026-11-24T09:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 14, 12.35),
        )
        lower = self.workout(
            "W2", "2026-11-24T12:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 8, 12.35),
        )
        records, _ = self.calculate(tied, lower, earlier)
        self.assertAlmostEqual(records.highest_session_volume.value, 172.9)
        self.assertEqual(records.highest_session_volume.workout_id, "W9")
        self.assertEqual(records.highest_session_volume.achieved_at.isoformat(),
                         earlier.completed_at.isoformat())

    def test_equal_decimal_session_totals_keep_first_achievement(self):
        first = self.workout(
            "W1", "2026-11-23T08:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 1, 0.3),
        )
        later = self.workout(
            "W2", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E1", "Press", 1, 3, 0.1),
        )
        records, = self.calculate(later, first)
        self.assertEqual(records.highest_session_volume, PersonalBest(
            0.3, first.completed_at, date(2026, 11, 23), "W1",
        ))
        series, = calculate_exercise_progression([later, first], as_of=self.as_of)
        self.assertEqual([point.total_volume_kg for point in series.daily_history], [0.3, 0.3])

    def test_strictly_higher_exact_volume_wins_even_if_float_totals_match(self):
        large = LoggedExercise("E1", "Press", 1, 1, 1e16)
        first = self.workout("W1", "2026-11-23T08:00:00-05:00", large)
        later = self.workout(
            "W2", "2026-11-24T08:00:00-05:00",
            large, LoggedExercise("E1", "Press", 1, 1, 1.0),
        )
        records, = self.calculate(first, later)
        self.assertEqual(records.highest_session_volume.value, 1e16)
        self.assertEqual(records.highest_session_volume.workout_id, "W2")

    def test_zero_weight_records_remain_available_in_unweighted_and_mixed_history(self):
        workout = self.workout(
            "W1", "2026-11-24T08:00:00-05:00",
            LoggedExercise("E1", "Push-up", 3, 12, 0.0),
            LoggedExercise("E1", "Push-up", 1, 8, 5.0),
            LoggedExercise("E2", "Squat", 2, 15, 0.0),
        )
        mixed, unweighted = self.calculate(workout)
        self.assertEqual(
            [(record.weight_kg, record.reps) for record in mixed.repetition_records],
            [(0.0, 12), (5.0, 8)],
        )
        self.assertEqual(mixed.highest_session_volume.value, 40.0)
        self.assertIsNone(unweighted.heaviest_weight)
        self.assertIsNone(unweighted.highest_session_volume)
        self.assertEqual(unweighted.repetition_records[0].reps, 15)

    def test_identical_instants_use_deterministic_achievement_and_name_ties(self):
        earlier_id = self.workout(
            "W1", "2026-11-25T12:00:00-05:00",
            LoggedExercise("E1", "Z Name", 1, 6, 40.0),
        )
        later_id = self.workout(
            "W2", "2026-11-25T17:00:00+00:00",
            LoggedExercise("E1", "B Name", 1, 3, 40.0),
            LoggedExercise("E1", "A Name", 1, 3, 40.0),
        )
        future = self.workout(
            "W3", "2026-11-25T12:01:00-05:00",
            LoggedExercise("E1", "Future Name", 2, 15, 50.0),
        )
        expected = self.calculate(earlier_id, later_id)
        self.assertEqual(self.calculate(future, later_id, earlier_id), expected)
        records, = expected
        self.assertEqual(records.exercise_name, "A Name")
        self.assertEqual(records.heaviest_weight.workout_id, "W1")
        self.assertEqual(records.repetition_records[0].workout_id, "W1")
        self.assertEqual(records.highest_session_volume.workout_id, "W1")

    def test_naive_and_unsupported_timestamps_raise_clear_errors(self):
        exercise = LoggedExercise("E1", "Press", 1, 1, 10.0)
        for timestamp, message in (
            ("2026-11-24T08:00:00", "timezone-aware"),
            ("0001-01-01T00:00:00+01:00", "supported datetime range"),
        ):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(ValueError, f"W1 completed_at.*{message}"):
                    self.calculate(self.workout("W1", timestamp, exercise))
        with self.assertRaisesRegex(ValueError, "as_of.*timezone-aware"):
            calculate_personal_records([], as_of=datetime(2026, 11, 25))

    def test_session_volume_rejects_individual_and_total_overflow(self):
        huge = LoggedExercise("E1", "Press", 1, 1, 1e308)
        for entries in ((LoggedExercise("E1", "Press", 1, 2, 1e308),), (huge, huge)):
            with self.subTest(entries=entries):
                workout = self.workout("W1", "2026-11-24T08:00:00-05:00", *entries)
                with self.assertRaisesRegex(ValueError, "E1 session volume in workout W1.*finite"):
                    self.calculate(workout)


class StudentProgressAnalyticsTests(unittest.TestCase):
    as_of = datetime.fromisoformat("2026-11-25T12:00:00-05:00")

    def workout(self, workout_id, timestamp, weight=42.5):
        return WorkoutLog(
            workout_id, "ST001", "RT001", "Saved routine",
            datetime.fromisoformat(timestamp),
            [LoggedExercise("EX001", "Press", 2, 7, weight)],
        )

    def calculate(self, *workouts, **dates):
        return calculate_student_analytics("ST001", workouts, as_of=self.as_of, **dates)

    def test_no_eligible_history_has_empty_metrics_and_both_flags_false(self):
        future = self.workout("W1", "2026-11-25T12:01:00-05:00")
        expected = StudentProgressAnalytics(
            "ST001", (), (), (), None, None, self.as_of, False, False,
        )
        self.assertEqual(self.calculate(), expected)
        self.assertEqual(self.calculate(future), expected)

    def test_one_workout_populates_each_metric(self):
        workout = self.workout("W1", "2026-11-25T08:00:00-05:00")
        result = self.calculate(workout)
        self.assertTrue(result.has_workouts)
        self.assertTrue(result.has_workouts_in_period)
        self.assertEqual(result.weekly_consistency[0].active_dates, (date(2026, 11, 25),))
        self.assertEqual(result.exercise_progression[0].daily_history[0].max_reps, 7)
        self.assertEqual(result.personal_records[0].highest_session_volume.value, 595.0)

    def test_all_time_components_match_independent_calculations_with_iterable_input(self):
        workouts = [
            self.workout("W2", "2026-11-25T17:00:00+00:00", 40.0),
            self.workout("W1", "2026-11-23T04:59:00+00:00", 50.0),
            self.workout("W3", "2026-11-25T17:00:00.000001+00:00", 60.0),
        ]
        before = [workout.to_dict() for workout in workouts]
        result = calculate_student_analytics("ST001", iter(workouts), as_of=self.as_of)
        self.assertEqual(result.weekly_consistency,
                         tuple(calculate_weekly_consistency(workouts, self.as_of)))
        self.assertEqual(result.exercise_progression,
                         tuple(calculate_exercise_progression(workouts, as_of=self.as_of)))
        self.assertEqual(result.personal_records,
                         tuple(calculate_personal_records(workouts, self.as_of)))
        self.assertEqual(result.weekly_consistency[0].active_dates, (date(2026, 11, 22),))
        self.assertEqual(result.weekly_consistency[1].active_dates, (date(2026, 11, 25),))
        self.assertEqual(result.exercise_progression[0].daily_history[-1].max_weight_kg, 40.0)
        self.assertEqual(result.personal_records[0].heaviest_weight.value, 50.0)
        self.assertEqual([workout.to_dict() for workout in workouts], before)
        self.assertEqual(self.calculate(*reversed(workouts)), result)

    def test_implicit_reference_is_resolved_once_and_reused(self):
        resolve = analytics._reference_times
        reference, reference_day = resolve(self.as_of)

        def fixed_reference(as_of):
            if as_of is None:
                return reference, reference_day
            return resolve(as_of)

        workout = self.workout("W1", "2026-11-25T17:00:00+00:00")
        with patch.object(analytics, "_reference_times", side_effect=fixed_reference) as resolver:
            result = calculate_student_analytics("ST001", [workout])
        self.assertEqual(resolver.call_args_list, [call(None)] + [call(reference)] * 3)
        self.assertIs(result.as_of, reference)
        self.assertTrue(result.has_workouts_in_period)
        self.assertEqual(result.personal_records[0].heaviest_weight.workout_id, "W1")

    def test_mixed_or_wrong_student_input_is_rejected_even_if_future_dated(self):
        own = self.workout("W1", "2026-11-25T08:00:00-05:00")
        other = replace(self.workout("W2", "2026-11-26T09:00:00-05:00"), student_id="ST002")
        for workouts in ((other,), (own, other)):
            with self.subTest(workouts=workouts):
                with self.assertRaisesRegex(ValueError, "W2 does not belong to student 'ST001'"):
                    self.calculate(*workouts)

    def test_range_counts_only_selected_days_and_keeps_partial_week_labels(self):
        workouts = [
            self.workout("W1", "2026-11-09T09:00:00-05:00", 90.0),
            self.workout("W2", "2026-11-11T09:00:00-05:00", 40.0),
            self.workout("W3", "2026-11-24T04:59:00+00:00", 45.0),
            self.workout("W4", "2026-11-24T05:00:00+00:00", 50.0),
        ]
        start, end = date(2026, 11, 11), date(2026, 11, 23)
        result = self.calculate(*workouts, start_date=start, end_date=end)
        self.assertEqual((result.start_date, result.end_date), (start, end))
        self.assertTrue(result.has_workouts_in_period)
        self.assertEqual(result.weekly_consistency, (
            WeeklyConsistency(date(2026, 11, 9), date(2026, 11, 15), (start,), False, True),
            WeeklyConsistency(date(2026, 11, 16), date(2026, 11, 22), (), False),
            WeeklyConsistency(date(2026, 11, 23), date(2026, 11, 29), (end,), True, True),
        ))
        self.assertEqual(result.weekly_consistency, tuple(calculate_weekly_consistency(
            workouts, self.as_of, start_date=start, end_date=end,
        )))
        self.assertEqual(result.exercise_progression, tuple(calculate_exercise_progression(
            workouts, start, end, self.as_of,
        )))
        self.assertEqual([point.date for point in result.exercise_progression[0].daily_history],
                         [start, end])
        self.assertEqual(result.personal_records, self.calculate(*workouts).personal_records)
        self.assertEqual(result.personal_records[0].heaviest_weight.value, 90.0)

    def test_independent_date_bounds_and_future_dates_respect_reference_week(self):
        workout = self.workout("W1", "2026-11-17T09:00:00-05:00")
        after = self.calculate(workout, start_date=date(2026, 11, 24))
        self.assertEqual(after.weekly_consistency, (
            WeeklyConsistency(date(2026, 11, 23), date(2026, 11, 29), (), True, True),
        ))
        before = self.calculate(workout, end_date=date(2026, 11, 17))
        self.assertTrue(before.has_workouts_in_period)
        self.assertEqual(before.weekly_consistency, (
            WeeklyConsistency(date(2026, 11, 16), date(2026, 11, 22),
                              (date(2026, 11, 17),), False, True),
        ))
        beyond = self.calculate(workout, end_date=date(2026, 12, 31))
        self.assertEqual(beyond.weekly_consistency, self.calculate(workout).weekly_consistency)

    def test_empty_periods_distinguish_history_and_clamp_before_first_week(self):
        workout = self.workout("W1", "2026-11-20T09:00:00-05:00")
        records = self.calculate(workout).personal_records
        for bounds, expected_weeks in (
            ({"end_date": date(2026, 11, 15)}, ()),
            ({"end_date": date(2026, 11, 17)}, (
                WeeklyConsistency(date(2026, 11, 16), date(2026, 11, 22), (), False, True),
            )),
            ({"start_date": date(2026, 11, 26)}, ()),
        ):
            with self.subTest(bounds=bounds):
                result = self.calculate(workout, **bounds)
                self.assertTrue(result.has_workouts)
                self.assertFalse(result.has_workouts_in_period)
                self.assertEqual(result.weekly_consistency, expected_weeks)
                self.assertEqual(result.exercise_progression, ())
                self.assertEqual(result.personal_records, records)
        spanning = self.calculate(workout, start_date=date(2026, 10, 1))
        self.assertEqual(spanning.weekly_consistency[0].week_start, date(2026, 11, 16))

    def test_invalid_ranges_and_reference_raise_existing_errors(self):
        with self.assertRaisesRegex(ValueError, "start_date.*on or before"):
            self.calculate(start_date=date(2026, 11, 25), end_date=date(2026, 11, 24))
        for field, value in (("start_date", "2026-11-24"), ("end_date", self.as_of)):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, f"{field}.*calendar date"):
                    self.calculate(**{field: value})
        with self.assertRaisesRegex(ValueError, "as_of.*timezone-aware"):
            calculate_student_analytics("ST001", [], as_of=datetime(2026, 11, 25))

    def test_timestamp_boundary_and_overflow_errors_propagate(self):
        for timestamp, message in (
            ("2026-11-24T09:00:00", "W1 completed_at.*timezone-aware"),
            ("0001-01-01T00:00:00+01:00", "W1 completed_at.*supported datetime range"),
        ):
            with self.subTest(timestamp=timestamp):
                with self.assertRaisesRegex(ValueError, message):
                    self.calculate(self.workout("W1", timestamp))
        overflow = self.workout("W1", "2026-11-24T09:00:00-05:00", 1e308)
        with self.assertRaisesRegex(ValueError, "EX001 volume on 2026-11-24.*finite"):
            self.calculate(overflow)
        with self.assertRaisesRegex(ValueError, "EX001 session volume in workout W1.*finite"):
            self.calculate(overflow, end_date=date(2026, 11, 23))

    def test_unrepresentable_week_end_still_raises_when_week_is_included(self):
        workout = self.workout("W1", "9999-12-30T10:00:00+00:00")
        reference = datetime.fromisoformat("9999-12-31T12:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "Sunday.*supported date range"):
            calculate_student_analytics("ST001", [workout], as_of=reference)
