import os
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, current_app, send_from_directory)
from flask_login import login_required, current_user
from functools import wraps
from werkzeug.utils import secure_filename
from models import db
from models.knowledge_point import KnowledgePoint, LearningMaterial, QuizQuestion
from models.learning_record import LearningRecord
from models.prerequisite import Prerequisite
from services.diagnosis import get_class_weak_analysis
from services.llm_service import llm_service
from services.cache_service import PageCacheService
from utils.helpers import format_score

teacher_bp = Blueprint('teacher', __name__)


def teacher_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('teacher', 'admin'):
            flash('需要教师权限', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set


@teacher_bp.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    # 本教师上传的材料和题目数量
    my_materials = LearningMaterial.query.filter_by(
        teacher_id=current_user.id, is_active=True).count()
    my_questions = QuizQuestion.query.filter_by(
        teacher_id=current_user.id, is_active=True).count()

    # 班级薄弱点分析 - 优先读缓存
    class_analysis = PageCacheService.get_cached_or_compute(
        current_user.id, 'class_weak_analysis',
        lambda: get_class_weak_analysis(current_user.id),
        timeout_seconds=600
    )
    weak_kps = [k for k in class_analysis if k['avg_score'] is not None and k['avg_score'] < 60][:5]

    return render_template('teacher/dashboard.html',
                            my_materials=my_materials,
                            my_questions=my_questions,
                            weak_kps=weak_kps,
                            class_analysis=class_analysis[:10])


# ===== 材料管理 =====
@teacher_bp.route('/materials')
@login_required
@teacher_required
def material_list():
    kp_id = request.args.get('kp_id', type=int)
    page = request.args.get('page', 1, type=int)

    query = LearningMaterial.query.filter_by(teacher_id=current_user.id, is_active=True)
    if kp_id:
        query = query.filter_by(kp_id=kp_id)

    pagination = query.order_by(LearningMaterial.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    kps = KnowledgePoint.query.filter_by(is_active=True).order_by(
        KnowledgePoint.chapter_order).all()

    return render_template('teacher/materials.html', pagination=pagination,
                            kps=kps, current_kp_id=kp_id)


@teacher_bp.route('/materials/upload', methods=['GET', 'POST'])
@login_required
@teacher_required
def upload_material():
    kps = KnowledgePoint.query.filter_by(is_active=True).order_by(
        KnowledgePoint.chapter_order).all()

    if request.method == 'POST':
        kp_id = request.form.get('kp_id', type=int)
        title = request.form.get('title', '').strip()
        material_type = request.form.get('material_type', 'text')
        description = request.form.get('description', '').strip()
        content = request.form.get('content', '')
        external_url = request.form.get('external_url', '').strip()

        if not kp_id or not title:
            flash('请填写完整信息', 'warning')
            return render_template('teacher/upload_material.html', kps=kps)

        material = LearningMaterial(
            kp_id=kp_id,
            teacher_id=current_user.id,
            title=title,
            material_type=material_type,
            description=description,
            content=content if material_type == 'text' else None,
            external_url=external_url if external_url else None
        )

        file = request.files.get('file')
        if file and file.filename:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'],
                                       material_type + 's')
            os.makedirs(upload_dir, exist_ok=True)

            allowed = (current_app.config['ALLOWED_VIDEO_EXTENSIONS']
                       if material_type == 'video'
                       else current_app.config['ALLOWED_DOC_EXTENSIONS'])

            if not allowed_file(file.filename, allowed):
                flash(f'不支持的文件格式', 'danger')
                return render_template('teacher/upload_material.html', kps=kps)

            filename = secure_filename(file.filename)
            import time
            filename = f"{int(time.time())}_{filename}"
            save_path = os.path.join(upload_dir, filename)
            file.save(save_path)
            material.file_path = os.path.join(material_type + 's', filename)
            material.file_size = os.path.getsize(save_path)

        db.session.add(material)
        db.session.commit()
        flash(f'材料《{title}》上传成功', 'success')
        return redirect(url_for('teacher.material_list'))

    return render_template('teacher/upload_material.html', kps=kps)


@teacher_bp.route('/materials/<int:material_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_material(material_id):
    material = LearningMaterial.query.get_or_404(material_id)
    if material.teacher_id != current_user.id and current_user.role != 'admin':
        return jsonify({'error': '无权限'}), 403
    material.is_active = False
    db.session.commit()
    return jsonify({'status': 'ok'})


# ===== 题目管理 =====
@teacher_bp.route('/questions')
@login_required
@teacher_required
def question_list():
    kp_id = request.args.get('kp_id', type=int)
    page = request.args.get('page', 1, type=int)

    query = QuizQuestion.query.filter_by(teacher_id=current_user.id, is_active=True)
    if kp_id:
        query = query.filter_by(kp_id=kp_id)

    pagination = query.order_by(QuizQuestion.kp_id, QuizQuestion.order_in_kp).paginate(
        page=page, per_page=20, error_out=False)
    kps = KnowledgePoint.query.filter_by(is_active=True).order_by(
        KnowledgePoint.chapter_order).all()

    # 统计每个知识点有多少道题
    from sqlalchemy import func
    kp_question_counts = dict(db.session.query(
        QuizQuestion.kp_id, func.count(QuizQuestion.id)
    ).filter_by(teacher_id=current_user.id, is_active=True
    ).group_by(QuizQuestion.kp_id).all())

    return render_template('teacher/questions.html', pagination=pagination,
                            kps=kps, current_kp_id=kp_id,
                            kp_question_counts=kp_question_counts)


@teacher_bp.route('/questions/create', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_question():
    kps = KnowledgePoint.query.filter_by(is_active=True).order_by(
        KnowledgePoint.chapter_order).all()

    if request.method == 'POST':
        kp_id = request.form.get('kp_id', type=int)
        # 获取已有题目数量
        existing_count = QuizQuestion.query.filter_by(
            kp_id=kp_id, teacher_id=current_user.id, is_active=True).count()

        if existing_count >= 5:
            flash('该知识点已有5道题目，如需修改请先删除旧题', 'warning')
            return redirect(url_for('teacher.question_list', kp_id=kp_id))

        question = QuizQuestion(
            kp_id=kp_id,
            teacher_id=current_user.id,
            question_text=request.form.get('question_text', '').strip(),
            question_type=request.form.get('question_type', 'single'),
            option_a=request.form.get('option_a', '').strip() or None,
            option_b=request.form.get('option_b', '').strip() or None,
            option_c=request.form.get('option_c', '').strip() or None,
            option_d=request.form.get('option_d', '').strip() or None,
            correct_answer=request.form.get('correct_answer', '').strip().upper(),
            explanation=request.form.get('explanation', '').strip() or None,
            difficulty=int(request.form.get('difficulty', 3)),
            order_in_kp=existing_count + 1
        )
        db.session.add(question)
        db.session.commit()
        flash('题目创建成功', 'success')
        return redirect(url_for('teacher.question_list', kp_id=kp_id))

    kp_id = request.args.get('kp_id', type=int)
    return render_template('teacher/create_question.html', kps=kps, selected_kp_id=kp_id)


@teacher_bp.route('/questions/<int:question_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_question(question_id):
    question = QuizQuestion.query.get_or_404(question_id)
    if question.teacher_id != current_user.id and current_user.role != 'admin':
        return jsonify({'error': '无权限'}), 403
    question.is_active = False
    db.session.commit()
    return jsonify({'status': 'ok'})


# ===== 班级分析 =====
@teacher_bp.route('/class_analysis')
@login_required
@teacher_required
def class_analysis():
    analysis = PageCacheService.get_cached_or_compute(
        current_user.id, 'class_weak_analysis',
        lambda: get_class_weak_analysis(current_user.id),
        timeout_seconds=600
    )
    return render_template('teacher/class_analysis.html', analysis=analysis)


@teacher_bp.route('/class_analysis/knowledge_graph')
@login_required
@teacher_required
def class_knowledge_graph():
    return render_template('teacher/class_knowledge_graph.html')


@teacher_bp.route('/class_analysis/ai_advice')
@login_required
@teacher_required
def ai_class_advice():
    analysis = get_class_weak_analysis(current_user.id)
    advice = llm_service.generate_teacher_advice(analysis, top_n=5)
    return jsonify({'advice': advice})


@teacher_bp.route('/student_detail/<int:student_id>')
@login_required
@teacher_required
def student_detail(student_id):
    from models.user import User
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash('该用户不是学生', 'warning')
        return redirect(url_for('teacher.dashboard'))

    # 学生学习记录
    records = LearningRecord.query.filter_by(student_id=student_id).order_by(
        LearningRecord.updated_at.desc()).all()

    # 获取薄弱点 - 优先读缓存
    from services.cache_service import PageCacheService
    from services.diagnosis import detect_weak_points
    weak_analysis = PageCacheService.get_cached_or_compute(
        student_id, 'weak_points',
        lambda: detect_weak_points(student_id),
        timeout_seconds=300
    )

    return render_template('teacher/student_detail.html',
                            student=student,
                            records=records,
                            weak_analysis=weak_analysis)


@teacher_bp.route('/prerequisites')
@login_required
@teacher_required
def prerequisite_manage():
    kps = KnowledgePoint.query.filter_by(is_active=True).order_by(
        KnowledgePoint.chapter_order).all()
    prerequisites = Prerequisite.query.all()
    return render_template('teacher/prerequisites.html',
                            kps=kps, prerequisites=prerequisites)


@teacher_bp.route('/prerequisites/create', methods=['POST'])
@login_required
@teacher_required
def create_prerequisite():
    prereq_id = request.form.get('prerequisite_kp_id', type=int)
    target_id = request.form.get('target_kp_id', type=int)
    relation_type = request.form.get('relation_type', 'must')

    if prereq_id == target_id:
        flash('前置知识点和目标知识点不能相同', 'warning')
        return redirect(url_for('teacher.prerequisite_manage'))

    existing = Prerequisite.query.filter_by(
        prerequisite_kp_id=prereq_id, target_kp_id=target_id).first()
    if existing:
        flash('该前驱关系已存在', 'warning')
        return redirect(url_for('teacher.prerequisite_manage'))

    prereq = Prerequisite(
        prerequisite_kp_id=prereq_id,
        target_kp_id=target_id,
        relation_type=relation_type
    )
    db.session.add(prereq)
    db.session.commit()

    # 同步到Neo4j
    try:
        from services.neo4j_service import neo4j_service
        from_kp = KnowledgePoint.query.get(prereq_id)
        to_kp = KnowledgePoint.query.get(target_id)
        if from_kp and to_kp:
            neo4j_service.create_prerequisite_relation(
                from_kp.code, to_kp.code, relation_type.upper())
    except Exception as e:
        flash(f'Neo4j同步失败：{str(e)}', 'warning')

    flash('前驱关系创建成功', 'success')
    return redirect(url_for('teacher.prerequisite_manage'))

# teacher.py 新增前驱删除路由
@teacher_bp.route('/prerequisites/<int:prereq_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_prerequisite(prereq_id):
    prereq = Prerequisite.query.get_or_404(prereq_id)
    from_kp = KnowledgePoint.query.get(prereq.prerequisite_kp_id)
    to_kp = KnowledgePoint.query.get(prereq.target_kp_id)
    # 先删除Neo4j关系
    try:
        from services.neo4j_service import neo4j_service
        query = """
        MATCH (a:KnowledgePoint{code:$from})-[r:PREREQUISITE_OF]->(b:KnowledgePoint{code:$to})
        DELETE r
        """
        neo4j_service.run_query(query, {"from": from_kp.code, "to": to_kp.code})
    except Exception as e:
        flash(f"Neo4j同步删除失败:{str(e)}", "warning")
    # 删除MySQL
    db.session.delete(prereq)
    db.session.commit()
    flash("前驱关系删除成功", "success")
    return redirect(url_for("teacher.prerequisite_manage"))