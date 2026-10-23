# services/diagnosis.py - 多维度薄弱点检测服务
from datetime import datetime
from sqlalchemy import func, text as sql_text
from models import db
from models.knowledge_point import KnowledgePoint
from models.learning_record import LearningRecord
from models.prerequisite import WeakPointRecord, Prerequisite
from config import Config
from models.user import User
from extensions import cache
from utils.helpers import format_score


def calculate_weighted_score(record):
    weights = {
        'video': 0.35,
        'text': 0.15,
        'quiz': 0.50
    }
    
    video_score = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0.0
    
    text_score_val = 0.0
    text_total_length = getattr(record, 'text_total_length', 0) or 0
    if text_total_length > 0:
        text_score_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0.0
    else:
        text_read_duration = getattr(record, 'text_read_duration', 0) or 0
        if text_read_duration > 0:
            text_score_val = min(100, text_read_duration / 300 * 100)
    
    quiz_score = getattr(record, 'quiz_score', 0) or 0.0
    
    weighted_score = (video_score * weights['video'] + 
                      text_score_val * weights['text'] + 
                      quiz_score * weights['quiz'])
    
    return round(weighted_score, 2)


def clear_student_weak_cache(student_id):
    WeakPointRecord.query.filter_by(student_id=student_id).delete()


def calc_student_avg_score(student_id):
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=student_id).group_by(LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    if not records:
        return 0.0
    
    total_score = 0.0
    for record in records:
        video = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
        t_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
        quiz = getattr(record, 'quiz_score', 0) or 0
        total_score += round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2)
    avg_score = total_score / len(records)
    
    return round(avg_score, 2)


def get_kp_block_counts(kp_id):
    count = Prerequisite.query.filter(
        Prerequisite.prerequisite_kp_id == kp_id,
        Prerequisite.relation_type == 'must'
    ).count()
    return count


def get_forgetting_slope(student_id, kp_id):
    rows = db.session.execute(
        sql_text("SELECT * FROM learning_records WHERE student_id = :student_id AND kp_id = :kp_id ORDER BY updated_at ASC"),
        {'student_id': student_id, 'kp_id': kp_id}
    ).fetchall()
    
    records = []
    for row in rows:
        record = LearningRecord()
        for k, v in dict(row._mapping).items():
            setattr(record, k, v)
        records.append(record)
    
    if len(records) < 2:
        return None, None, None, len(records), 0.0, 0
    
    scores = []
    timestamps = []
    for i, record in enumerate(records):
        video = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
        t_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
        quiz = getattr(record, 'quiz_score', 0) or 0
        ws = round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2)
        scores.append(ws)
        timestamps.append(i)
    
    n = len(scores)
    if n < 2:
        return None, None, None, n, 0.0, 0
    
    sum_x = sum(timestamps)
    sum_y = sum(scores)
    sum_xy = sum(x * y for x, y in zip(timestamps, scores))
    sum_x2 = sum(x * x for x in timestamps)
    
    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        best_score = max(scores)
        current_score = scores[-1]
        total_drop = round(best_score - current_score, 2)
        drop_count = sum(1 for i in range(1, n) if scores[i] < scores[i-1])
        return 0.0, best_score, current_score, n, total_drop, drop_count
    
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    
    best_score = max(scores)
    current_score = scores[-1]
    total_drop = round(best_score - current_score, 2)
    drop_count = sum(1 for i in range(1, n) if scores[i] < scores[i-1])
    
    return round(slope, 3), best_score, current_score, n, total_drop, drop_count


