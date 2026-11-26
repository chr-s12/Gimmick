# Gimmick
Created to create an app according to the UWI Computing course COMP2140 requirements

## Run the Gymmick app

The whole prototype (all seven features, login and roles) runs as one local Flask app (SRS 1.4.1).

```sh
python -m pip install -r requirements.txt
python seedData.py --reset      # demo accounts, six weeks of attendance, trainer times, templates
python app.py                   # then open http://127.0.0.1:5000
```

Demo logins (password `gymmick123` for all of them):

| Role | UWI ID | Lands on |
|---|---|---|
| Student | `620200001` (Alex Brown) | Home: routines, sessions, occupancy |
| Personal trainer | `700000001` (Devon Clarke) | My schedule |
| Gym staff | `100000001` | Front desk |
| Gym operator | `100000002` | Usage reports |

New students and trainers can also register on the sign-up page.

Check-ins are only accepted during gym opening hours (SRS 1.6.8). To try the front desk outside those hours,
start the app with the environment variable `GYMMICK_IGNORE_HOURS=1`.

To show the queue without typing 20 check-ins, `python seedData.py --fill-gym` checks demo students in
until 19 people are inside (`--fill-gym 20` makes the gym full). It works while the app is running.

A step-by-step guide with screenshots of every feature is in [docs/userGuide.md](docs/userGuide.md), and
the 8-minute demo script is in [docs/demoRunSheet.md](docs/demoRunSheet.md).

### Where each feature lives

Each feature follows the SDS layers: a Blueprint in `controllers/` checks the login and role, calls one
service, and the service reads and writes JSON files in `data/` through its repositories.

| Feature | Pages (`controllers/`) | Service |
|---|---|---|
| Login, roles, password resets (SRS 3.2.2) | `auth.py`, `home.py` | `accounts/` |
| 1 Build Routines | `routines.py` | `routineBuilder/` (uses `Routine`, `Exercise`, `Student`) |
| 2 Manage Availability | `availability.py` | `manageAvailability/` |
| 3 Occupancy Monitoring | `occupancy.py` | `occupancyTrends/occupancyService.py` |
| 4 Track Progress | `progress/routes.py` | `progress/` |
| 5 Book Trainers | `booking.py` | `bookTrainers/` |
| 6 View Clientele | `clients.py` | `viewClientele/` |
| 7 Analyze Usage Trends | `reports.py` | `occupancyTrends/reportService.py` |

`app.py` builds the services and Blueprints, and on every request checks the login, the 15-minute
inactivity timeout and the user's role, and sends session reminders that are due. Failed logins and
server errors are written to `logs/gymmick.log` (SRS 4.3). The operator can download a backup of
`data/` (SRS 4.1).

### Tests

```sh
python -m pytest
```

`tests/testWebApp.py` drives the real pages end to end; the other test files cover each service.

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

In the full app, Track Progress uses the logged-in student and their saved
and trainer-added routines (`app.ProgressAccounts`). Passing
`PROGRESS_FIXTURES=True` to the app factory (as the Feature 4 tests do)
runs it on fictional student ST001 instead, with the students and routines
from the JSON files in `fixtures/` through `progress/mock_dependencies.py`.

Saved workouts go in the Git-ignored project file `data/workoutLogs.json`, where View Clientele also reads them.
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
dashboard charts, including SVG downloads for Weekly Consistency and
Individual Exercise Progression. Group integration remains pending.

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
Records completed at the same instant retain their saved order. History
links to each saved summary. Both views display completion times in the
Jamaica timezone used by analytics while retaining the original timestamp
in storage and in the HTML time element. If a boundary timestamp cannot
be converted, the view displays its stored offset. Both views use the
mock student's identity and the stored workout
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
standalone dashboard. Weekly Consistency and Exercise Progression
can be saved as standalone SVGs.

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
proposed design remains pending.

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

