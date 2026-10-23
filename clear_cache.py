import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
app = create_app()

with app.app_context():
    from extensions import cache
    cache.clear()
    print("Cache cleared successfully")
