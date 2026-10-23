import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
app = create_app()

with app.app_context():
    from services.diagnosis import detect_weak_points
    
    print("Calling detect_weak_points(16)...")
    try:
        result = detect_weak_points(16)
        print("Success!")
        print(f"forgetting_trend count: {len(result.get('forgetting_trend', []))}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
