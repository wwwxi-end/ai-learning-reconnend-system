import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routes.api_new import api_bp
import inspect

func = api_bp.view_functions['forgetting_trend']
print(f"forgetting_trend source: {inspect.getfile(func)}")
print(f"forgetting_trend code:")
print(inspect.getsource(func))