Phase 7 reuses the presentation geometry and SVG markup and embeds the
chart styles for independent viewing. Team approval of the proposed SDS and UML revisions is pending.

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

The form preserves the applied period. Phase 7 exports the currently
selected series with embedded styles. Team approval of the proposed SDS and UML revisions remain pending.

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
all-time regardless of dashboard dates. Team approval of the proposed
SDS and UML changes is pending.

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
chart period. The mock student identity remains in use. Group integration
and approval of the proposed SDS and UML revisions are pending.

### Phase 6 verification and integration

The standalone dashboard was verified with the mock student identity.
The design merge should capture the analytics route, the period resolver,
the shared GET selection fields, and the SVG chart presentation models.
Group integration needs the shared student identity, routine provider, and
layout. Team approval of the proposed SDS and UML metrics remains pending.
Phase 7 adds the chart save option and standalone file access for AC-04.4
and Scenarios 4.3 and 4.5. The original Scenario 4.6 remains unverified.
See the Phase 8 acceptance review for the proposed replacement.

### Step 7.1 SVG export foundation

The proposed offline export format is SVG. The local ES module
`progress/static/js/chart_export.js` takes an already rendered dashboard
SVG. Step 7.1 introduced the reusable component before chart controls.
`chartDimensions()` validates the SVG root and intrinsic geometry.
`prepareStandaloneSvg()` copies the chart into a detached SVG using a
limited set of graphical elements and attributes. It preserves the
original dimensions and full viewBox, even if only part of the chart is
visible on screen. It inlines the required computed paints, strokes,
fonts and label styles, and adds a white background. The original
dashboard chart is left intact. Links, scripts, event handlers, hidden
graphics and remote paint references are excluded.

The caller can supply a title, description, measurement, exercise,
metric, unit, applied period, start and end dates, and notes from the
displayed chart. The module writes those values as accessible SVG text
through the DOM and does not recalculate relative dates or analytics.
`serializeSvg()` uses the browser XML serializer, `createSvgBlob()`
creates an `image/svg+xml` Blob, and `makeChartFilename()` builds a
bounded filename from descriptive components such as the chart or
exercise name, metric and optional dates. The chart controls should
supply only presentation data and keep account identifiers out of those
values. No storage, export route or JavaScript dependency is required.

`exportChart()` prepares the displayed snapshot and dispatches the save
method. In auto mode, `supportsDirectSave()` checks for a secure context
with a callable `showSaveFilePicker()`. Invoke it from the user's actual
save action to retain browser activation. `saveSvgDirect()` reports a
save only after writing and closing the stream. Picker dismissal stops
the operation without downloading a second copy. Browsers can also abort
a picker for a restricted selection. Unsupported browsers
can use `downloadSvg()`, which clicks a temporary Blob link, removes
the link, and revokes its object URL after a delay. That result confirms
download initiation only.

Status codes distinguish preparation failure, unsupported direct save,
picker dismissal, permission denial, detectable storage or quota errors,
other write failures, and download initiation failure. Error details are
available to callers separately from the outcome status. A quota signal
alone cannot establish insufficient physical disk space. Standard browser
downloads do not reliably report local write failures. The Phase 8
acceptance review records the proposed change to Scenario 4.6.

