# Gimmick
Created to create an app according to the UWI Computing course COMP2140 requirements

## Run the standalone Feature 4 app

From this checkout, use Python 3.12 and the project virtual environment.
For a fresh checkout, create the environment and install the pinned packages.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

```sh
.venv/bin/python -B -m flask --app app run
```

Open [Log Workout](http://127.0.0.1:5000/progress/) to select a saved
routine. A successful save opens its summary. [History](http://127.0.0.1:5000/progress/history)
lists saved workouts newest first. [My Progress](http://127.0.0.1:5000/progress/analytics)
shows Weekly Consistency, Individual Exercise Progression, and All-time
Personal Records from the student's saved workouts.

This standalone prototype always uses fictional student ST001. The
students and saved routines come from the JSON files in `fixtures/`
through `progress/mock_dependencies.py`. Group integration still needs
authenticated student identity and the team's routine provider.

Saved workouts go in the Git-ignored project file `data/workouts.json`.
Tests use an isolated file by passing `WORKOUT_STORAGE_PATH` to the app factory.

```sh
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m pip --disable-pip-version-check --no-cache-dir check
```

## Feature 4 architecture

- Jinja templates and scoped CSS render shared navigation, forms, records, and charts.
- The Flask Blueprint handles requests, selection validation, and HTTP responses.
- `ProgressService` validates workouts and supplies saved history to the analytics calculators.
- `progress.analytics` computes the three metrics. `progress.charts` prepares SVG coordinates and labels.
- `WorkoutLogRepository` manages JSON reads, ownership-scoped lookups, and atomic writes.
- `WorkoutLog` and `LoggedExercise` represent and serialise workout snapshots.

The standalone app supports logging, history, summaries, analytics, and
dashboard charts. Chart downloads and group integration remain pending.

## Feature 4 design merge notes

Step 4.1 proposes adding `to_dict()` and `from_dict(data)` to both
`LoggedExercise` and `WorkoutLog` in the class diagram. The methods
convert between model instances and JSON-compatible dictionaries using
the existing field names. Workout records embed exercise dictionaries and
use ISO 8601 completion timestamps with a UTC offset. Deserialisation
raises `ValueError` for malformed records. The model methods perform no
file I/O.

Step 4.2 proposes adding `WorkoutLogRepository` and its public methods to
the data-access layer in the final design merge.

- `save(workout)` validates and appends a workout with a unique ID across
  the store.
- `get_by_student(student_id)` returns that student's workouts in saved order.
- `get_by_id(student_id, workout_id)` returns a workout only when both the
  owner and workout ID match. It returns `None` when there is no match.

The default store is the project-relative `data/workouts.json`. A repository
can also receive a different path at construction. The file is a UTF-8 JSON
array using the Step 4.1 model records. A missing file represents an empty
history. Reads and saves raise `WorkoutLogStorageError` for malformed
content, invalid or duplicate records, and I/O failures. A save validates the
existing file before attempting to replace it.

Each save writes a temporary file in the destination directory and replaces
the destination after closing the temporary file. A shared in-process thread
lock serialises the full read-modify-write sequence across repository
instances. Readers open a complete snapshot. The lock covers threads in one
process, and saves rewrite the full array. Cross-process writers and
power-loss durability are outside the supported prototype scope.

Step 4.3 proposes adding `ProgressService.log_workout(student_id, routine, form_data)`
and `get_workout(student_id, workout_id)` to the business-logic layer for
the design merge. The app factory injects a repository into the service and
stores the service in `app.extensions["progress_service"]`. Pass
`WORKOUT_STORAGE_PATH` in the configuration mapping supplied to
`create_app()` to use an isolated store. The repository performs all JSON I/O.

A valid form POST saves through the service before returning HTTP 303 to
`GET /progress/workouts/<workout_id>`. That route looks up the saved workout
for the current mock student and returns HTTP 404 when there is no match.
Refreshing the summary repeats the GET. A separate POST can create another
workout. Storage errors return HTTP 500 with a generic message. A failed
save redisplays the entered values, and the underlying error is logged
server-side.

Step 4.4 proposes adding `ProgressService.get_workout_history(student_id)`
to the business-logic layer and `GET /progress/history` to the controller
design. The service returns repository records newest first by UTC instant.
Records completed at the same instant retain their saved order. The history
screen displays each record's original UTC offset and links to its saved
summary. Both views use the mock student's identity and the stored workout
snapshot, so routine changes or removal do not affect previous workouts.
An empty history returns HTTP 200 with a link to saved routines. Storage
failures return HTTP 500 with a generic message and server-side logging.
History and summary GET requests only read the repository.

### Step 5.2 proposed analytics changes

The proposed prototype metrics are Weekly Consistency in place of daily
streaks, Individual Exercise Progression in place of standalone overall
training volume, and Personal Records in place of Stronger/Weaker/Stagnant.
They support the SRS goals of showing accurate workout analytics and
updating them after logged workouts (AC-04.1–AC-04.3). They revise the SDS
and UML and are pending team approval. Weekly Consistency, Individual
Exercise Progression, and Personal Records are implemented in the
standalone dashboard. Exports are planned.

`progress.analytics.calculate_weekly_consistency(workouts, as_of=None)` takes
one student's completed `WorkoutLog` objects. `ProgressService` supplies
that student's history through the combined calculator. The calculation
has no Flask, authentication, or storage dependency.

Each Monday–Sunday week counts the distinct America/Jamaica calendar
dates with at least one completed workout. Unweighted sessions count.
The function returns chronological `WeeklyConsistency` results from the
first eligible week through the reference week. Each result has
`week_start`, `week_end`, sorted `active_dates`, a derived `active_days`
count, and an `is_current_week` flag. Gap weeks and a current week
without training appear with zero days. Empty or future-only history
returns an empty list.

The default reference is the current instant. An explicit `as_of` must
be timezone-aware. Workouts completed at the reference instant count.
Valid future timestamps are excluded before local calendar conversion.
Calculation uses the system's America/Jamaica timezone data via
`zoneinfo`. Naive timestamps, unsupported conversions, and a reference
week with an unrepresentable Sunday (when returning history) raise
`ValueError`. An eligible record that cannot be converted to a Jamaica
date stops the calculation with its ID in the error.

### Step 5.3 Individual Exercise Progression

For the proposed SDS and UML revision, the analytics component adds
`calculate_exercise_progression(workouts, start_date=None, end_date=None,
as_of=None)`, `ExerciseProgression`, and `ExerciseDailyProgress`. The
function accepts one student's completed workout snapshots and returns
exercise series ordered by stable exercise ID. Recorded names can change
across routines without splitting a series. Each series uses the most
recent eligible name by completion instant. Ties use the greatest workout
ID in lexical order and then the last matching entry in that workout.
If duplicate inputs share all those keys, the lexically greatest name wins.

Each exercise has one point per Jamaica calendar date on which it was
logged. The point contains the date, the highest recorded external
weight, the highest recorded repetitions per set, and the sum of
`sets × reps × weight_kg` for all matching entries, including multiple
sessions and repeated exercise entries. The two maxima are independent.
Zero-weight sessions retain repetition history and add zero external-weight
volume. Dates with no performances are omitted. Volume uses the decimal
representation of each stored weight and sums exactly before converting
the completed total to a float for output. This uses the precision
available in the stored weights. An unrepresentable total raises
`ValueError` identifying the exercise and date. Volume alone does not
establish a change in muscular strength.

Optional start and end dates are inclusive and can be supplied separately.
Omit both for all eligible history. Dates use America/Jamaica and the
timezone-aware `as_of` cutoff applies before local grouping, with future
workouts excluded. Invalid dates, reversed ranges, naive timestamps and
unsupported conversions raise `ValueError`. A period without eligible
exercise records returns an empty list. The calculation uses the existing
sets, reps and weight per logged exercise entry. Individual sets and
bodyweight itself are outside this external-weight volume calculation.

### Step 5.4 Personal Records

The proposed SDS and UML revision adds
`calculate_personal_records(workouts, as_of=None)`, `ExercisePersonalRecords`,
`PersonalBest`, and `RepetitionRecord`. The calculation uses one student's
full eligible history of saved workout snapshots. Results are grouped and
ordered by stable exercise ID. As in Exercise Progression, each display
name comes from the latest eligible instant, then the lexically greatest
workout ID and last matching entry. The calculation assumes saved workout
IDs are unique, as enforced by the repository.

- Heaviest weight is the highest positive external weight recorded.
- Repetition records track the highest reps per set at each exact weight.
  Records are ordered by ascending weight. Numerically equal weights such
  as 40 and 40.0 share a record. Zero weight has its own repetition record.
- Highest session volume is the largest positive sum of
  `sets × reps × weight_kg` for the exercise within one workout. Repeated
  entries count toward that session. Exercise Progression instead sums
  all sessions on a Jamaica calendar date.

The first eligible performance establishes each available record. A
strict improvement replaces it. Equal values keep the earliest achievement.
Session volume compares exact totals before float conversion. For example,
three reps at 0.1 kg and one rep at 0.3 kg have equal volume and keep the
first achievement. No tolerance or display rounding is used for ranking.
At equal instants, the lexically smallest workout ID takes precedence.
Each record retains its original offset-aware timestamp, Jamaica calendar
date, and workout ID. An exclusively unweighted exercise has no weight or
volume record. Empty or future-only history returns an empty list.

The shared timezone-aware cutoff includes the reference instant and
excludes future workouts. Invalid timestamps, unsupported date conversions,
and session volume overflow raise `ValueError`. Records use the saved
sets, repetitions per set, and external weight. They use no separate
storage and do not include individual-set or bodyweight measurements.

### Step 5.5 combined student analytics

The proposed SDS and UML revision adds `StudentProgressAnalytics` and
`calculate_student_analytics(student_id, workouts, start_date=None,
end_date=None, as_of=None)`. The result holds the student ID, tuples of
all three metrics, the requested dates, the resolved UTC reference
instant, and separate `has_workouts` and `has_workouts_in_period` flags.
Every supplied workout must belong to the requested student, including
future-dated records. The calculation resolves the reference once and
uses that same instant for each metric. Workouts completed at the cutoff
are eligible.

Start and end dates are inclusive Jamaica calendar dates and can be used
independently. They filter Exercise Progression and weekly training dates.
Personal Records use all eligible history regardless of the selected
dates. Weekly Consistency now also accepts optional keyword arguments
`start_date` and `end_date`. It returns weeks intersecting the selection
from the Monday of the first eligible workout week through the reference
date, including zero-day weeks. Explicit selections before that first
Monday add no earlier weeks. A selection entirely before that Monday or
after the reference date returns no weeks. A selection within that span
can return zero-day weeks even when it contains no workouts.

Week labels always run Monday through Sunday. `is_partial_week` means
the selected start or end date cuts that calendar week. The
`is_current_week` flag independently marks the reference week when it
is included, even if the selection also cuts it. A student with no
eligible history has empty metrics and both flags false. A student with
history outside the selected period still has all-time records and
`has_workouts = True`, while `has_workouts_in_period = False`.

The calculators remain independent of Flask and storage. The
standalone dashboard uses the combined result. Team approval of the
proposed design and chart exports are pending.

### Step 5.6 analytics service integration

The proposed SDS and UML revision adds
`ProgressService.get_analytics(student_id, start_date=None, end_date=None,
as_of=None) -> StudentProgressAnalytics`. The service reads the full
student-scoped history from its injected `WorkoutLogRepository` on every
call and delegates to `calculate_student_analytics`. The calculator
also rejects any record whose student ID differs from the requested ID.
The existing app factory supplies the same service and repository used
for workout logging.

Inclusive Jamaica date bounds apply to Weekly Consistency and Exercise
Progression. Personal Records use all eligible history. All three metrics
share the reference instant, including when calls use an explicit
timezone-aware `as_of`. Empty history and an empty selected period retain
their distinct flags. Storage and calculation errors propagate to callers.

Each call derives metrics from saved workouts, so a successful save is
visible to the next analytics request. Logging and analytics retrieval
are separate. The saved workouts are the source of truth and no analytics
cache or separate analytics file is needed. My Progress displays the
refreshed data on the next visit.

### Step 6.1 Feature 4 presentation

Feature 4 pages share `progress/base.html` and use the Blueprint's local
`css/feature4.css`. The layout has a skip link and highlights the current
navigation destination. The CSS scopes the provisional neutral and blue
palette, responsive cards, forms, and focus styles to Feature 4.

- **Log Workout** (`/progress/`) lists saved routines and leads to the
  existing logging form.
- **History** (`/progress/history`) lists saved workouts and leads to
  their summaries.
- **My Progress** (`/progress/analytics`) displays Weekly Consistency,
  Individual Exercise Progression, and all-time Personal Records.

The feature uses system fonts and local assets. A shared group layout can
replace the local header and navigation when the team integrates Feature 4.
The proposed chart approach is locally
generated SVG with lightweight JavaScript where useful, so charts can work
offline and support later exports. The group has yet to approve that
approach and the final palette.

### Step 6.2 live My Progress dashboard

`GET /progress/analytics` uses the existing mock student identity and
calls `ProgressService.get_analytics()` with all eligible history. Each
page request reads the current persisted workouts. A successful workout
save still redirects to its summary. Visiting My Progress afterward
shows the refreshed data.

The dashboard shows active training days for Monday–Sunday weeks.
Exercise Progression uses daily values for each exercise. All-time Personal
Records show available weight and session-volume bests, repetition records at each
weight, and their first-achieved dates. An unweighted exercise can show
repetition records even when it has no weight or session-volume best.

The dashboard shows a Log Workout link and an explanation when the student
has no eligible workouts. Storage and calculation errors use the shared
error page with HTTP 500 and server-side diagnostic logging. The route
uses the existing service interface as a presentation-layer addition to
the proposed design.

### Step 6.3 Weekly Consistency chart

My Progress displays one vertical SVG bar per Monday–Sunday week in
chronological order. Each active training day adds the same height on a
fixed zero-to-seven scale. Monday dates and exact counts label the bars.
Zero-day weeks show a baseline marker and a visible zero. The incomplete
current week uses a dashed outline and a text label. A partially selected
week has its own text label whenever the service supplies that flag.

The route passes the service results to `build_weekly_chart()` in
`progress/charts.py` for SVG coordinates. The local Jinja component
`progress/weekly_chart.svg` draws the chart using those results. CSS
preserves bar and label sizes inside a keyboard-focusable horizontal
scroll region. The expandable weekly data table supplies both calendar
dates, exact counts, and status for each week. The empty-history page
shows a logging link.

The presentation geometry and SVG markup can be reused for a future
export. A standalone SVG will need its styles embedded. Downloads remain a
future milestone. Team approval of the proposed SDS and UML revisions is pending.

### Step 6.4 Individual Exercise Progression chart

The Exercise and Metric selects submit GET parameters `exercise` and
`metric` to My Progress. The page returns to the exercise section with
both selections preserved. Exercise options are based on the current
student's history and use stable IDs. Duplicate names include their IDs.
The first exercise in ID order and Weight are the defaults. Unavailable
exercise IDs and unknown metric keys fall back to the relevant defaults.
Each request reads fresh analytics from the existing service.

Choose Weight for daily peak external weight (kg), Repetitions for daily
peak reps per set, or Volume for daily combined sets × reps × weight
(kg) for that exercise. The weight and reps peaks may come from different
performances. `build_exercise_chart()` maps the selected daily series
onto elapsed Jamaica calendar days and a zero-based vertical scale with
rounded ticks. The number of date labels is capped at five. Dots are the
recorded observations, and dashed segments connect consecutive observations
across gaps. The chart adds no data points between them.

The Jinja templates `progress/exercise_progression.html` and
`progress/exercise_chart.svg` render the controls and SVG. A one-date
history has a centred dot. Constant histories keep a valid scale, and
all-zero weights and volumes remain visible on the baseline. An unweighted
exercise can still have a repetition history. The empty exercise state
offers a link to Log Workout. On narrow screens the chart scrolls inside
its card, and View exercise data expands to show the exact dates and
values for the selected metric.

The form preserves the applied period. Phase 7 can reuse the selected
series and standalone SVG template with embedded styles. Downloads and
team approval of the proposed SDS and UML revisions remain pending.

### Step 6.5 Personal Records

Personal Records shows all-time achievements for one exercise using
`ExercisePersonalRecords` and its existing record values. Each card
shows the first-achievement date in Jamaica. Heaviest Weight uses the
best positive external load. Repetition Record shows the best reps per
set at one recorded weight. Highest Session Volume uses the best
exercise-specific volume in one workout. Each request reads fresh
analytics from the existing service.

The offline GET forms use `record_exercise` and `record_weight`. The
first exercise in stable ID order is the default. Duplicate names show
their IDs. Exercise changes default the repetition card to its highest
recorded weight. The weight selector appears when multiple weights
exist and retains the full stored decimal precision. Invalid selections
fall back to the applicable default. Unweighted repetition records use
an Unweighted label. Exclusively unweighted exercises omit positive
weight and session-volume cards.

`progress/personal_records.html` renders the selector and responsive
cards. The shared `progress/selection_fields.html` macro preserves the
other section's resolved selections in both directions. It also
preserves the selected period and any custom bounds. Records remain
all-time regardless of dashboard dates. Downloads and team approval of
the proposed SDS and UML changes are pending.

### Step 6.6 Analytics periods and dashboard refresh

My Progress offers All time (the default), Last 30 days, Last 7 days and
Custom date range. The relative presets include today in Jamaica and
the preceding 29 or six calendar dates. `resolve_period()` in
`progress/periods.py` resolves the inclusive bounds. The controller
uses the same UTC reference instant for that resolution and
`ProgressService.get_analytics()`. The custom period accepts either
or both ISO dates. A missing start includes earlier eligible history,
and a missing end includes eligible history through the reference
instant. Future dates are allowed, but future workouts remain excluded.
Invalid periods, invalid dates and reversed bounds return HTTP 400
with a correction form. Storage and calculation errors keep the
existing HTTP 500 response.

`progress/analytics_period.html` renders the native GET controls and
applied dates. Choose Custom date range to use the date fields. Reset to
All time keeps the exercise, metric and record selections. The chart
and record forms carry the period key and only send dates for a custom
period, so relative presets re-resolve on each request. A future
download route can reuse the resolver and the same query parameters.

Weekly Consistency counts only training dates in range. The chart and
detail table identify current and partial weeks separately, retaining
zero-day weeks within the backend's history boundaries. The exercise
selector uses all-time eligible exercise names from Personal Records.
When the chosen exercise has no points in range, it stays selected
with an explanation. A period with no workouts is distinct from an
account with no history. Personal Records stay all-time in either chart
view.

Opening My Progress after saving a workout recalculates the dashboard.
The new workout affects the charts for periods that include its Jamaica
training date and can update all-time records even when outside the
chart period. The mock student identity remains in use. SVG downloads
and team integration are pending, along with approval of the proposed
SDS and UML revisions.

### Phase 6 verification and integration

The standalone dashboard was verified with the mock student identity.
The design merge should capture the analytics route, the period resolver,
the shared GET selection fields, and the SVG chart presentation models.
Group integration needs the shared student identity, routine provider, and
layout. Team approval of the proposed SDS and UML metrics remains pending.
AC-04.4 and scenarios 4.5 and 4.6 depend on chart downloads. Scenario 4.3
has verified charts and still requires its save option.
