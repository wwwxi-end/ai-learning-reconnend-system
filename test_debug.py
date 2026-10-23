import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routes.api_v2 import api_bp
print(f"api_bp view_functions: {list(api_bp.view_functions.keys())}")

import inspect
for name, func in api_bp.view_functions.items():
    print(f"{name}: {inspect.getfile(func)}")
