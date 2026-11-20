import os
from . import db, seed
from .api import create_app

path = os.environ.get("CAMPUS_DB_PATH", "campus.db")
c = db.connect(path)
db.migrate(c)
seed.seed(c)
c.close()
app = create_app()
if __name__ == "__main__":
    app.run(host=os.environ.get("BIND_HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8000)))
