from flask import Flask, render_template, request, redirect, url_for, jsonify,flash, session  
from progress.repository import WorkoutLogRepository
from progress.routes import progress_bp
from progress.service import ProgressService
from Student import Student
from Routine import Routine
from Exercise import Exercise
import os
from Trainer import Trainer


# Load or initialize a default Student user for testing
def get_current_user(user_id: str = "620150001") -> Student:
    user = Student.loadUser(user_id)
    if user is None:
        user = Student("Khairy", user_id)
        user.userSave()
    return user

def get_current_trainer(trainer_id: str = "T001") -> Trainer:
    active_id = session.get("trainer_id", trainer_id)
    trainer = Trainer.loadUser(active_id)
    if trainer is None:
        trainer = Trainer("Coach Devon", active_id)
        trainer.userSave()
    return trainer


def create_app(config=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-gimmick")
    if config is not None:
        app.config.update(config)

    # Initialize Progress tracking extension & blueprint
    storage_path = app.config.get("WORKOUT_STORAGE_PATH")
    repository = (
        WorkoutLogRepository() if storage_path is None else WorkoutLogRepository(storage_path)
    )
    app.extensions["progress_service"] = ProgressService(repository)
    app.register_blueprint(progress_bp, url_prefix="/progress")

    # Dashboard & Routine Routes
    @app.route("/")
    def index():
        user = get_current_user()
        public_routines = Routine.getPublicRoutines()
        return render_template(
            "member_dash.html",
            user=user,
            my_routines=user._routine_list,
            public_routines=public_routines,
            common_exercises=Exercise.getCommonExercises(),
        )

    @app.route("/create-routine", methods=["POST"])
    def create_routine():
        user = get_current_user()
        routine_name = (request.form.get("routine_name") or "").strip()
        is_public = request.form.get("is_public") == "on"

        if not routine_name:
            flash("Routine name cannot be empty.", "error")
            return redirect(url_for("index"))

        names = request.form.getlist("excer_name")
        sets = request.form.getlist("num_sets")
        reps = request.form.getlist("num_reps")
        rests = request.form.getlist("rest_time")
        weights = request.form.getlist("weight_kg")

        exercises = []
        for i in range(len(names)):
            excer_name = names[i].strip()
            if not excer_name:
                continue  # Skip blank rows

            try:
                num_sets = int(sets[i])
                num_reps = int(reps[i])
                rest_time = int(rests[i] or 0)
                weight_kg = float(weights[i] or 0)
            except (ValueError, IndexError):
                flash(f"Invalid numeric values for exercise '{excer_name}'.", "error")
                return redirect(url_for("index"))

            if num_sets <= 0 or num_reps <= 0 or rest_time < 0 or weight_kg < 0:
                flash(f"Sets and reps must be positive, and rest/weight cannot be negative for '{excer_name}'.", "error")
                return redirect(url_for("index"))

            exercises.append(Exercise(
                excer_name=excer_name,
                num_sets=num_sets,
                num_reps=num_reps,
                rest_time=rest_time,
                weight_kg=weight_kg
            ))

        if not exercises:
            flash("Add at least one valid exercise to create a routine.", "error")
            return redirect(url_for("index"))

        user.buildRoutine(routine_name, exercises, is_public)
        return redirect(url_for("index"))

    @app.route("/edit-routine/<routine_id>", methods=["GET", "POST"])
    def edit_routine(routine_id):
        user = get_current_user()
        routine = user.getRoutineById(routine_id)

        if routine is None:
            return "Routine not Found", 404

        if request.method == "POST":
            new_name = (request.form.get("routine_name") or "").strip()
            new_public = request.form.get("is_public") == "on"

            if not new_name:
                flash("Routine name cannot be empty.", "error")
                return render_template("edit_routine.html", routine=routine)

            user.editRoutine(routine, routineName=new_name, isPublic=new_public)
            return redirect(url_for("index"))

        return render_template("edit_routine.html", routine=routine)

    @app.route("/delete-routine/<routine_id>", methods=["POST"])
    def delete_routine(routine_id):
        user = get_current_user()
        routine = user.getRoutineById(routine_id)
        if routine:
            user.deleteRoutine(routine)
        return redirect(url_for("index"))

    @app.route("/adopt-routine/<routine_id>", methods=["POST"])
    def adopt_routine(routine_id):
        user = get_current_user()
        public_routines = Routine.getPublicRoutines()
        routine = next(
            (r for r in public_routines if str(r.getRoutineId()) == str(routine_id)),
            None
        )
        if routine:
            user.adoptRoutine(routine)
        return redirect(url_for("index"))

    @app.route("/assign-routine", methods=["POST"])
    def assign_routine():
        trainer = get_current_trainer()  # Replace with your active Trainer loader
        student_id = (request.form.get("student_id") or "").strip()
        routine_id = (request.form.get("routine_id") or "").strip()

        if not student_id or not routine_id:
            flash("Please select both a student and a routine.", "error")
            return redirect(url_for("trainer_dash"))

        stu = Student.loadUser(student_id)
        if stu is None:
            flash(f"Student '{student_id}' could not be found.", "error")
            return redirect(url_for("trainer_dash"))

        routine = trainer.getRoutineById(routine_id)
        if routine is None:
            flash("Selected routine could not be found.", "error")
            return redirect(url_for("trainer_dash"))

        if not any(str(c.getIdNum()) == str(stu.getIdNum()) for c in trainer._client_list):
            flash(f"{stu.getUsername()} is not on your client list.", "error")
            return redirect(url_for("trainer_dash"))

        if any(str(r.getRoutineId()) == str(routine.getRoutineId()) for r in stu._routine_list):
            flash(f"{stu.getUsername()} already has '{routine.getRoutineName()}'.", "error")
            return redirect(url_for("trainer_dash"))

        if trainer.assignRoutine(routine, stu):
            flash(f"Assigned '{routine.getRoutineName()}' to {stu.getUsername()}!", "success")
        else:
            flash("Could not assign routine due to an unexpected error.", "error")

        return redirect(url_for("trainer_dash"))
    return app

    


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)