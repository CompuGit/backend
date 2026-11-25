from dotenv import load_dotenv

load_dotenv()

import os
from pathlib import Path

from app import create_app

os.environ.setdefault("APP_NAME", os.getenv("APP_NAME", "Compugit_Python_REST_API"))
version_file = Path(__file__).with_name("VERSION")
os.environ.setdefault("VERSION", os.getenv("VERSION", version_file.read_text().strip()))

if __name__ == "__main__":
    app = create_app()
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("DEBUG", "False").lower() in {"true", "1", "yes", "on"},
    )