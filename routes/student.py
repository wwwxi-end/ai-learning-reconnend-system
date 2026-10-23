from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, make_response, current_app)
from flask_login import login_required, current_user
from datetime import datetime
from functools import wraps
from models import db
from models.knowledge_point import KnowledgePoint, LearningMaterial, QuizQuestion
from models.learning_record import LearningRecord, QuizSubmission, QuizAnswer, StudySession
from models.prerequisite import Prerequisite
from services.diagnosis import detect_weak_points
from services.recommendation import generate_recommendations, get_learning_path_for_kp
from services.llm_service import llm_service
from services.pdf_generator import generate_learning_plan_pdf
from extensions import cache
from sqlalchemy import func

# 创建学生模块蓝图，用于管理学生端所有页面和接口
student_bp = Blueprint('student', __name__)

from utils.helpers import format_score
import time

# 学习计划数据的模块级缓存，避免重复计算（缓存字典 + 时间戳）
_student_plan_cache = {}
_PLAN_CACHE_TTL = 120  # 缓存过期时间（秒），超过后自动重新计算


def invalidate_student_cache(student_id):
    """使学生相关的所有缓存失效
    
    当学生提交测验或更新学习进度时调用，确保数据实时性。
    
    参数:
        student_id: 学生用户ID
    """
    # 需要清除的缓存键列表（覆盖图表、统计、薄弱点、推荐等所有学生相关缓存）
    cache_keys = [
        f"graph_colored_{student_id}",
        f"dashboard_stats_{student_id}",
        f"chapter_radar_{student_id}",
        f"score_distribution_{student_id}",
        f"weak_points_{student_id}",
        f"recommendations_{student_id}"
    ]
    # 逐个清除Flask-Caching缓存
    for key in cache_keys:
        try:
            cache.delete(key)
        except Exception:
            pass
    # 清除memoized缓存（detect_weak_points函数的缓存）
    try:
        from services.diagnosis import detect_weak_points
        cache.delete_memoized(detect_weak_points, student_id)
    except Exception:
        pass
    # 清除模块级学习计划缓存
    _student_plan_cache.pop(student_id, None)


def _get_student_plan_data(student_id):
    """获取学习计划所需的所有数据（带TTL缓存）
    
    使用模块级字典缓存，每条记录附带时间戳，超过_PLAN_CACHE_TTL秒自动失效。
    invalidate_student_cache()也会清除该缓存，确保学生提交测验后立即刷新。
    
    参数:
        student_id: 学生用户ID
    
    返回值结构:
        {
            'weak_analysis': 薄弱点分析结果,
            'recommendations': 推荐列表,
            'student_data': {
                'name': 学生姓名,
                'avg_score': 平均分数,
                'studied_count': 已学知识点数,
                'weak_count': 薄弱点数量,
                'progress': 学习进度百分比
            },
            '_cache_time': 缓存时间戳
        }
    """
    now = time.time()
    # 检查缓存是否存在且未过期
    if student_id in _student_plan_cache:
        cached = _student_plan_cache[student_id]
        # 检查TTL是否过期（当前时间 - 缓存时间 < 过期时间）
        if now - cached['_cache_time'] < _PLAN_CACHE_TTL:
            return cached
        else:
            # 缓存过期，删除旧缓存以便重新计算
            del _student_plan_cache[student_id]
    
    # 重新计算数据：调用薄弱点检测算法
    weak_analysis = detect_weak_points(student_id)
    # 使用薄弱点分析结果生成推荐（避免重复计算）
    recs = generate_recommendations(student_id, top_n=5, weak_analysis=weak_analysis)
    
    # 查询学生平均分数（聚合查询）
    avg_score = db.session.query(func.avg(LearningRecord.quiz_score)).filter_by(
        student_id=student_id).scalar() or 0
    # 查询已学知识点数量（去重计数）
    studied_count = db.session.query(
        LearningRecord.kp_id.distinct()).filter_by(student_id=student_id).count()
    # 查询总知识点数量（活跃状态）
    total_kps = KnowledgePoint.query.filter_by(is_active=True).count()
    
    # 查询学生信息（姓名）
    from models.user import User
    student = User.query.get(student_id)
    student_name = student.real_name if student else ''
    
    # 组装学生数据字典
    student_data = {
        'name': student_name,
        'avg_score': format_score(float(avg_score)),
        'studied_count': studied_count,
        'weak_count': len(weak_analysis.get('absolute_weak', [])) +
                      len(weak_analysis.get('relative_weak', [])),
        'progress': (studied_count / total_kps * 100) if total_kps else 0
    }
    
    # 组装最终结果
    result = {
        'weak_analysis': weak_analysis,
        'recommendations': recs,
        'student_data': student_data,
        'plan_content': None,
        '_cache_time': now  # 记录缓存时间，用于TTL检查
    }
    
    # 存入缓存
    _student_plan_cache[student_id] = result
    return result


