from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from database.db import init_db
from routes.web import web


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SALESPREDICT_SECRET_KEY", "change-this-for-deployment"),
        DATABASE=os.environ.get(
            "SALESPREDICT_DATABASE", str(Path(app.instance_path) / "salespredict.sqlite3")
        ),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DATABASE"])
    app.register_blueprint(web)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
