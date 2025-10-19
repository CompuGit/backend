from dotenv import load_dotenv
# Load environment variables
load_dotenv()

from app import app
from app.applogger import logger
import os
import sys

if __name__ == '__main__':
    logger.info("Starting Backend app ...")
    
    if (len(sys.argv) > 1 and sys.argv[1] == '--prod') or os.getenv('ENV') == 'prod':
        # Production mode with Gunicorn
        from gunicorn.app.base import BaseApplication

        class GunicornApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key, value)

            def load(self):
                return self.application

        options = {
            'bind': f"{os.getenv('HOST','0.0.0.0')}:{os.getenv('PORT','5000')}",
            'workers': 3,
            'worker_class': 'sync',
            'timeout': 30
        }
        GunicornApplication(app, options).run()
    else:
        # Development mode with Flask
        app.run(
            host=os.getenv('HOST','0.0.0.0'), 
            port=int(os.getenv('PORT',5000)), 
            debug=eval(os.getenv('DEBUG','False').title())
        )

'''
api auth -done
logger -done
env -done
routes
swagger
gunicorn
dockerfile
structured dir / modular

'''