import os
from dotenv import load_dotenv

load_dotenv()
print(f"FLASK_DEBUG: {os.environ.get('FLASK_DEBUG')}")
print(f"DEBUG value: {os.environ.get('FLASK_DEBUG') == 'True'}")
