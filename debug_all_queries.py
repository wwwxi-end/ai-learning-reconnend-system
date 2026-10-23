import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
app = create_app()

with app.app_context():
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    
    all_queries = []
    
    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        all_queries.append({
            'sql': statement,
            'params': parameters
        })
    
    from services.diagnosis import detect_weak_points
    result = detect_weak_points(16)
    
    print("\n" + "="*80)
    print("ALL EXECUTED QUERIES:")
    print("="*80)
    for i, q in enumerate(all_queries):
        print(f"\nQuery {i+1}:")
        print(f"SQL: {q['sql'][:200]}...")
        if 'not(NULL)' in q['sql']:
            print("  *** PROBLEMATIC QUERY FOUND! ***")
            print(f"Full SQL: {q['sql']}")
            print(f"Params: {q['params']}")
