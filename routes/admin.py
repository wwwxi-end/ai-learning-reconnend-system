from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from models import db
from models.user import User, CourseGroup, TeacherCourseGroup
from models.knowledge_point import KnowledgePoint, LearningMaterial, QuizQuestion
from models.learning_record import LearningRecord
from models.prerequisite import Prerequisite
from utils.helpers import format_score

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('需要管理员权限', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_students': User.query.filter_by(role='student', is_active=True).count(),
        'total_teachers': User.query.filter_by(role='teacher', is_active=True).count(),
        'total_kps': KnowledgePoint.query.filter_by(is_active=True).count(),
        'total_records': LearningRecord.query.count(),
        'total_groups': CourseGroup.query.count(),
    }
    recent_students = User.query.filter_by(role='student').order_by(
        User.created_at.desc()).limit(10).all()
    recent_teachers = User.query.filter_by(role='teacher').order_by(
        User.created_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html', stats=stats,
                            recent_students=recent_students,
                            recent_teachers=recent_teachers,
                            now=datetime.utcnow())


# ===== 用户管理 =====
@admin_bp.route('/users')
@login_required
@admin_required
def user_list():
    role = request.args.get('role', 'student')
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')

    query = User.query.filter(User.role == role)
    if keyword:
        query = query.filter(
            (User.username.contains(keyword)) |
            (User.real_name.contains(keyword)) |
            (User.student_id.contains(keyword))
        )
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return render_template('admin/users.html', pagination=pagination,
                            role=role, keyword=keyword)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        real_name = request.form.get('real_name', '').strip()
        role = request.form.get('role', 'student')
        email = request.form.get('email', '').strip() or None
        student_id = request.form.get('student_id', '').strip() or None
        teacher_id = request.form.get('teacher_id', '').strip() or None
        department = request.form.get('department', '').strip() or None
        course_group = request.form.get('course_group', '').strip() or None

        # 验证
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return render_template('admin/create_user.html',
                                    course_groups=CourseGroup.query.all())

        user = User(
            username=username,
            real_name=real_name,
            role=role,
            email=email,
            student_id=student_id,
            teacher_id=teacher_id,
            department=department,
            course_group=course_group
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # 如果是老师且有课程组，建立关联
        if role == 'teacher' and course_group:
            cg = CourseGroup.query.filter_by(name=course_group).first()
            if cg:
                tcg = TeacherCourseGroup(teacher_id=user.id, course_group_id=cg.id)
                db.session.add(tcg)
                db.session.commit()

        flash(f'用户 {real_name} 创建成功', 'success')
        return redirect(url_for('admin.user_list', role=role))

    course_groups = CourseGroup.query.all()
    return render_template('admin/create_user.html', course_groups=course_groups)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        return jsonify({'error': '不能禁用管理员'}), 400
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({'status': 'ok', 'is_active': user.is_active})


@admin_bp.route('/users/<int:user_id>/reset_password', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '123456')
    user.set_password(new_password)
    db.session.commit()
    flash(f'用户 {user.real_name} 的密码已重置', 'success')
    return redirect(url_for('admin.user_list', role=user.role))


# ===== 批量导入用户 =====
@admin_bp.route('/users/batch_import', methods=['GET', 'POST'])
@login_required
@admin_required
def batch_import_users():
    if request.method == 'POST':
        import csv
        import io
        file = request.files.get('csv_file')
        if not file:
            flash('请上传CSV文件', 'warning')
            return redirect(request.url)

        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        created = 0
        errors = []

        for row in reader:
            try:
                username = row.get('username', '').strip()
                if not username or User.query.filter_by(username=username).first():
                    errors.append(f"用户名 {username} 已存在或为空")
                    continue

                user = User(
                    username=username,
                    real_name=row.get('real_name', username),
                    role=row.get('role', 'student'),
                    email=row.get('email') or None,
                    student_id=row.get('student_id') or None,
                    teacher_id=row.get('teacher_id') or None,
                    department=row.get('department') or None
                )
                user.set_password(row.get('password', '123456'))
                db.session.add(user)
                created += 1
            except Exception as e:
                errors.append(str(e))

        db.session.commit()
        flash(f'成功导入 {created} 个用户，{len(errors)} 个失败', 'info')
        if errors:
            for e in errors[:5]:
                flash(e, 'warning')
        return redirect(url_for('admin.user_list'))

    return render_template('admin/batch_import.html')


# ===== 课程组管理 =====
@admin_bp.route('/course_groups')
@login_required
@admin_required
def course_group_list():
    groups = CourseGroup.query.all()
    return render_template('admin/course_groups.html', groups=groups)


@admin_bp.route('/course_groups/create', methods=['POST'])
@login_required
@admin_required
def create_course_group():
    name = request.form.get('name', '').strip()
    course_name = request.form.get('course_name', '').strip()
    description = request.form.get('description', '').strip()

    if CourseGroup.query.filter_by(name=name).first():
        flash('课程组名称已存在', 'danger')
    else:
        cg = CourseGroup(name=name, course_name=course_name, description=description)
        db.session.add(cg)
        db.session.commit()
        flash(f'课程组 {name} 创建成功', 'success')
    return redirect(url_for('admin.course_group_list'))


# ===== 知识点管理（管理员视图）=====
@admin_bp.route('/knowledge_points')
@login_required
@admin_required
def knowledge_point_list():
    kps = KnowledgePoint.query.order_by(
        KnowledgePoint.chapter_order, KnowledgePoint.id).all()
    return render_template('admin/knowledge_points.html', kps=kps)


@admin_bp.route('/knowledge_points/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_knowledge_point():
    if request.method == 'POST':
        kp = KnowledgePoint(
            name=request.form.get('name', '').strip(),
            code=request.form.get('code', '').strip(),
            chapter=request.form.get('chapter', '').strip(),
            chapter_order=int(request.form.get('chapter_order', 0)),
            description=request.form.get('description', ''),
            difficulty=int(request.form.get('difficulty', 3)),
            importance=int(request.form.get('importance', 3)),
            estimated_minutes=int(request.form.get('estimated_minutes', 30)),
            created_by=current_user.id
        )
        db.session.add(kp)
        db.session.commit()

        # 同步到Neo4j
        try:
            from services.neo4j_service import neo4j_service
            neo4j_id = neo4j_service.create_knowledge_point({
                'code': kp.code,
                'name': kp.name,
                'chapter': kp.chapter,
                'chapter_order': kp.chapter_order,
                'description': kp.description or '',
                'difficulty': kp.difficulty,
                'importance': kp.importance,
                'mysql_id': kp.id
            })
            if neo4j_id:
                kp.neo4j_id = neo4j_id
                db.session.commit()
        except Exception as e:
            flash(f'Neo4j同步失败（不影响使用）：{str(e)}', 'warning')

        flash(f'知识点 {kp.name} 创建成功', 'success')
        return redirect(url_for('admin.knowledge_point_list'))

    return render_template('admin/create_knowledge_point.html')


# ===== 系统统计 =====
@admin_bp.route('/stats')
@login_required
@admin_required
def system_stats():
    from sqlalchemy import func
    from services.diagnosis import calculate_weighted_score
    
    teachers = User.query.filter_by(role='teacher', is_active=True).all()
    
    all_kps = KnowledgePoint.query.filter_by(is_active=True).order_by(KnowledgePoint.chapter_order).all()
    kp_map = {kp.id: kp for kp in all_kps}
    
    all_students = User.query.filter_by(role='student', is_active=True).all()
    student_group_map = {s.id: s.course_group for s in all_students}
    group_students_map = {}
    for s in all_students:
        group_id = s.course_group
        if group_id not in group_students_map:
            group_students_map[group_id] = []
        group_students_map[group_id].append(s.id)
    
    kp_ids = [kp.id for kp in all_kps]
    if kp_ids:
        subq = db.session.query(
            LearningRecord.student_id,
            LearningRecord.kp_id,
            func.max(LearningRecord.id).label("max_id")
        ).filter(LearningRecord.kp_id.in_(kp_ids)).group_by(
            LearningRecord.student_id, LearningRecord.kp_id
        ).subquery()
        
        all_records = db.session.query(LearningRecord).join(
            subq, LearningRecord.id == subq.c.max_id
        ).all()
        
        record_map = {}
        for rec in all_records:
            key = (rec.student_id, rec.kp_id)
            record_map[key] = rec
    else:
        record_map = {}
    
    teacher_kp_stats = []
    for teacher in teachers:
        teacher_group_id = teacher.course_group
        student_ids = group_students_map.get(teacher_group_id, [])
        
        kp_stats = []
        for kp in all_kps:
            if not student_ids:
                kp_stats.append({
                    'kp_id': kp.id,
                    'kp_name': kp.name,
                    'chapter': kp.chapter,
                    'avg_score': None,
                    'record_count': 0
                })
                continue
            
            scores = []
            for student_id in student_ids:
                key = (student_id, kp.id)
                if key in record_map:
                    scores.append(calculate_weighted_score(record_map[key]))
            
            if scores:
                avg_score = format_score(sum(scores) / len(scores))
                record_count = len(scores)
            else:
                avg_score = None
                record_count = 0
            
            kp_stats.append({
                'kp_id': kp.id,
                'kp_name': kp.name,
                'chapter': kp.chapter,
                'avg_score': avg_score,
                'record_count': record_count
            })
        
        teacher_kp_stats.append({
            'teacher_id': teacher.id,
            'teacher_name': teacher.real_name,
            'kp_stats': kp_stats
        })

    return render_template('admin/stats.html', teacher_kp_stats=teacher_kp_stats)


@admin_bp.route('/stats/knowledge_graph')
@login_required
@admin_required
def admin_knowledge_graph():
    return render_template('admin/admin_knowledge_graph.html')
