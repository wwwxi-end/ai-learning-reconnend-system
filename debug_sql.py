import sys
sys.path.insert(0, '.')

from app import create_app
from flask import current_app
from models import db
from models.learning_record import LearningRecord

app = create_app()

with app.app_context():
    queries = [
        "get_forgetting_slope",
        LearningRecord.query.filter(
            LearningRecord.student_id == 16,
            LearningRecord.kp_id == 1
        ).order_by(LearningRecord.updated_at),
        
        "detect_weak_points subquery",
        db.session.query(
            LearningRecord.kp_id,
            db.func.max(LearningRecord.id).label('max_id')
        ).filter_by(student_id=16).group_by(LearningRecord.kp_id),
        
        "all records for student",
        LearningRecord.query.filter_by(student_id=16),
        
        "with quiz_score filter",
        LearningRecord.query.filter_by(student_id=16).filter(LearningRecord.quiz_score != None),
    ]
    
    for i, item in enumerate(queries):
        if isinstance(item, str):
            print(f"\n{'='*50}")
            print(f"Query: {item}")
            print(f"{'='*50}")
        else:
            try:
                stmt = item.statement if hasattr(item, 'statement') else item
                sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
                print(f"\nQuery {i}:")
                print(sql)
            except Exception as e:
                print(f"\nQuery {i} error: {e}")
