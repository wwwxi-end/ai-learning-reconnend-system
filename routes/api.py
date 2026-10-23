from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import db
from models.knowledge_point import KnowledgePoint
from models.learning_record import LearningRecord
from models.prerequisite import Prerequisite
from services.diagnosis import (
    get_chapter_radar_data,
    get_score_distribution,
    get_forgetting_trend_data,
    detect_weak_points,
    calculate_weighted_score
)
from services.recommendation import get_learning_path_for_kp
from services.neo4j_service import neo4j_service
from sqlalchemy import func

api_bp = Blueprint('api', __name__)


def get_student_id():
    student_id = current_user.id
    if request.args.get('student_id') and current_user.role in ('teacher', 'admin'):
        student_id = request.args.get('student_id', type=int)
    return student_id


@api_bp.route('/student/dashboard_stats')
@login_required
def dashboard_stats():
    student_id = get_student_id()
    
    records = LearningRecord.query.filter(
        LearningRecord.student_id == student_id
    ).all()

    kp_ids = set()
    weak_count = 0
    mastered_count = 0
    partial_count = 0
    scores = []

    for record in records:
        kp_ids.add(record.kp_id)
        ws_val = calculate_weighted_score(record)
        scores.append(ws_val)

        if ws_val >= 80:
            mastered_count += 1
        elif ws_val >= 60:
            partial_count += 1
        else:
            weak_count += 1

    total_kps = KnowledgePoint.query.filter_by(is_active=True).count()
    studied_kps = len(kp_ids)
    unlearned_kps = total_kps - studied_kps

    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    progress_percent = round(studied_kps / total_kps * 100, 1) if total_kps > 0 else 0

    return jsonify({
        'total_kps': total_kps,
        'studied': studied_kps,
        'unlearned': unlearned_kps,
        'mastered': mastered_count,
        'partial': partial_count,
        'weak': weak_count,
        'avg_score': avg_score,
        'progress_percent': progress_percent
    })


@api_bp.route('/student/chapter_radar')
@login_required
def chapter_radar():
    student_id = get_student_id()
    data = get_chapter_radar_data(student_id)
    
    indicators = []
    values = []
    for item in data:
        indicators.append({
            'name': item['chapter'],
            'max': 100
        })
        values.append(item['avg_score'])
    
    return jsonify({
        'indicators': indicators,
        'values': values
    })


@api_bp.route('/student/score_distribution')
@login_required
def score_distribution():
    student_id = get_student_id()
    distribution = get_score_distribution(student_id)
    
    categories = ['0-40', '40-60', '60-80', '80-100']
    values = [
        distribution['0-40'],
        distribution['40-60'],
        distribution['60-80'],
        distribution['80-100']
    ]
    colors = ['#ef4444', '#f59e0b', '#22c55e', '#10b981']
    
    return jsonify({
        'categories': categories,
        'values': values,
        'colors': colors
    })


@api_bp.route('/student/forgetting_trend')
@login_required
def forgetting_trend():
    student_id = get_student_id()
    data = get_forgetting_trend_data(student_id)
    
    result = []
    for item in data:
        kp = KnowledgePoint.query.get(item.get('kp_id'))
        result.append({
            'kp_id': item['kp_id'],
            'kp_name': kp.name if kp else f'知识点{item["kp_id"]}',
            'chapter': kp.chapter if kp else '',
            'slope': item.get('slope'),
            'scores': item.get('scores', []),
            'dates': item.get('dates', []),
            'best_score': item.get('best_score'),
            'score': item.get('score'),
            'attempts': item.get('attempts')
        })
    
    return jsonify(result)


@api_bp.route('/graph/colored')
@login_required
def graph_colored():
    student_id = get_student_id()
    
    all_kps = KnowledgePoint.query.filter_by(is_active=True).all()
    kp_dict = {kp.id: kp for kp in all_kps}
    
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=student_id).group_by(LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    score_map = {}
    for r in records:
        score_map[r.kp_id] = calculate_weighted_score(r)
    
    prereqs = Prerequisite.query.all()
    
    nodes = []
    for kp in all_kps:
        score = score_map.get(kp.id)
        if score is None:
            status = 'unlearned'
            color = '#d9d9d9'
        elif score >= 60:
            status = 'mastered'
            color = '#52c41a'
        elif score >= 40:
            status = 'partial'
            color = '#faad14'
        else:
            status = 'weak'
            color = '#ff4d4f'
        
        nodes.append({
            'id': kp.id,
            'name': kp.name,
            'chapter': kp.chapter,
            'difficulty': kp.difficulty,
            'importance': kp.importance,
            'score': score,
            'status': status,
            'color': color
        })
    
    edges = []
    for p in prereqs:
        if p.prerequisite_kp_id in kp_dict and p.target_kp_id in kp_dict:
            edges.append({
                'source': p.prerequisite_kp_id,
                'target': p.target_kp_id,
                'relation_type': p.relation_type
            })
    
    return jsonify({
        'nodes': nodes,
        'edges': edges
    })


@api_bp.route('/graph/class_colored')
@login_required
def graph_class_colored():
    all_kps = KnowledgePoint.query.filter_by(is_active=True).all()
    kp_dict = {kp.id: kp for kp in all_kps}
    
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).group_by(LearningRecord.student_id, LearningRecord.kp_id).subquery()
    
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    
    kp_stats = {}
    for r in records:
        if r.kp_id not in kp_stats:
            kp_stats[r.kp_id] = {'scores': [], 'student_count': 0}
        score = calculate_weighted_score(r)
        kp_stats[r.kp_id]['scores'].append(score)
        kp_stats[r.kp_id]['student_count'] += 1
    
    prereqs = Prerequisite.query.all()
    
    nodes = []
    for kp in all_kps:
        stats = kp_stats.get(kp.id)
        if stats and stats['scores']:
            avg_score = sum(stats['scores']) / len(stats['scores'])
            student_count = stats['student_count']
            weak_count = sum(1 for s in stats['scores'] if s < 60)
            fail_rate = round(weak_count / len(stats['scores']) * 100, 1) if stats['scores'] else 0
        else:
            avg_score = None
            student_count = 0
            fail_rate = 0
        
        if avg_score is None:
            status = 'unlearned'
            color = '#d9d9d9'
        elif avg_score >= 60:
            status = 'mastered'
            color = '#52c41a'
        elif avg_score >= 40:
            status = 'partial'
            color = '#faad14'
        else:
            status = 'weak'
            color = '#ff4d4f'
        
        nodes.append({
            'id': kp.id,
            'name': kp.name,
            'chapter': kp.chapter,
            'difficulty': kp.difficulty,
            'importance': kp.importance,
            'score': round(avg_score, 1) if avg_score is not None else None,
            'status': status,
            'color': color,
            'student_count': student_count,
            'fail_rate': fail_rate
        })
    
    edges = []
    for p in prereqs:
        if p.prerequisite_kp_id in kp_dict and p.target_kp_id in kp_dict:
            edges.append({
                'source': p.prerequisite_kp_id,
                'target': p.target_kp_id,
                'relation_type': p.relation_type
            })
    
    return jsonify({
        'nodes': nodes,
        'edges': edges
    })


