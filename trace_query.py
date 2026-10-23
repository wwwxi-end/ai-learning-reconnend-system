import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
app = create_app()

with app.app_context():
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    
    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if 'quiz_score' in statement and 'not(NULL)' in statement:
            print("\n" + "="*100)
            print("PROBLEMATIC QUERY DETECTED!")
            print("="*100)
            print(f"SQL: {statement}")
            print(f"Parameters: {parameters}")
            import traceback
            traceback.print_stack()
            print("="*100 + "\n")
    
    from services.diagnosis import detect_weak_points
    result = detect_weak_points(16)
    print(f"Result keys: {list(result.keys())}")
    print(f"Forgeting trend count: {len(result.get('forgetting_trend', []))}")
