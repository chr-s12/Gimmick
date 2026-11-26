from flask import Flask, render_template, request, redirect, url_for, jsonify
from Student import Student
from Routine import Routine
from Exercise import Exercise

app = Flask(__name__)

# Load or initialize a default Student user for testing
def get_current_user(user_id: str = "620150001") -> Student:
    user = Student.loadUser(user_id)
    if user is None:
        user = Student("Khairy", user_id)
        user.userSave()
    return user


@app.route("/")
def index():
    user = get_current_user()
    public_routines = Routine.getPublicRoutines()
    # Replace "index.html" with the exact filename inside your templates/ folder
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
  
    # If the user clicked "Save Changes"
    if request.method == "POST":
        new_name = request.form.get("routine_name")
        new_public = request.form.get("is_public") == "on"
        user.editRoutine(routine, routineName=new_name, isPublic=new_public)
        return redirect(url_for("index"))

    # If the user just clicked "Edit" to open the page and does not savev(GET):
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
    

if __name__ == "__main__":
    app.run(debug=True)