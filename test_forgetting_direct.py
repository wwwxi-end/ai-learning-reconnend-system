import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from flask_login import LoginManager, UserMixin, login_user

app = Flask(__name__)
app.config.from_object('config.Config')

from models import db
db.init_app(app)

from models.learning_record import LearningRecord
from models.knowledge_point import KnowledgePoint

with app.app_context():
    student_id = 2
    
    kp_ids = [row[0] for row in db.session.query(LearningRecord.kp_id).filter(
        LearningRecord.student_id == student_id
    ).distinct().all()]
    
    print(f"Found {len(kp_ids)} knowledge points")
    
    kps = {kp.id: kp for kp in KnowledgePoint.query.filter(
        KnowledgePoint.id.in_(kp_ids)
    ).all()} if kp_ids else {}

    result = []
    for kid in kp_ids:
        kp = kps.get(kid)
        if not kp:
            continue
            
        history = LearningRecord.query.filter(
            LearningRecord.student_id == student_id,
            LearningRecord.kp_id == kid
        ).order_by(LearningRecord.updated_at.asc()).all()

        if len(history) < 2:
            continue

        dates = [r.updated_at.strftime('%m/%d') if r.updated_at else '' for r in history]
        scores = []
        for r in history:
            v_score = getattr(r, 'video_score', 0) or getattr(r, 'video_progress', 0) or 0
            t_score = getattr(r, 'text_score', 0) or getattr(r, 'text_progress', 0) or 0
            q_score = getattr(r, 'quiz_score', 0) or 0
            scores.append(round(v_score * 0.35 + t_score * 0.15 + q_score * 0.50, 2))

        n = len(scores)
        timestamps = list(range(n))
        sum_x = sum(timestamps)
        sum_y = sum(scores)
        sum_xy = sum(x * y for x, y in zip(timestamps, scores))
        sum_x2 = sum(x * x for x in timestamps)
        
        denom = n * sum_x2 - sum_x * sum_x
        slope = (n * sum_xy - sum_x * sum_y) / denom if denom != 0 else 0.0
        
        if slope >= -0.5:
            continue

        best = max(scores)
        current = scores[-1]

        result.append({
            'kp_name': kp.name,
            'kp_id': kid,
            'dates': dates,
            'scores': scores,
            'current_score': current,
            'previous_score': scores[-2] if len(scores) >= 2 else None,
            'slope': round(slope, 3),
            'best_score': best,
            'total_drop': round(best - current, 2),
            'drop_count': sum(1 for i in range(1, n) if scores[i] < scores[i-1])
        })

    result.sort(key=lambda x: x['slope'])
    print(f"\nForgetting trend result ({len(result)} items):")
    for item in result:
        print(f"  - {item['kp_name']}: slope={item['slope']}, score={item['current_score']}, drop={item['total_drop']}")
