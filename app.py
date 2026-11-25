from flask import Flask
from progress.repository import WorkoutLogRepository
from progress.routes import progress_bp
from progress.service import ProgressService

def create_app(config=None):
    app = Flask(__name__)
    if config is not None:
        app.config.update(config)

    storage_path = app.config.get("WORKOUT_STORAGE_PATH")
    repository = (
        WorkoutLogRepository() if storage_path is None else WorkoutLogRepository(storage_path)
    )
    app.extensions["progress_service"] = ProgressService(repository)

    app.register_blueprint(
        progress_bp,
        url_prefix="/progress"
    )

    return app

app = create_app()