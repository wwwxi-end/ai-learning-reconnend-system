import os
import traceback
from flask import Flask, render_template, jsonify, request
from flask_login import LoginManager, login_required, current_user
from sqlalchemy import text
from models import db
from models.learning_record import LearningRecord
from models.knowledge_point import KnowledgePoint
from models.prerequisite import Prerequisite
from models.user import User
from config import config
from services.llm_service import llm_service
from services.neo4j_service import neo4j_service
from extensions import cache, csrf, limiter

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'warning'


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))
    app.debug = False

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'texts'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'questions'), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    cache.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    llm_service.init_app(app)
    try:
        neo4j_service.init_app(app)
    except Exception as exc:
        app.logger.warning('Neo4j 初始化失败：%s', exc)

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.teacher import teacher_bp
    from routes.student import student_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(teacher_bp, url_prefix='/teacher')
    app.register_blueprint(student_bp, url_prefix='/student')

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    import json

    @app.template_filter('from_json')
    def from_json_filter(value):
        try:
            return json.loads(value or '[]')
        except Exception:
            return []

    @app.template_filter('tojson_safe')
    def tojson_safe_filter(value):
        return json.dumps(value, ensure_ascii=False)

    @app.errorhandler(404)
    def not_found(error):
        return (render_template('errors/404.html'), 404)

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.route('/api/forgetting_trend')
    @login_required
    def forgetting_trend():
        try:
            student_id = current_user.id
            if request.args.get('student_id') and current_user.role in ('teacher', 'admin'):
                student_id = request.args.get('student_id', type=int)

            kp_ids = [row[0] for row in db.session.query(LearningRecord.kp_id).filter(
                LearningRecord.student_id == student_id
            ).distinct().all()]
            
            kps_dict = {}
            if kp_ids:
                kps_list = KnowledgePoint.query.filter(
                    KnowledgePoint.id.in_(kp_ids)
                ).all()
                kps_dict = {kp.id: kp for kp in kps_list}

            result = []
            for kid in kp_ids:
                records = LearningRecord.query.filter(
                    LearningRecord.student_id == student_id,
                    LearningRecord.kp_id == kid
                ).order_by(LearningRecord.updated_at).all()

                if len(records) < 2:
                    continue

                scores = []
                timestamps = []
                for i, record in enumerate(records):
                    video_val = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
                    t_score_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
                    quiz_val = getattr(record, 'quiz_score', 0) or 0
                    ws_val = round(video_val * 0.35 + t_score_val * 0.15 + quiz_val * 0.50, 2)
                    scores.append(ws_val)
                    timestamps.append(i)

                if len(scores) < 2:
                    continue

                n = len(scores)
                sum_x = sum(timestamps)
                sum_y = sum(scores)
                sum_xy = sum(x * y for x, y in zip(timestamps, scores))
                sum_x2 = sum(x * x for x in timestamps)

                denominator = n * sum_x2 - sum_x * sum_x
                if denominator == 0:
                    slope = 0
                else:
                    slope = (n * sum_xy - sum_x * sum_y) / denominator

                kp = kps_dict.get(kid)
                result.append({
                    'kp_id': kid,
                    'kp_name': kp.name if kp else f'知识点{kid}',
                    'chapter': kp.chapter if kp else '',
                    'slope': round(slope, 4),
                    'scores': scores,
                    'timestamps': timestamps
                })

            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

    @app.route('/api/dashboard_stats')
    @login_required
    def dashboard_stats():
        try:
            student_id = current_user.id
            if request.args.get('student_id') and current_user.role in ('teacher', 'admin'):
                student_id = request.args.get('student_id', type=int)

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
                video_val = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
                t_score_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
                quiz_val = getattr(record, 'quiz_score', 0) or 0
                ws_val = round(video_val * 0.35 + t_score_val * 0.15 + quiz_val * 0.50, 2)
                scores.append(ws_val)

                if ws_val >= 80:
                    mastered_count += 1
                elif ws_val >= 60:
                    partial_count += 1
                else:
                    weak_count += 1

            total_kps = KnowledgePoint.query.count()
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
        except Exception as e:
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

    @app.route('/api/chapter_radar')
    @login_required
    def chapter_radar():
        try:
            student_id = current_user.id
            if request.args.get('student_id') and current_user.role in ('teacher', 'admin'):
                student_id = request.args.get('student_id', type=int)

            chapters = db.session.query(KnowledgePoint.chapter).distinct().all()
            chapter_list = [ch[0] for ch in chapters if ch[0]]

            result = []
            for chapter in chapter_list:
                kps_in_chapter = KnowledgePoint.query.filter(
                    KnowledgePoint.chapter == chapter
                ).all()
                kp_ids = [kp.id for kp in kps_in_chapter]

                records = LearningRecord.query.filter(
                    LearningRecord.student_id == student_id,
                    LearningRecord.kp_id.in_(kp_ids)
                ).all()

                if not records:
                    avg_score = 0
                else:
                    total_ws = 0
                    for record in records:
                        video_val = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
                        t_score_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
                        quiz_val = getattr(record, 'quiz_score', 0) or 0
                        ws_val = round(video_val * 0.35 + t_score_val * 0.15 + quiz_val * 0.50, 2)
                        total_ws += ws_val
                    avg_score = round(total_ws / len(records), 2)

                result.append({
                    'name': chapter,
                    'value': avg_score,
                    'max': 100
                })

            return jsonify({
                'indicators': result,
                'values': [item['value'] for item in result]
            })
        except Exception as e:
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

    @app.route('/api/weak_points')
    @login_required
    def weak_points():
        try:
            student_id = current_user.id
            if request.args.get('student_id') and current_user.role in ('teacher', 'admin'):
                student_id = request.args.get('student_id', type=int)

            records = LearningRecord.query.filter(
                LearningRecord.student_id == student_id
            ).all()

            if not records:
                return jsonify([])

            kp_scores = {}
            kp_history = {}

            for record in records:
                kid = record.kp_id
                video_val = getattr(record, 'video_score', 0) or getattr(record, 'video_progress', 0) or 0
                t_score_val = getattr(record, 'text_score', 0) or getattr(record, 'text_progress', 0) or 0
                quiz_val = getattr(record, 'quiz_score', 0) or 0
                ws_val = round(video_val * 0.35 + t_score_val * 0.15 + quiz_val * 0.50, 2)

                if kid not in kp_scores:
                    kp_scores[kid] = []
                    kp_history[kid] = []
                kp_scores[kid].append(ws_val)
                kp_history[kid].append({
                    'score': ws_val,
                    'updated_at': record.updated_at
                })

            all_scores = [s for scores in kp_scores.values() for s in scores]
            if not all_scores:
                return jsonify([])
            overall_avg = sum(all_scores) / len(all_scores)

            kps = KnowledgePoint.query.all()
            kps_dict = {kp.id: kp for kp in kps}

            weak_points_list = []
            for kid, scores in kp_scores.items():
                latest_score = scores[-1]
                avg_score = sum(scores) / len(scores)
                drop_count = sum(1 for i in range(1, len(scores)) if scores[i] < scores[i-1])
                total_drop = sum(max(0, scores[i-1] - scores[i]) for i in range(1, len(scores)))
                max_score = max(scores)
                min_score = min(scores)

                is_absolute_weak = latest_score < 60
                is_relative_weak = latest_score < overall_avg * 0.8

                has_forgetting_trend = False
                if len(scores) >= 2:
                    n = len(scores)
                    sum_x = sum(range(n))
                    sum_y = sum(scores)
                    sum_xy = sum(i * s for i, s in enumerate(scores))
                    sum_x2 = sum(i * i for i in range(n))
                    denominator = n * sum_x2 - sum_x * sum_x
                    if denominator != 0:
                        slope = (n * sum_xy - sum_x * sum_y) / denominator
                        has_forgetting_trend = slope < -0.5

                has_high_risk = False
                kp = kps_dict.get(kid)
                if kp:
                    blocked_count = Prerequisite.query.filter(
                        Prerequisite.prerequisite_kp_id == kid
                    ).count()
                    has_high_risk = blocked_count >= 2

                if is_absolute_weak or is_relative_weak or has_forgetting_trend or has_high_risk:
                    tags = []
                    if is_absolute_weak:
                        tags.append('绝对薄弱')
                    if is_relative_weak:
                        tags.append('相对薄弱')
                    if has_forgetting_trend:
                        tags.append('遗忘趋势')
                    if has_high_risk:
                        tags.append('高危薄弱')

                    weak_points_list.append({
                        'kp_id': kid,
                        'kp_name': kp.name if kp else f'知识点{kid}',
                        'chapter': kp.chapter if kp else '',
                        'current_score': latest_score,
                        'avg_score': round(avg_score, 2),
                        'max_score': max_score,
                        'min_score': min_score,
                        'total_drop': total_drop,
                        'drop_count': drop_count,
                        'tags': tags,
                        'history': kp_history[kid]
                    })

            weak_points_list.sort(key=lambda x: x['current_score'])
            return jsonify(weak_points_list)
        except Exception as e:
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

    with app.app_context():
        db.create_all()

    return app


if __name__ == '__main__':
    app = create_app()
    app.debug = False
    app.run(host='0.0.0.0', port=8888, use_reloader=False)
