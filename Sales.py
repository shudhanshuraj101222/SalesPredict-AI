"""Compatibility entry point; run this file or app.py to start the application."""

from app import app


if __name__ == "__main__":
    app.run(debug=False)
