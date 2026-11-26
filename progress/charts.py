"""Presentation geometry for Feature 4 charts."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from progress.analytics import ExerciseProgression, WeeklyConsistency


@dataclass(frozen=True)
class WeeklyChartBar:
    week: WeeklyConsistency
    x: int
    center: int
    top: int
    height: int

    @property
    def date_label(self) -> str:
        start, end = self.week.week_start, self.week.week_end
        if start.month == end.month:
            return f"{start.day}–{end.day} {end:%b}"
        return f"{start.day} {start:%b}–{end.day} {end:%b}"


@dataclass(frozen=True)
class WeeklyChart:
    width: int
    height: int
    axis_x: int
    baseline: int
    bar_width: int
    ticks: tuple[tuple[int, int], ...]
    bars: tuple[WeeklyChartBar, ...]


def build_weekly_chart(weeks: tuple[WeeklyConsistency, ...]) -> WeeklyChart:
    """Lay out the already-calculated weeks on a fixed zero-to-seven scale."""
    axis_x, right_padding = 32, 12
    slot_width, bar_width = 108, 36
    baseline, pixels_per_day = 214, 26
    bars = []
    for index, week in enumerate(weeks):
        center = axis_x + index * slot_width + slot_width // 2
        height = week.active_days * pixels_per_day
        bars.append(WeeklyChartBar(
            week, center - bar_width // 2, center, baseline - height, height,
        ))
    return WeeklyChart(
        width=axis_x + len(bars) * slot_width + right_padding,
        height=280,
        axis_x=axis_x,
        baseline=baseline,
        bar_width=bar_width,
        ticks=tuple((days, baseline - days * pixels_per_day) for days in range(8)),
        bars=tuple(bars),
    )


@dataclass(frozen=True)
class ExerciseMetric:
    label: str
    measurement: str
    unit: str
    attribute: str


EXERCISE_METRICS = {
    "weight": ExerciseMetric("Weight", "Highest external weight", "kg", "max_weight_kg"),
    "reps": ExerciseMetric("Repetitions", "Most repetitions per set", "reps", "max_reps"),
    "volume": ExerciseMetric("Volume", "Combined daily volume", "kg", "total_volume_kg"),
}


@dataclass(frozen=True)
class ExerciseChartPoint:
    date: date
    value: int | float
    x: float
    y: float


@dataclass(frozen=True)
class ExerciseChart:
    exercise_name: str
    metric: ExerciseMetric
    width: int
    height: int
    axis_left: int
    axis_right: int
    baseline: int
    x_ticks: tuple[tuple[date, float], ...]
    y_ticks: tuple[tuple[str, float], ...]
    points: tuple[ExerciseChartPoint, ...]

    @property
    def all_zero(self) -> bool:
        return all(point.value == 0 for point in self.points)


def _exercise_axis_step(maximum: Decimal, whole_numbers: bool) -> Decimal:
    if not maximum:
        return Decimal(1)
    target = maximum / 4
    magnitude = Decimal(1).scaleb(target.adjusted())
    step = next(
        magnitude * multiplier
        for multiplier in (Decimal(1), Decimal(2), Decimal("2.5"), Decimal(5), Decimal(10))
        if magnitude * multiplier >= target
    )
    return step.to_integral_value(rounding=ROUND_CEILING) if whole_numbers else step


def _exercise_tick_label(value: Decimal) -> str:
    if not value:
        return "0"
    if -3 <= value.adjusted() <= 4:
        return format(value.normalize(), "f")
    return format(value.normalize(), ".2E")


def build_exercise_chart(
    exercise: ExerciseProgression,
    metric: ExerciseMetric,
) -> ExerciseChart | None:
    """Map one exercise's existing daily values onto a calendar-based SVG."""
    history = exercise.daily_history
    if not history:
        return None

    width, height = 660, 254
    axis_right = 602
    top, baseline = 22, 206
    first_date = history[0].date
    span = (history[-1].date - first_date).days
    values = [getattr(day, metric.attribute) for day in history]
    # Decimal keeps the axis finite even when a rounded tick exceeds float range.
    decimals = [Decimal(str(value)) for value in values]
    maximum = max(decimals)
    step = _exercise_axis_step(maximum, whole_numbers=metric.attribute == "max_reps")
    steps = int((maximum / step).to_integral_value(rounding=ROUND_CEILING)) if maximum else 1
    ceiling = steps * step
    tick_labels = tuple(_exercise_tick_label(tick * step) for tick in range(steps + 1))
    # Reserve room for scientific notation, including the gap before the grid.
    axis_left = max(76, 18 + 9 * max(map(len, tick_labels)))
    # Leave room for half a centred ISO date after the fixed-axis crop.
    plot_left = axis_left + 46

    def calendar_x(offset: int) -> float:
        if not span:
            return (axis_left + axis_right) / 2
        return round(plot_left + offset / span * (axis_right - plot_left), 2)

    def value_y(value: Decimal) -> float:
        return round(baseline - float(value / ceiling) * (baseline - top), 2)

    offsets = sorted({span * index // 4 for index in range(5)})
    return ExerciseChart(
        exercise_name=exercise.exercise_name,
        metric=metric,
        width=width,
        height=height,
        axis_left=axis_left,
        axis_right=axis_right,
        baseline=baseline,
        x_ticks=tuple(
            (first_date + timedelta(days=offset), calendar_x(offset))
            for offset in offsets
        ),
        y_ticks=tuple(
            (label, value_y(tick * step)) for tick, label in enumerate(tick_labels)
        ),
        points=tuple(
            ExerciseChartPoint(day.date, value, calendar_x((day.date - first_date).days), value_y(decimal))
            for day, value, decimal in zip(history, values, decimals)
        ),
    )