def detect_weak_points(student_id):
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=student_id).group_by(LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    kp_ids = [r.kp_id for r in records]
    kps = {kp.id: kp for kp in KnowledgePoint.query.filter(
        KnowledgePoint.id.in_(kp_ids)
    ).all()} if kp_ids else {}
    
    personal_avg = calc_student_avg_score(student_id) or 0.0
    relative_threshold = personal_avg * 0.8
    
    result = {
        'summary': {
            'detected_at': datetime.now().isoformat(),
            'total_kps_studied': len(records),
            'personal_avg': personal_avg
        },
        'absolute_weak': [],
        'relative_weak': [],
        'high_risk_weak': [],
        'forgetting_trend': []
    }
    
    for record in records:
        kp_id = record.kp_id
        kp = kps.get(kp_id)
        if not kp:
            continue
        
        video = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
        t_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
        quiz = getattr(record, 'quiz_score', 0) or 0
        score = round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2)
        
        if score < 60:
            result['absolute_weak'].append({
                'kp_id': kp_id,
                'kp_name': kp.name,
                'score': score,
                'gap': round(60 - score, 1),
                'chapter': kp.chapter,
                'chapter_order': kp.chapter_order
            })
        
        if personal_avg > 0 and score < relative_threshold:
            gap_ratio = round((personal_avg - score) / personal_avg * 100, 1)
            result['relative_weak'].append({
                'kp_id': kp_id,
                'kp_name': kp.name,
                'score': score,
                'gap_ratio': gap_ratio,
                'chapter': kp.chapter,
                'chapter_order': kp.chapter_order
            })
        
        if score < 60:
            blocks_count = get_kp_block_counts(kp_id)
            if blocks_count > 0:
                result['high_risk_weak'].append({
                    'kp_id': kp_id,
                    'kp_name': kp.name,
                    'score': score,
                    'blocks_count': blocks_count,
                    'chapter': kp.chapter,
                    'chapter_order': kp.chapter_order
                })
        
        slope, best_score, current_score, attempts, total_drop, drop_count = get_forgetting_slope(student_id, kp_id)
        if slope is not None and attempts >= 2 and slope < -0.5:
            result['forgetting_trend'].append({
                'kp_id': kp_id,
                'kp_name': kp.name,
                'score': current_score,
                'best_score': best_score,
                'slope': slope,
                'attempts': attempts,
                'total_drop': total_drop,
                'drop_count': drop_count,
                'chapter': kp.chapter,
                'chapter_order': kp.chapter_order
            })
    
    result['absolute_weak'].sort(key=lambda x: x['score'])
    result['relative_weak'].sort(key=lambda x: x['score'])
    result['high_risk_weak'].sort(key=lambda x: (-x['blocks_count'], x['score']))
    result['forgetting_trend'].sort(key=lambda x: x['slope'])
    
    return result


def detect_weak_points_with_db_write(student_id):
    weak_analysis = detect_weak_points(student_id)
    
    clear_student_weak_cache(student_id)
    
    all_weak = []
    for item in weak_analysis['absolute_weak']:
        all_weak.append((item['kp_id'], 'absolute'))
    for item in weak_analysis['relative_weak']:
        all_weak.append((item['kp_id'], 'relative'))
    for item in weak_analysis['high_risk_weak']:
        all_weak.append((item['kp_id'], 'high_risk'))
    for item in weak_analysis['forgetting_trend']:
        all_weak.append((item['kp_id'], 'forgetting'))
    
    for kp_id, weak_type in all_weak:
        record = WeakPointRecord(
            student_id=student_id,
            kp_id=kp_id,
            weak_type=weak_type,
            detected_at=datetime.now()
        )
        db.session.add(record)
    
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    return weak_analysis


def get_ai_weak_analysis(student_id, weak_analysis=None):
    from services.llm_service import llm_service
    if weak_analysis is None:
        weak_analysis = detect_weak_points(student_id)
    return llm_service.analyze_weak_points(
        student_id=student_id,
        personal_avg=weak_analysis.get('summary', {}).get('personal_avg', 0),
        absolute_weak=weak_analysis.get('absolute_weak', []),
        relative_weak=weak_analysis.get('relative_weak', []),
        high_risk_weak=weak_analysis.get('high_risk_weak', []),
        forgetting_trend=weak_analysis.get('forgetting_trend', [])
    )


def get_class_weak_analysis(teacher_id=None):
    subq = db.session.query(
        LearningRecord.student_id,
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).group_by(LearningRecord.student_id, LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    kp_stats = {}
    for record in records:
        kp_id = record.kp_id
        if kp_id not in kp_stats:
            kp_stats[kp_id] = {'scores': [], 'weak_count': 0}
        video = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
        t_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
        quiz = getattr(record, 'quiz_score', 0) or 0
        score = round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2)
        kp_stats[kp_id]['scores'].append(score)
        if score < 60:
            kp_stats[kp_id]['weak_count'] += 1
    
    kps = {kp.id: kp for kp in KnowledgePoint.query.filter(
        KnowledgePoint.id.in_(list(kp_stats.keys()))
    ).all()}
    
    result = []
    for kp_id, stats in kp_stats.items():
        kp = kps.get(kp_id)
        if not kp:
            continue
        scores = stats['scores']
        avg_score = sum(scores) / len(scores) if scores else 0
        result.append({
            'kp_id': kp_id,
            'kp_name': kp.name,
            'chapter': kp.chapter,
            'avg_score': round(avg_score, 1),
            'student_count': len(scores),
            'weak_count': stats['weak_count'],
            'weak_rate': round(stats['weak_count'] / len(scores) * 100, 1) if scores else 0
        })
    
    result.sort(key=lambda x: x['avg_score'])
    return result