Browser API references:
[Chrome File System Access guide](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access)
and [WHATWG File System Standard](https://fs.spec.whatwg.org/).

Run the dependency-free export helper checks with Node.js 22 or later.

```sh
node --input-type=module --check < progress/static/js/chart_export.js
node --test tests/test_chart_export.mjs
```

### Step 7.2 Weekly Consistency download

The **Download SVG** button next to Weekly Consistency uses the local
`weekly_chart_download.js` module. It targets the displayed weekly SVG
and exports that snapshot without refreshing analytics or changing the
dashboard. Valid zero-day charts can be downloaded. The control appears
when a weekly chart is available.

The module reads the applied period, inclusive boundaries, plotted
Monday–Sunday extent, and relevant week statuses from server-rendered
attributes. Relative periods retain the resolved dates from that page
load. Custom ranges with an omitted bound show From or Through, and
All time has neither bound. The standalone image includes a visible
title, measurement, period and week context above the complete chart.
The chart retains its own dimensions and viewBox. Styling is inline
and the SVG includes accessible title and description text.

All time uses `weekly-consistency.svg`. Bounded ranges add their dates
as `START-to-END`, while open-ended ranges use `from-START` or
`through-END`. The shared filename helper sanitises the result.

The button uses the standard browser download path and announces
initiation. The direct-save helper remains available in the shared
module for the later save interaction. Browser verification checked
keyboard activation, desktop and mobile layout, and preservation of
the displayed chart after a subsequent workout. A downloaded 15-week
SVG matched the selected dates, values and indicators. Quick Look
rendered it after the local Flask preview stopped.

Step 7.4 added the shared save controls and feedback. This walkthrough
verified the standard browser download.

### Step 7.3 Individual Exercise Progression downloads

**Download SVG** beside the selected exercise and metric exports the
displayed Weight, Repetitions, or Volume chart. The browser uses the
current SVG and its server-resolved exercise, metric, and period. The
export keeps the full chart viewport, axes, line and markers, including
each point's exact value and date. It adds a visible title, exercise,
metric, measurement and plotted dates above the chart. The applied
period and its available inclusive bounds are also carried in the
accessible description. The SVG is self-contained and readable offline.

`exerciseExportOptions()` prepares the displayed chart metadata.
Both chart modules use `describePeriod()` and `bindChartDownload()`
from the local `chart_download.js` helper for consistent period labels,
button binding, and download initiation feedback. The standard browser
download path initiates a download. The app cannot confirm a local write
through that mechanism.

Filenames use `EXERCISE-METRIC-progression.svg`, with the applicable
date suffix from the weekly convention. Names are sanitised and shortened
when needed while retaining the metric and date suffix. Duplicate exercise
names use their selector label and an ID-based filename key to distinguish
the files. Long or punctuated IDs use a short deterministic fingerprint
to preserve both the distinguishing key and the metric and date suffixes.
All time adds no date suffix. Empty exercise periods have no exercise
download control. Valid unweighted histories retain their zero-weight or
zero-volume points, and single recorded performances export one marker.

Browser verification at desktop and mobile sizes produced six exercise
SVG files and a Weekly Consistency regression download. The three
Bench Press metrics kept all 13 points. A Last 7 days export kept its
original two points after another tab saved a workout. Zero-volume and
single-point files parsed successfully. Quick Look rendered the three
all-time metrics and the filtered volume SVG after Flask stopped.

Step 7.4 added shared direct-save controls and error handling. Actual
insufficient physical storage remains unverified.

### Step 7.4 Shared chart saving and feedback

In My Progress, use the action beside either Weekly Consistency or the
selected Exercise Progression chart. In a secure context that exposes
a native save picker, **Save SVG** lets you choose a destination and
**Download SVG** uses the browser's normal downloads. Browsers without
the picker show **Download SVG** as the primary action. Open the resulting
file from the selected folder or the browser's downloads in an SVG viewer.

`bindChartDownload()` chooses the available controls, invokes the same
snapshot exporter directly in the click handler, and guards both actions
for that chart while a save is pending. The active button keeps keyboard
focus. Each chart has its own status live region. The direct path reports
success only when writing and closing both succeed. The download path
reports initiation. Cancelling a picker reports cancellation. Permission
denial and write failures report their own messages and leave the
explicit download action available without starting it automatically.
Preparation failures have separate feedback. Technical details are kept
out of the interface.

When the browser reports `QuotaExceededError`, the interface identifies
a browser storage or quota problem and suggests checking available space
or choosing another destination. An ambiguous write error receives
generic feedback. The [File System Standard](https://fs.spec.whatwg.org/)
distinguishes browser storage quota from local disk errors, and standard
downloads do not expose a reliable write result to the application.
The [File System Access picker specification](https://wicg.github.io/file-system-access/)
also requires transient user activation.

Desktop and mobile browser checks created both standard SVG downloads.
Their full chart viewBoxes, period metadata and values were checked on
disk. Quick Look rendered both files after Flask stopped. The native
picker request entered the pending state in the in-app browser, where
automation could not operate the destination dialog. Mocked tests
covered confirmed write and close, cancellation, permission and quota
failures, generic write errors, cleanup and overlapping attempts.
Actual native file-write failures and insufficient physical storage
remain unverified. Further physical-storage testing is outside the
proposed prototype scope.

To check direct saving manually, open the local My Progress page in
desktop Chrome. Choose **Save SVG**, select a new file in a writable
folder, and wait for “Visualisation saved successfully.” Open that file
in an SVG viewer. Then start another save and cancel the picker.
Confirm “Save cancelled” and check that the browser did not start a
download. The secondary **Download SVG** action remains available.

### Phase 7 final verification and design handoff

An isolated desktop walkthrough saved a workout, refreshed My Progress
and downloaded a Last 7 days Weekly Consistency SVG. A mobile walkthrough
chose Bicep Curls, selected Volume and downloaded a Last 30 days
Exercise Progression SVG. Keyboard activation worked for both. Both
downloads preserved the displayed SVG and the resolved date bounds.
The saved files were checked on disk and rendered in Quick Look after
Flask stopped. These checks support AC-04.4 and Scenarios 4.3 and 4.5
for the standalone mock-student prototype.

Desktop Chrome exposed the native-save action. The browser reported
cancellation, restored the controls and kept the download option
available. Confirmed native writing and closing remain covered by mocks.
Actual write failures and insufficient physical device storage are still
unverified, so Scenario 4.6 remains partially implemented.

For the proposed SDS and UML revision, record the browser-side SVG
snapshot preparation, chart-specific metadata adapters and shared save
and feedback handler in the presentation layer. The snapshot comes
from the existing chart markup and needs no export endpoint or
persistent export data. Group integration still needs real authentication,
shared student and routine providers, and approval of the revised
metrics.

### Step 8.1 consolidated acceptance review

The regression run passed 149 Python tests and 17 JavaScript tests.
Isolated storage was used for workout tests and the application store
checksum matched before and after the run. Earlier actual browser and
offline SVG checks support AC-04.0 through AC-04.4 and Scenarios 4.1
through 4.5 together with the automated evidence. This assessment covers
the standalone mock-student prototype. Analytics recalculate on the next
dashboard request after a successful save. Real authentication, shared
Routine Builder integration and final group access-control verification
remain outstanding. Team approval of the proposed analytics metrics
and the associated SDS and UML changes remains pending.

**Proposed SRS revision (team approval pending) — Scenario 4.6:
Visualisation Saving Failure**

> Given the student is viewing a generated visualisation,
>
> When a file-saving operation fails and the browser reports the failure,
>
> Then Gymmick displays an appropriate error message and allows the
> student to retry or use an alternative download method.

The original insufficient-device-storage scenario remains unverified.
Ordinary browser-managed downloads do not reliably expose local
file-write failures or available disk space to Gymmick. Further physical
storage detection and testing are outside the proposed prototype scope.
The existing direct-save implementation remains in place. Mocked API and
control tests verify browser-reported failure classification, feedback,
and control restoration. Actual native file writing and actual write
failure handling remain unverified. Review the original scenario for
replacement or removal when the team reviews the SRS.

### Step 8.2 performance and offline verification

SRS v1.1 §3.1.4, Data Loading, states: “User workout history, saved
routine templates, and personal dashboards shall load within 5 seconds.”
Sections 1.4–1.5 describe a single-computer browser prototype backed by
local Flask and JSON that works without internet after installation.

The benchmark ran on macOS 26.7.3, Apple M1 (arm64), 16 GiB installed
RAM, Python 3.12.14 and Flask 3.1.3. The deterministic fixture includes
three routines, overlapping exercise IDs, gap weeks, same-day sessions,
decimal weights, unweighted exercises and a second fictional owner.
The 30, 250 and 1,000 total records contained 27, 225 and 900 workouts for
the mock student and occupied 20,011, 166,742 and 666,942 JSON bytes.

Run the standard-library benchmark from the repo root:

```sh
PYTHONPATH="$PWD" .venv/bin/python -B scripts/benchmark_progress.py
```

Each operation has one untimed warm-up and seven measured repetitions.
The script uses `perf_counter()`, restores the JSON baseline before
each timed save, fixes the analytics reference date in Jamaica, and
checks outcomes outside the timed interval. Flask test-client results
include request handling, storage, calculations and rendered response
construction. The table shows median / maximum milliseconds.

| Flask test-client route | 30 records | 250 records | 1,000 records |
| --- | ---: | ---: | ---: |
| Saved routines | 0.27 / 0.39 | 0.26 / 0.51 | 0.25 / 0.31 |
| History | 2.44 / 2.60 | 18.93 / 23.41 | 74.65 / 77.26 |
| Individual workout summary | 0.61 / 0.73 | 3.36 / 3.86 | 12.99 / 18.30 |
| My Progress, all time | 2.23 / 2.44 | 13.96 / 18.19 | 52.82 / 60.24 |
| My Progress, last 30 days | 1.92 / 2.11 | 8.16 / 8.33 | 28.50 / 33.29 |
| My Progress, last 7 days | 1.64 / 1.82 | 8.00 / 8.09 | 29.63 / 35.53 |
| My Progress, custom dates | 1.94 / 2.05 | 8.05 / 8.35 | 29.88 / 33.93 |

At 1,000 records, the repository's student lookup was 12.73 / 12.96 ms,
individual lookup 12.69 / 17.22 ms and save 39.37 / 45.22 ms. All-time
service analytics took 43.60 / 48.10 ms, including repository reads.
The calculation alone took 29.69 / 35.30 ms. The script prints the
complete diagnostic results. Save, individual summary and SVG preparation
are supplemental measurements.

Headless Chrome 158.0.8127.37 used loopback Flask on port 5094, with debug
and reloader off and browser cache disabled. At 1,000 records, five
measured navigations per action followed one warm-up. At 1280 × 900,
saved routines took 7.30 / 9.10 ms, History 64.30 / 72.60 ms, My Progress
83.50 / 98.30 ms, exercise and metric selection 91.60 / 97.00 ms, and
period selection 53.40 / 59.00 ms. At 390 × 844, My Progress took
94.20 / 112.60 ms. Timing was navigation start through `loadEventEnd`
and includes local requests, DOM parsing and the load event. It does not
measure completion of visual painting. Both viewports contained the long
chart scroll areas without page-wide overflow. Filtered SVG preparation
took 0.80 / 0.90 ms for Weekly Consistency and 0.30 / 0.50 ms for
Exercise Progression (seven calls after warm-up, through Blob creation).
All tested SRS loading operations met the five-second target.

To reproduce the browser setup, start an isolated loopback server:

```sh
PYTHONPATH="$PWD" .venv/bin/python -B scripts/benchmark_progress.py --serve 1000 --port 5094
```

Use a disposable Chrome profile configured with
`--proxy-server=http://127.0.0.1:1`. Verify that an external request fails
while `http://127.0.0.1:5094/progress/` loads. Use DevTools to disable
cache, set each viewport and read
`performance.getEntriesByType("navigation")[0].loadEventEnd` after each
navigation. Use the All time or custom dates 2026-10-15 to 2026-11-20 for
the fixed historical fixture. For the offline walkthrough, log and save a
workout, open its summary and History, select a chart exercise, metric and
period, inspect Personal Records, and use both standard SVG downloads.

In the verified run, the external canary failed with
`ERR_PROXY_CONNECTION_FAILED`. The app requested only loopback resources.
The workout was saved locally and both SVGs downloaded. After stopping
Flask, both SVGs rendered through Quick Look and passed XML checks for
standalone chart geometry and absence of external links. The walkthrough
used a browser-level proxy block. It did not disconnect the computer's
network. Application pages require the local Flask server.

These results cover the single-user standalone prototype on the tested
hardware and fixture sizes. Repository reads parse the full JSON file and
saves rewrite it. Analytics and chart rendering scale with the amount of
history. Production capacity, concurrent users and final integration
performance were outside these measurements. No performance fixes were
needed. The full regression suites passed with 149 Python and 17
JavaScript tests, and the real workout store checksum was unchanged.

### Step 8.3 final usability and implementation review

A visible, isolated browser walkthrough verified the route from a saved
routine to the completed summary, History and My Progress. A negative
weight was blocked and the entered repetitions were retained. A corrected
Bench Press entry of 3 × 8 × 42.5 kg showed 1,020 kg for daily volume and
1,020 kg as its session record. Exercise, metric and period controls
worked, benchmark and logged exercises with the same name remained
distinguishable, and Personal Records kept all-time scope. Both charts
downloaded using the keyboard and opened locally in Quick Look.

Keyboard checks covered a focused invalid field, scrolling the weekly
chart with the right arrow, opening its exact-data table with Enter, and
entering both chart download actions. Headings, form labels, navigation
state, status associations and chart alternatives were also reviewed in
the templates. At 1280 × 900 and 390 × 844 the inspected layout contained
chart scrolling without page-wide overflow. This is a focused usability
review. Comprehensive assistive-technology testing remains outstanding.

History and Summary previously showed storage timestamps in different
formats. An evening workout could appear to have been logged the next day
when stored in UTC. Both screens now display Jamaica time, consistent
with analytics. The browser showed the same saved workout as 17:11:57
UTC before the fix and 12:11:57 Jamaica time after it. F4-14 extends
F4-01 and F4-04 with a cross-midnight regression. A fictional workout
at 2026-11-25 02:30 UTC must display as November 24 at 21:30 Jamaica
time on both pages with its stored timestamp intact. The test passed
and the date-limit fallback remains covered.

The app factory, progress blueprint, service, calculator, repository
and local export modules keep their separate responsibilities. The
benchmark and preview use a generated fictional dataset in a
`TemporaryDirectory` and inject the JSON path into `create_app()`.
Normal shutdown cleans up that directory. No benchmark rerun was needed.

Group integration dependencies:

- Register the progress blueprint and wire the existing service to the
  shared app configuration. Align the route prefix, navigation, base
  template and CSS with the group interface.
- Replace the fixed mock student with the authenticated student ID and
  role. Adapt student lookup to provide the display name currently read
  from `username`. Verify the student isolation boundaries under real
  authentication. Agree on trainer access and consent before exposing
  any workout data to trainers.
- Adapt shared Routine Builder lookups to return only routines owned by
  that student and supply stable routine and exercise IDs, names and
  planned sets, repetitions and weights. Preserve historical snapshots.
- Agree the shared workout JSON path, write ownership and record schema
  before enabling other modules to write. Repository locking covers one
  process. The real prototype workout file remains Git-ignored.
- Review the proposed metrics and related SDS/UML changes with the team.
  Review the proposed replacement for Scenario 4.6 with the original SRS.
  Physical storage detection remains outside scope.

The full regression run passed 150 Python and 17 JavaScript tests.
These include student isolation, escaped dynamic chart text, safe export
outcomes with mocked browser APIs and the timestamp regression. The
actual workout storage checksum matched before and after verification.
The final group test plan belongs to Step 8.4.
