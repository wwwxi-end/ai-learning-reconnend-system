import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
app = create_app()

with app.app_context():
    from models.learning_record import LearningRecord
    from sqlalchemy import select
    
    stmt1 = select(LearningRecord).filter(LearningRecord.quiz_score.isnot(None))
    print(f"isnot(None): {stmt1.compile()}")
    
    stmt2 = select(LearningRecord).filter(LearningRecord.quiz_score != None)
    print(f"!= None: {stmt2.compile()}")
    
    stmt3 = select(LearningRecord).filter(LearningRecord.quiz_score.is_not(None))
    print(f"is_not(None): {stmt3.compile()}")
    
    stmt4 = select(LearningRecord).filter(LearningRecord.quiz_score.isnot(None)).order_by(LearningRecord.created_at.asc())
    print(f"isnot(None) + order_by: {stmt4.compile()}")
    
    stmt5 = select(LearningRecord).filter(LearningRecord.quiz_score.isnot(None)).order_by(LearningRecord.kp_id, LearningRecord.updated_at)
    print(f"isnot(None) + order_by kp_id, updated_at: {stmt5.compile()}")
