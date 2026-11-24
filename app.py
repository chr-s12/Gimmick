from flask import Flask
from progress.routes import progress_bp

def create_app():
    app = Flask(__name__)

    app.register_blueprint(
        progress_bp,
        url_prefix="/progress"
    )

    return app

app = create_app()