@api_bp.route('/graph/admin_colored')
@login_required
def graph_admin_colored():
    all_kps = KnowledgePoint.query.filter_by(is_active=True).all()
    kp_dict = {kp.id: kp for kp in all_kps}
    
    prereqs = Prerequisite.query.all()
    
    chapter_colors = {
        "第1章": "#52c41a",
        "第2章": "#1890ff", 
        "第3章": "#722ed1",
        "第4章": "#fa8c16",
        "第5章": "#eb2f96",
        "第6章": "#13c2c2",
        "第7章": "#faad14",
        "第8章": "#f5222d"
    }
    
    def get_chapter_color(chapter_str):
        for key, color in chapter_colors.items():
            if chapter_str and key in chapter_str:
                return color
        return "#8c8c8c"
    
    nodes = []
    for kp in all_kps:
        color = get_chapter_color(kp.chapter)
        nodes.append({
            'id': kp.id,
            'name': kp.name,
            'chapter': kp.chapter,
            'difficulty': kp.difficulty,
            'importance': kp.importance,
            'description': kp.description,
            'estimated_minutes': kp.estimated_minutes,
            'color': color
        })
    
    edges = []
    for p in prereqs:
        if p.prerequisite_kp_id in kp_dict and p.target_kp_id in kp_dict:
            edges.append({
                'source': p.prerequisite_kp_id,
                'target': p.target_kp_id,
                'relation_type': p.relation_type
            })
    
    return jsonify({
        'nodes': nodes,
        'edges': edges
    })


@api_bp.route('/kp/<int:kp_id>')
@login_required
def kp_detail(kp_id):
    kp = KnowledgePoint.query.get_or_404(kp_id)
    
    prereqs = Prerequisite.query.filter_by(target_kp_id=kp_id).all()
    successors = Prerequisite.query.filter_by(prerequisite_kp_id=kp_id).all()
    
    return jsonify({
        'kp': {
            'id': kp.id,
            'name': kp.name,
            'chapter': kp.chapter,
            'description': kp.description,
            'difficulty': kp.difficulty,
            'importance': kp.importance,
            'estimated_minutes': kp.estimated_minutes,
            'is_active': kp.is_active
        },
        'prerequisites': [
            {'id': p.prerequisite_kp.id, 'name': p.prerequisite_kp.name}
            for p in prereqs
        ],
        'successors': [
            {'id': p.target_kp.id, 'name': p.target_kp.name}
            for p in successors
        ]
    })


@api_bp.route('/kp/learning_path/<int:kp_id>')
@login_required
def kp_learning_path(kp_id):
    student_id = get_student_id()
    path_data = get_learning_path_for_kp(kp_id, student_id)
    
    return jsonify(path_data)


@api_bp.route('/material/view/<int:material_id>', methods=['POST'])
@login_required
def record_material_view(material_id):
    return jsonify({'status': 'ok'})


@api_bp.route('/record_progress', methods=['POST'])
@login_required
def record_progress():
    data = request.get_json()
    kp_id = data.get('kp_id')
    study_duration = data.get('study_duration', 0)
    video_progress = data.get('video_progress', 0)
    text_progress = data.get('text_progress', 0)
    quiz_score = data.get('quiz_score')
    
    record = LearningRecord.query.filter_by(
        student_id=current_user.id, kp_id=kp_id
    ).order_by(LearningRecord.id.desc()).first()
    
    if not record:
        record = LearningRecord(student_id=current_user.id, kp_id=kp_id)
        db.session.add(record)
    
    record.study_duration = (record.study_duration or 0) + study_duration
    record.video_progress = max(record.video_progress or 0, video_progress)
    record.text_progress = max(record.text_progress or 0, text_progress)
    if quiz_score is not None:
        record.quiz_score = quiz_score
    
    db.session.commit()
    
    return jsonify({'status': 'ok'})