def get_chapter_radar_data(student_id):
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=student_id).group_by(LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    kp_ids = [r.kp_id for r in records]
    kps = {kp.id: kp for kp in KnowledgePoint.query.filter(
        KnowledgePoint.id.in_(kp_ids)
    ).all()} if kp_ids else {}
    
    chapter_scores = {}
    for record in records:
        kp = kps.get(record.kp_id)
        if not kp:
            continue
        chapter = kp.chapter
        if chapter not in chapter_scores:
            chapter_scores[chapter] = []
        video = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
        t_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
        quiz = getattr(record, 'quiz_score', 0) or 0
        score = round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2)
        chapter_scores[chapter].append(score)
    
    result = []
    for chapter, scores in chapter_scores.items():
        avg_score = sum(scores) / len(scores) if scores else 0
        result.append({
            'chapter': chapter,
            'avg_score': round(avg_score, 1),
            'kp_count': len(scores)
        })
    
    return result


def get_score_distribution(student_id):
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=student_id).group_by(LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    scores = []
    for r in records:
        video = getattr(r, 'video_score', 0) or getattr(r, 'video_progress', 0) or 0
        t_val = getattr(r, 'text_score', 0) or getattr(r, 'text_progress', 0) or 0
        quiz = getattr(r, 'quiz_score', 0) or 0
        scores.append(round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2))
    
    distribution = {
        '0-40': 0,
        '40-60': 0,
        '60-80': 0,
        '80-100': 0
    }
    
    for score in scores:
        if score < 40:
            distribution['0-40'] += 1
        elif score < 60:
            distribution['40-60'] += 1
        elif score < 80:
            distribution['60-80'] += 1
        else:
            distribution['80-100'] += 1
    
    return distribution


def get_kp_mastery_dict(student_id):
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=student_id).group_by(LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    result = {}
    for r in records:
        video = getattr(r, 'video_score', 0) or getattr(r, 'video_progress', 0) or 0
        t_val = getattr(r, 'text_score', 0) or getattr(r, 'text_progress', 0) or 0
        quiz = getattr(r, 'quiz_score', 0) or 0
        result[r.kp_id] = round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2)
    return result


def get_forgetting_trend_data(student_id):
    from sqlalchemy import text
    
    kp_ids = db.session.query(LearningRecord.kp_id).filter_by(
        student_id=student_id
    ).distinct().all()
    kp_ids = [row[0] for row in kp_ids]
    
    if not kp_ids:
        return []
    
    kps = {kp.id: kp for kp in KnowledgePoint.query.filter(
        KnowledgePoint.id.in_(kp_ids)
    ).all()}
    
    result = []
    for kp_id in kp_ids:
        kp = kps.get(kp_id)
        if not kp:
            continue
        
        rows = db.session.execute(
            text("SELECT * FROM learning_records WHERE student_id = :student_id AND kp_id = :kp_id ORDER BY updated_at ASC"),
            {'student_id': student_id, 'kp_id': kp_id}
        ).fetchall()
        
        scores = []
        dates = []
        for row in rows:
            record = LearningRecord()
            for col, val in dict(row._mapping).items():
                setattr(record, col, val)
            
            video = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
            t_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
            quiz = getattr(record, 'quiz_score', 0) or 0
            ws = round(video * 0.35 + t_val * 0.15 + quiz * 0.50, 2)
            scores.append(ws)
            
            updated_at = getattr(record, 'updated_at', getattr(record, 'created_at', None))
            if updated_at:
                if isinstance(updated_at, str):
                    dates.append(updated_at[:10])
                else:
                    dates.append(updated_at.strftime('%Y-%m-%d'))
            else:
                dates.append(f'第{len(dates)+1}次')
        
        if len(scores) < 2:
            continue
        
        slope, best_score, current_score, attempts, total_drop, drop_count = get_forgetting_slope(student_id, kp_id)
        if slope is not None and slope < -0.5:
            result.append({
                'kp_id': kp_id,
                'kp_name': kp.name,
                'chapter': kp.chapter,
                'scores': scores,
                'dates': dates,
                'current_score': current_score,
                'best_score': best_score,
                'slope': slope,
                'attempts': attempts,
                'total_drop': total_drop,
                'drop_count': drop_count
            })
    
    result.sort(key=lambda x: x['slope'])
    return result


def get_all_forgetting_slopes(student_id):
    records = LearningRecord.query.filter_by(student_id=student_id).all()
    kp_ids = set([r.kp_id for r in records])
    
    result = {}
    for kp_id in kp_ids:
        slope, best_score, current_score, attempts, total_drop, drop_count = get_forgetting_slope(student_id, kp_id)
        if slope is not None:
            result[kp_id] = {
                'slope': slope,
                'best_score': best_score,
                'current_score': current_score,
                'attempts': attempts,
                'total_drop': total_drop,
                'drop_count': drop_count
            }
    
    return result
