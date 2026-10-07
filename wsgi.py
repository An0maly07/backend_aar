"""WSGI entry point: `flask run` (dev) or `waitress-serve --port=5000 wsgi:app` (Windows prod)."""
from app import create_app

app = create_app()