def student_required(f):
    """学生角色权限装饰器
    
    检查当前用户是否已登录且角色为student，否则重定向到登录页面。
    
    参数:
        f: 被装饰的视图函数
    
    返回:
        装饰后的视图函数
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            flash('需要学生身份', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@student_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    """学生仪表盘页面
    
    展示学生学习统计、薄弱点分析、推荐列表和最近学习记录
    """
    # 基本学习统计：总知识点数
    total_kps = KnowledgePoint.query.filter_by(is_active=True).count()
    # 已学习知识点数（去重）
    studied_kps = db.session.query(LearningRecord.kp_id.distinct()).filter_by(
        student_id=current_user.id).count()

    # 已掌握知识点数量（最新加权分≥60分）：使用子查询获取每个知识点最新记录
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=current_user.id).group_by(
        LearningRecord.kp_id).subquery()

    from services.diagnosis import calculate_weighted_score
    latest_records_for_mastered = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    mastered_count = sum(1 for r in latest_records_for_mastered if calculate_weighted_score(r) >= 60)

    # 薄弱点分析（只计算一次，异常时返回空）
    try:
        weak_analysis = detect_weak_points(current_user.id)
        weak_summary = weak_analysis.get('summary', {})
    except Exception:
        weak_analysis = None
        weak_summary = {}

    # 最新推荐（复用薄弱分析结果，避免重复计算）
    try:
        recommendations = generate_recommendations(current_user.id, top_n=5, weak_analysis=weak_analysis)
    except Exception:
        recommendations = []

    # 最近学习记录（按更新时间倒序，取前5条）
    recent_records = LearningRecord.query.filter_by(
        student_id=current_user.id
    ).order_by(LearningRecord.updated_at.desc()).limit(5).all()

    # 渲染仪表盘页面，传递统计数据和推荐信息
    return render_template('student/dashboard.html',
                            total_kps=total_kps,
                            studied_kps=studied_kps,
                            mastered_count=mastered_count,
                            recommendations=recommendations,
                            weak_summary=weak_summary,
                            recent_records=recent_records)


@student_bp.route('/knowledge_points')
@login_required
@student_required
def knowledge_list():
    """知识点列表页面
    
    支持按章节筛选，展示各知识点及其最新成绩
    """
    # 获取章节筛选参数（URL query参数）
    chapter = request.args.get('chapter', '')
    # 查询活跃知识点，支持章节筛选
    kps = KnowledgePoint.query.filter_by(is_active=True)
    if chapter:
        kps = kps.filter_by(chapter=chapter)
    # 按章节排序和ID排序，确保知识点有序展示
    kps = kps.order_by(KnowledgePoint.chapter_order, KnowledgePoint.id).all()

    # 获取学生各知识点最新成绩（使用子查询优化，避免N+1查询问题）
    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=current_user.id).group_by(
        LearningRecord.kp_id).subquery()

    # 构建知识点ID到成绩的映射字典（使用加权分数，与图谱着色、诊断逻辑一致）
    from services.diagnosis import calculate_weighted_score
    score_map = {}
    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id).all()
    for r in records:
        score_map[r.kp_id] = calculate_weighted_score(r)

    # 获取所有章节列表（去重并排序），用于筛选下拉框
    chapters = db.session.query(
        KnowledgePoint.chapter, KnowledgePoint.chapter_order
    ).distinct().order_by(KnowledgePoint.chapter_order).all()

    # 渲染知识点列表页面，传递知识点列表、成绩映射和章节列表
    return render_template('student/knowledge_list.html',
                            kps=kps, score_map=score_map,
                            chapters=chapters, current_chapter=chapter)


@student_bp.route('/learn/<int:kp_id>')
@login_required
@student_required
def learn_kp(kp_id):
    """学习知识点页面
    
    展示知识点详情、学习材料、测验题目、前驱后继关系和学习历史
    
    参数:
        kp_id: 知识点ID（URL路径参数）
    """
    # 获取知识点对象（不存在返回404错误）
    kp = KnowledgePoint.query.get_or_404(kp_id)
    # 获取该知识点的活跃学习材料
    materials = LearningMaterial.query.filter_by(kp_id=kp_id, is_active=True).all()
    # 获取该知识点的活跃测验题目（按序号排序）
    questions = QuizQuestion.query.filter_by(kp_id=kp_id, is_active=True).order_by(
        QuizQuestion.order_in_kp).all()

    # 获取前驱知识点（当前知识点是目标）
    prereqs = Prerequisite.query.filter_by(target_kp_id=kp_id).all()
    # 获取后继知识点（当前知识点是前置）
    successors = Prerequisite.query.filter_by(prerequisite_kp_id=kp_id).all()

    # 获取学生该知识点的学习历史（按创建时间倒序）
    history = LearningRecord.query.filter_by(
        student_id=current_user.id, kp_id=kp_id
    ).order_by(LearningRecord.created_at.desc()).all()

    # 计算最佳成绩（取所有历史记录中的最高分）
    best_score = max((r.quiz_score for r in history if r.quiz_score is not None), default=None)

    # 记录开始学习会话（创建学习会话记录）
    session = StudySession(
        student_id=current_user.id,
        kp_id=kp_id,
        start_time=datetime.utcnow(),
        # 根据材料类型自动选择操作类型（优先视频）
        action_type='watch_video' if any(m.material_type == 'video' for m in materials) else 'read_text'
    )
    db.session.add(session)
    db.session.commit()

    # 渲染学习页面，传递知识点、材料、题目、关系和历史数据
    return render_template('student/learn.html',
                            kp=kp,
                            materials=materials,
                            questions=questions,
                            prereqs=[p.prerequisite_kp for p in prereqs],
                            successors=[p.target_kp for p in successors],
                            history=history,
                            best_score=best_score,
                            session_id=session.id)


@student_bp.route('/learn/<int:kp_id>/record_progress', methods=['POST'])
@login_required
@student_required
def record_progress(kp_id):
    """记录学习进度（AJAX接口）
    
    更新学习会话结束时间和学习记录进度
    
    参数:
        kp_id: 知识点ID（URL路径参数）
    """
    # 获取JSON请求数据（前端通过AJAX发送）
    data = request.get_json()
    session_id = data.get('session_id')
    progress = data.get('progress', 0)
    duration = data.get('duration', 0)

    # 更新学习会话（如果有session_id）
    if session_id:
        session = StudySession.query.get(session_id)
        if session and session.student_id == current_user.id:
            session.end_time = datetime.utcnow()
            session.duration_seconds = duration
            db.session.commit()

    # 更新或创建学习记录：查询该学生该知识点的最新记录
    record = LearningRecord.query.filter_by(
        student_id=current_user.id, kp_id=kp_id
    ).order_by(LearningRecord.id.desc()).first()

    if not record:
        # 没有记录时创建新记录
        record = LearningRecord(student_id=current_user.id, kp_id=kp_id)
        db.session.add(record)

    # 更新学习时长（累加）和进度（取最大值）
    record.study_duration = (record.study_duration or 0) + duration
    record.progress_percent = max(record.progress_percent or 0, progress)
    # 进度达到95%自动标记为已完成
    if record.status == 'studying' and progress >= 95:
        record.status = 'completed'
    db.session.commit()

    # 使缓存失效，确保下次查询时获取最新数据
    invalidate_student_cache(current_user.id)
    return jsonify({'status': 'ok'})


@student_bp.route('/learn/<int:kp_id>/submit_quiz', methods=['POST'])
@login_required
@student_required
def submit_quiz(kp_id):
    """提交测验答案
    
    计算得分、保存提交记录、检测薄弱点、可选获取AI分析
    
    参数:
        kp_id: 知识点ID（URL路径参数）
    """
    # 获取JSON请求数据
    data = request.get_json() or {}
    answers_data = data.get('answers', {})  # {question_id: answer}
    time_spent = data.get('time_spent', 0)
    need_ai_explanation = data.get('need_ai_explanation', False)

    # 获取该知识点的活跃题目
    questions = QuizQuestion.query.filter_by(kp_id=kp_id, is_active=True).all()
    if not questions:
        return jsonify({'error': '该知识点暂无题目'}), 400

    # 计算得分和答题详情
    correct_count = 0
    total = len(questions)
    answer_details = []

    # 获取知识点对象（用于AI分析）
    kp = KnowledgePoint.query.get_or_404(kp_id)

    # 遍历每道题目进行批改
    for q in questions:
        student_ans = answers_data.get(str(q.id), '').strip().upper()
        is_correct = student_ans == q.correct_answer.upper()
        if is_correct:
            correct_count += 1
        answer_details.append({
            'question_id': q.id,
            'student_answer': student_ans,
            'correct_answer': q.correct_answer,
            'is_correct': is_correct,
            'explanation': q.explanation or '',
            'question_text': q.question_text
        })

    # 计算总分（正确率 * 100）
    score = (correct_count / total) * 100 if total > 0 else 0

    # 保存测验记录到学习记录
    record = LearningRecord.query.filter_by(
        student_id=current_user.id, kp_id=kp_id
    ).order_by(LearningRecord.id.desc()).first()

    if not record:
        record = LearningRecord(student_id=current_user.id, kp_id=kp_id)
        db.session.add(record)

    record.quiz_score = score
    record.quiz_attempts = (record.quiz_attempts or 0) + 1
    record.correct_count = correct_count
    record.total_questions = total
    record.status = 'completed'
    db.session.flush()  # 刷新以获取record.id（用于关联提交记录）

    # 保存测验提交记录
    submission = QuizSubmission(
        student_id=current_user.id,
        kp_id=kp_id,
        learning_record_id=record.id,
        total_score=score,
        time_spent=time_spent
    )
    db.session.add(submission)
    db.session.flush()  # 刷新以获取submission.id（用于关联答题详情）

    # 保存每题的作答详情
    for detail in answer_details:
        qa = QuizAnswer(
            submission_id=submission.id,
            question_id=detail['question_id'],
            student_answer=detail['student_answer'],
            is_correct=detail['is_correct'],
            score=100.0 / total if detail['is_correct'] else 0
        )
        db.session.add(qa)

    db.session.commit()

    # 触发薄弱点检测（带数据库写入），更新薄弱点记录
    from services.diagnosis import detect_weak_points_with_db_write
    detect_weak_points_with_db_write(current_user.id)

    # 组装响应数据
    response = {
        'score': format_score(score),
        'correct_count': correct_count,
        'total': total,
        'passed': score >= 60,
        'details': answer_details
    }

    # 如果需要AI分析，调用LLM服务生成详细解析
    if need_ai_explanation:
        try:
            ai_explanation = llm_service.explain_quiz_result(
                kp.name, score, correct_count, total, answer_details
            )
            response['ai_explanation'] = ai_explanation
        except Exception as e:
            response['ai_explanation'] = None
            current_app.logger.error(f"AI explanation error: {e}")

    return jsonify(response)


@student_bp.route('/knowledge_graph')
@login_required
@student_required
def knowledge_graph():
    """知识图谱页面
    
    展示知识点之间的关系图谱（通过ECharts渲染）
    """
    return render_template('student/knowledge_graph.html')


@student_bp.route('/diagnosis')
@login_required
@student_required
def diagnosis():
    """薄弱点诊断页面
    
    调用detect_weak_points获取多维度薄弱点分析结果并展示
    """
    try:
        weak_analysis = detect_weak_points(current_user.id)
    except Exception as e:
        # 异常时返回空分析结果和错误信息，避免页面崩溃
        weak_analysis = {'error': str(e), 'summary': {}, 'absolute_weak': [],
                         'relative_weak': [], 'high_risk_weak': [], 'forgetting_trend': []}
    return render_template('student/diagnosis.html', weak_analysis=weak_analysis)


@student_bp.route('/diagnosis/ai_analysis', methods=['POST'])
@login_required
@student_required
def diagnosis_ai_analysis():
    """异步获取AI薄弱点分析（AJAX接口）
    
    调用LLM服务对薄弱点进行自然语言分析和解释
    """
    from services.diagnosis import get_ai_weak_analysis, detect_weak_points
    data = request.get_json() or {}
    weak_analysis = data.get('weak_analysis')
    
    # 如果前端未传入分析结果，重新计算
    if not weak_analysis:
        weak_analysis = detect_weak_points(current_user.id)
    
    # 调用LLM服务获取AI分析
    ai_analysis = get_ai_weak_analysis(current_user.id, weak_analysis)
    return jsonify({'ai_analysis': ai_analysis})


@student_bp.route('/recommendations')
@login_required
@student_required
def recommendations():
    """推荐列表页面
    
    展示个性化学习推荐（Top-5）
    """
    error_msg = None
    try:
        recs = generate_recommendations(current_user.id, top_n=5)
    except Exception as e:
        recs = []
        error_msg = str(e)
        current_app.logger.error(f"推荐生成失败 (student={current_user.id}): {e}", exc_info=True)
    return render_template('student/recommendations.html', recommendations=recs, error_msg=error_msg)


@student_bp.route('/qa')
@login_required
@student_required
def qa():
    """智能问答页面
    
    提供自然语言问答界面，学生可以提问学习相关问题
    """
    return render_template('student/qa.html')


@student_bp.route('/qa/ask', methods=['POST'])
@login_required
@student_required
def qa_ask():
    """智能问答接口（AJAX）
    
    接收学生问题，调用LLM服务返回答案
    
    请求体:
        { "question": "问题内容" }
    """
    question = request.get_json().get('question', '').strip()
    if not question:
        return jsonify({'error': 'question required'}), 400
    
    # 构建上下文信息（包含学生ID，便于LLM了解学生学习情况）
    context = {'student_id': current_user.id}
    try:
        answer = llm_service.answer_learning_question(question, context)
        return jsonify({'success': True, 'answer': answer, 'question': question})
    except Exception as e:
        import traceback
        current_app.logger.error(f"qa_ask error: {str(e)}")
        current_app.logger.error(f"Full traceback:\n{traceback.format_exc()}")
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@student_bp.route('/plan')
@login_required
@student_required
def learning_plan():
    """学习计划页面
    
    展示个性化学习计划，包含薄弱点分析和推荐
    """
    try:
        plan_data = _get_student_plan_data(current_user.id)
    except Exception as e:
        current_app.logger.error(f"获取学习计划数据失败 (student={current_user.id}): {e}", exc_info=True)
        # 异常时使用默认空数据，避免页面崩溃
        plan_data = {
            'recommendations': [],
            'weak_analysis': {'absolute_weak': [], 'relative_weak': [], 'high_risk_weak': [], 'forgetting_trend': []},
            'student_data': {'name': current_user.real_name, 'avg_score': 0, 'studied_count': 0, 'weak_count': 0, 'progress': 0}
        }
        flash(f'获取学习数据出错: {str(e)}', 'danger')
    
    # 渲染学习计划页面
    return render_template('student/plan.html',
                            recommendations=plan_data['recommendations'],
                            weak_analysis=plan_data['weak_analysis'],
                            student_data=plan_data['student_data'],
                            plan_content=None)


@student_bp.route('/plan/generate', methods=['POST'])
@login_required
@student_required
def generate_plan():
    """生成学习计划内容（AJAX接口）
    
    调用LLM服务生成个性化学习计划文本，并缓存结果供PDF导出使用
    """
    try:
        plan_data = _get_student_plan_data(current_user.id)
        plan_content = llm_service.generate_learning_plan_content(
            plan_data['student_data'], plan_data['recommendations'])
        
        # 将生成的计划内容缓存到模块级缓存中，供PDF导出使用
        if current_user.id in _student_plan_cache:
            _student_plan_cache[current_user.id]['plan_content'] = plan_content
        
        return jsonify({'plan_content': plan_content})
    except Exception as e:
        current_app.logger.error(f"生成学习计划失败 (student={current_user.id}): {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@student_bp.route('/plan/export_pdf')
@login_required
@student_required
def export_pdf():
    """导出学习计划PDF
    
    生成PDF文件并提供下载，优先使用已缓存的plan_content确保与前端一致
    """
    try:
        plan_data = _get_student_plan_data(current_user.id)
    except Exception as e:
        current_app.logger.error(f"导出PDF获取数据失败 (student={current_user.id}): {e}", exc_info=True)
        flash(f'获取学习数据出错: {str(e)}', 'danger')
        return redirect(url_for('student.learning_plan'))
    
    # 复制学生数据并补充薄弱点数量
    student_data = plan_data['student_data'].copy()
    student_data['weak_count'] = len(plan_data['weak_analysis'].get('absolute_weak', []))

    try:
        # 优先使用缓存中的plan_content，确保与前端页面显示一致
        plan_content = plan_data.get('plan_content')
        if not plan_content:
            # 如果缓存中没有，才重新调用LLM生成
            plan_content = llm_service.generate_learning_plan_content(
                student_data, plan_data['recommendations'])

        # 生成PDF字节流（调用PDF生成器）
        pdf_bytes = generate_learning_plan_pdf(
            student_data, plan_data['weak_analysis'], plan_data['recommendations'], plan_content)

        # 构建响应（设置正确的Content-Type和文件名）
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        filename = f'learning_plan_{current_user.username}_{datetime.now().strftime("%Y%m%d")}.pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        current_app.logger.error(f"生成PDF失败 (student={current_user.id}): {e}", exc_info=True)
        flash(f'PDF生成失败: {str(e)}', 'danger')
        return redirect(url_for('student.learning_plan'))


@student_bp.route('/ai_advice')
@login_required
@student_required
def ai_advice():
    """获取AI个性化建议（AJAX接口）
    
    根据薄弱点分析和推荐列表生成学习建议
    """
    weak_analysis = detect_weak_points(current_user.id)
    recs = generate_recommendations(current_user.id, top_n=3, weak_analysis=weak_analysis)
    advice = llm_service.generate_student_advice(
        current_user.real_name, weak_analysis, recs)
    return jsonify({'advice': advice})