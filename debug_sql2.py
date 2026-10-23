import sys
sys.path.insert(0, '.')

from app import create_app
from models import db
from models.learning_record import LearningRecord
from services.diagnosis import detect_weak_points, get_forgetting_slope

app = create_app()

with app.app_context():
    print("Testing detect_weak_points...")
    try:
        result = detect_weak_points(16)
        print(f"Success! Keys: {result.keys()}")
        print(f"forgetting_trend count: {len(result.get('forgetting_trend', []))}")
    except Exception as e:
        print(f"Error: {e}")
        
    print("\n\nTesting get_forgetting_slope...")
    try:
        slope = get_forgetting_slope(16, 1)
        print(f"Success! Result: {slope}")
    except Exception as e:
        print(f"Error: {e}")
