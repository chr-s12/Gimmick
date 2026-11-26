from flask import Flask, render_template, request, redirect, url_for, jsonify
from progress.repository import WorkoutLogRepository
from progress.routes import progress_bp
from progress.service import ProgressService
from Student import Student
from Routine import Routine
from Exercise import Exercise


# Load or initialize a default Student user for testing
def get_current_user(user_id: str = "620150001") -> Student:
    user = Student.loadUser(user_id)
    if user is None:
        user = Student("Khairy", user_id)
        user.userSave()
    return user


def create_app(config=None):
    app = Flask(__name__)
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
            public_routines=public_routines
        )

    @app.route("/create-routine", methods=["POST"])
    def create_routine():
        user = get_current_user()
        routine_name = request.form.get("routine_name")
        is_public = request.form.get("is_public") == "on"

        names = request.form.getlist("excer_name")
        sets = request.form.getlist("num_sets")
        reps = request.form.getlist("num_reps")
        rests = request.form.getlist("rest_time")
        weights = request.form.getlist("weight_kg")

        exercises = []
        for i in range(len(names)):
            if names[i].strip():  # Skip blank rows
                exercises.append(Exercise(
                    excer_name=names[i],
                    num_sets=int(sets[i]),
                    num_reps=int(reps[i]),
                    rest_time=int(rests[i]),
                    weight_kg=int(weights[i])
                ))

        if exercises:
            user.buildRoutine(routine_name, exercises, is_public)

        return redirect(url_for("index"))

    @app.route("/edit-routine/<routine_id>", methods=["GET", "POST"])
    def edit_routine(routine_id):
        user = get_current_user()
        routine = user.getRoutineById(routine_id)

        if routine is None:
            return "Routine not Found", 404

        if request.method == "POST":
            new_name = request.form.get("routine_name")
            new_public = request.form.get("is_public") == "on"
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
        routine = Routine.getRoutineById(routine_id)
        if routine and routine.getIsPublic():
            user.adoptRoutine(routine)
        return redirect(url_for("index"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)