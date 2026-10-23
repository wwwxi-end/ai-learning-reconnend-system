from sqlalchemy import create_engine, select, Column, Integer, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class LearningRecord(Base):
    __tablename__ = 'learning_records'
    id = Column(Integer, primary_key=True)
    quiz_score = Column(Float)

engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)

with engine.connect() as conn:
    stmt = select(LearningRecord).filter(LearningRecord.quiz_score.is_not(None))
    print(f"SQL (is_not): {stmt.compile()}")
    
    stmt2 = select(LearningRecord).filter(LearningRecord.quiz_score != None)
    print(f"SQL (!= None): {stmt2.compile()}")
    
    stmt3 = select(LearningRecord).filter(LearningRecord.quiz_score.isnot(None))
    print(f"SQL (isnot): {stmt3.compile()}")
