from .main import app

# Support `uvicorn app:main` by exposing the ASGI app under both names.
main = app
