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

Open [My Progress](http://127.0.0.1:5000/progress/) to select a saved routine
and log a completed workout. A successful save opens the workout summary.
Workout History lists that student's saved workouts, newest first.

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

- The Jinja templates collect completed exercise values and display saved records.
- The Flask Blueprint handles requests, status codes, and navigation.
- `ProgressService` validates completed workouts and orders saved history.
- `WorkoutLogRepository` manages JSON reads, ownership-scoped lookups, and atomic writes.
- `WorkoutLog` and `LoggedExercise` represent and serialise workout snapshots.

Logging, saving, the summary, and workout history are implemented. Analytics,
charts, and downloads are planned work.

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
