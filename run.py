from dotenv import load_dotenv
load_dotenv()

import os
from app import create_app

os.environ.setdefault("APP_NAME", os.getenv("APP_NAME", "Compugit_Python_REST_API"))
os.environ.setdefault("VERSION", os.getenv("VERSION", open("./VERSION").read().strip()))

if __name__ == '__main__':
    app = create_app()
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', '5000')),
        debug=os.getenv('DEBUG', 'False').lower() in {'true', '1', 'yes', 'on'},
    )