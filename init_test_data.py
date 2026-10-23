# -*- coding: utf-8 -*-
"""
测试学生数据初始化脚本

为测试学生创建涵盖所有薄弱情况的学习记录：
1. 绝对薄弱（加权分 < 60）—— 多个知识点
2. 相对薄弱（低于个人平均20%）—— 多个知识点
3. 高危薄弱（薄弱且为其他知识点前置）—— 多个知识点
4. 遗忘趋势（学习次数增加但分数下降）—— 多个知识点
5. 已掌握（加权分 >= 60）—— 多个知识点
6. 部分掌握（加权分 40-59）—— 多个知识点
7. 未学习 —— 剩余知识点

使用方法：
    python init_test_data.py
"""
import os
import sys
from datetime import datetime, timedelta

# 确保项目根目录在path中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db
from models.user import User
from models.knowledge_point import KnowledgePoint, LearningMaterial, QuizQuestion
from models.learning_record import LearningRecord, QuizSubmission, QuizAnswer, StudySession
from models.prerequisite import Prerequisite, WeakPointRecord, RecommendationRecord
from services.diagnosis import calculate_weighted_score, detect_weak_points_with_db_write


def clear_existing_data(student):
    """清除测试学生的旧数据（学习记录、测验提交、薄弱点、推荐记录）"""
    print(f"  清除 {student.real_name} 的旧学习记录...")
    QuizSubmission.query.filter_by(student_id=student.id).delete()
    LearningRecord.query.filter_by(student_id=student.id).delete()
    WeakPointRecord.query.filter_by(student_id=student.id).delete()
    RecommendationRecord.query.filter_by(student_id=student.id).delete()
    StudySession.query.filter_by(student_id=student.id).delete()
    db.session.commit()


def create_or_get_student():
    """创建或获取测试学生账号"""
    student = User.query.filter_by(username='test_student').first()
    if student:
        print(f"  已存在用户: {student.real_name} (ID={student.id})")
        return student

    student = User(
        username='test_student',
        real_name='测试学生',
        role='student',
        email='student@test.com',
        student_id='20240001',
        department='计算机科学与技术学院',
        is_active=True
    )
    student.set_password('123456')
    db.session.add(student)
    db.session.commit()
    print(f"  创建用户: {student.real_name} (ID={student.id})")
    return student


def create_or_get_teacher():
    """创建或获取测试教师账号"""
    teacher = User.query.filter_by(username='teacher_test').first()
    if teacher:
        return teacher

    teacher = User(
        username='teacher_test',
        real_name='测试教师',
        role='teacher',
        email='teacher@test.com',
        teacher_id='T0001',
        department='计算机科学与技术学院',
        is_active=True
    )
    teacher.set_password('123456')
    db.session.add(teacher)
    db.session.commit()
    return teacher


def get_all_kps():
    """获取所有活跃知识点，按章节排序"""
    return KnowledgePoint.query.filter_by(is_active=True).order_by(
        KnowledgePoint.chapter_order, KnowledgePoint.id
    ).all()


def get_prereq_map():
    """获取前驱关系映射: {kp_id: [(prereq_kp_id, relation_type), ...]}"""
    all_prereqs = Prerequisite.query.all()
    prereq_map = {}
    for p in all_prereqs:
        prereq_map.setdefault(p.target_kp_id, []).append(
            (p.prerequisite_kp_id, p.relation_type)
        )
    return prereq_map


def get_blocked_map():
    """获取后继关系映射: {kp_id: [target_kp_id, ...]}（仅must关系）"""
    all_prereqs = Prerequisite.query.filter_by(relation_type='must').all()
    blocked_map = {}
    for p in all_prereqs:
        blocked_map.setdefault(p.prerequisite_kp_id, []).append(p.target_kp_id)
    return blocked_map


def create_learning_record(student_id, kp_id, teacher_id, quiz_score=None,
                            video_progress=0, text_progress=0, text_read_duration=0,
                            text_total_length=500, study_duration=300,
                            quiz_attempts=0, correct_count=None, total_questions=5,
                            status='completed', days_ago=0):
    """创建一条学习记录

    加权分 = video_progress * 0.35 + text_progress * 0.15 + quiz_score * 0.50
    所以要控制加权分，需要合理设置三个维度
    """
    record = LearningRecord(
        student_id=student_id,
        kp_id=kp_id,
        study_duration=study_duration,
        progress_percent=max(video_progress, text_progress),
        video_progress=video_progress,
        watched_duration=int(study_duration * 0.6),
        text_progress=text_progress,
        text_read_duration=text_read_duration,
        text_total_length=text_total_length,
        quiz_score=quiz_score,
        quiz_attempts=quiz_attempts,
        correct_count=correct_count if correct_count is not None else (
            int(quiz_score / 100 * total_questions) if quiz_score else 0
        ),
        total_questions=total_questions,
        status=status,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
        updated_at=datetime.utcnow() - timedelta(days=days_ago)
    )
    db.session.add(record)
    return record


def create_quiz_submission(student_id, kp_id, record_id, score, days_ago):
    """创建测验提交记录"""
    submission = QuizSubmission(
        student_id=student_id,
        kp_id=kp_id,
        learning_record_id=record_id,
        total_score=score,
        time_spent=300,
        submitted_at=datetime.utcnow() - timedelta(days=days_ago)
    )
    db.session.add(submission)


def seed_test_data():
    """主函数：为测试学生创建测试数据"""

    print("=" * 60)
    print("测试学生数据初始化脚本")
    print("=" * 60)

    # 1. 创建/获取用户
    print("\n[1/6] 创建用户...")
    student = create_or_get_student()
    teacher = create_or_get_teacher()

    # 2. 清除旧数据
    print("\n[2/6] 清除旧数据...")
    clear_existing_data(student)

    # 3. 获取所有知识点和前驱关系
    print("\n[3/6] 获取知识点和前驱关系...")
    all_kps = get_all_kps()
    if not all_kps:
        print("  错误：数据库中没有知识点！请先通过管理后台或Neo4j导入知识点。")
        return

    print(f"  共 {len(all_kps)} 个知识点")
    prereq_map = get_prereq_map()
    blocked_map = get_blocked_map()

    # 找出有后继的知识点（用于高危薄弱）
    kps_with_successors = [kp_id for kp_id, targets in blocked_map.items() if len(targets) > 0]
    # 找出有前驱的知识点
    kps_with_prereqs = list(prereq_map.keys())

    # 4. 分类知识点，为每种薄弱情况分配
    print("\n[4/6] 分配知识点场景...")

    # 按ID排序的知识点列表
    kp_list = list(all_kps)
    n = len(kp_list)

    # 场景分配策略：
    # - 前1/3知识点中选一些做"已掌握"和"部分掌握"
    # - 中间1/3做"绝对薄弱"、"高危薄弱"
    # - 最后1/3做"相对薄弱"、"遗忘趋势"、"未学习"

    # 已掌握（加权分 >= 60）：选5个知识点
    mastered_kps = kp_list[:min(5, n)]
    # 部分掌握（加权分 40-59）：选3个知识点
    partial_kps = kp_list[5:min(8, n)] if n > 5 else []
    # 绝对薄弱+高危薄弱（加权分 < 60 且有后继）：选有后继的知识点
    candidate_high_risk = [kp for kp in kp_list[8:] if kp.id in kps_with_successors]
    high_risk_kps = candidate_high_risk[:min(3, len(candidate_high_risk))]
    # 绝对薄弱（无后继的知识点）
    candidate_abs_weak = [kp for kp in kp_list[8:] if kp.id not in kps_with_successors and kp not in high_risk_kps]
    absolute_weak_kps = candidate_abs_weak[:min(3, len(candidate_abs_weak))]
    # 相对薄弱（分数低于个人平均20%）
    relative_weak_kps = candidate_abs_weak[3:min(5, len(candidate_abs_weak))] if len(candidate_abs_weak) > 3 else []
    # 遗忘趋势（需要多次测验，分数递减）
    forgetting_kps = kp_list[min(13, n):min(16, n)] if n > 13 else []
    # 未学习：剩余知识点
    used_kps = set()
    for kp in mastered_kps + partial_kps + high_risk_kps + absolute_weak_kps + relative_weak_kps + forgetting_kps:
        used_kps.add(kp.id)
    unlearned_kps = [kp for kp in kp_list if kp.id not in used_kps]

    print(f"  已掌握: {len(mastered_kps)} 个")
    print(f"  部分掌握: {len(partial_kps)} 个")
    print(f"  高危薄弱: {len(high_risk_kps)} 个")
    print(f"  绝对薄弱: {len(absolute_weak_kps)} 个")
    print(f"  相对薄弱: {len(relative_weak_kps)} 个")
    print(f"  遗忘趋势: {len(forgetting_kps)} 个")
    print(f"  未学习: {len(unlearned_kps)} 个")

    # 5. 创建学习记录
    print("\n[5/6] 创建学习记录...")

    student_id = student.id

    # === 已掌握（加权分 >= 60）===
    # 加权分 = video*0.35 + text*0.15 + quiz*0.50
    # 要让加权分=80: video=80, text=80, quiz=80 => 80*0.35+80*0.15+80*0.50 = 80
    for i, kp in enumerate(mastered_kps):
        score = 75 + (i * 5)  # 75, 80, 85, 90, 95
        if score > 100:
            score = 95
        create_learning_record(
            student_id=student_id, kp_id=kp.id, teacher_id=teacher.id,
            quiz_score=float(score), video_progress=float(score),
            text_progress=float(score), text_read_duration=300,
            text_total_length=500, study_duration=600 + i * 60,
            quiz_attempts=1 + (i % 2), correct_count=int(score / 100 * 5),
            total_questions=5, status='completed', days_ago=20 - i * 2
        )
        print(f"  已掌握: {kp.name} (加权分≈{score})")

    # === 部分掌握（加权分 40-59）===
    for i, kp in enumerate(partial_kps):
        score = 45 + (i * 5)  # 45, 50, 55
        create_learning_record(
            student_id=student_id, kp_id=kp.id, teacher_id=teacher.id,
            quiz_score=float(score), video_progress=float(score),
            text_progress=float(score), text_read_duration=200,
            text_total_length=500, study_duration=400,
            quiz_attempts=1, correct_count=int(score / 100 * 5),
            total_questions=5, status='completed', days_ago=15 - i
        )
        print(f"  部分掌握: {kp.name} (加权分≈{score})")

    # === 高危薄弱（加权分 < 60 且有后继知识点）===
    for i, kp in enumerate(high_risk_kps):
        score = 25 + (i * 10)  # 25, 35, 45
        create_learning_record(
            student_id=student_id, kp_id=kp.id, teacher_id=teacher.id,
            quiz_score=float(score), video_progress=float(score),
            text_progress=float(score), text_read_duration=150,
            text_total_length=500, study_duration=300,
            quiz_attempts=1, correct_count=int(score / 100 * 5),
            total_questions=5, status='completed', days_ago=10 - i
        )
        blocked_names = [KnowledgePoint.query.get(tid).name for tid in blocked_map.get(kp.id, [])][:3]
        print(f"  高危薄弱: {kp.name} (加权分≈{score}, 阻塞: {blocked_names})")

    # === 绝对薄弱（加权分 < 60，无后继或未选为高危）===
    for i, kp in enumerate(absolute_weak_kps):
        score = 20 + (i * 15)  # 20, 35, 50
        create_learning_record(
            student_id=student_id, kp_id=kp.id, teacher_id=teacher.id,
            quiz_score=float(score), video_progress=float(score),
            text_progress=float(score), text_read_duration=100,
            text_total_length=500, study_duration=200,
            quiz_attempts=1, correct_count=int(score / 100 * 5),
            total_questions=5, status='completed', days_ago=8 - i
        )
        print(f"  绝对薄弱: {kp.name} (加权分≈{score})")

    # === 相对薄弱（分数远低于个人平均）===
    # 个人平均大约在 55-65 之间，相对薄弱需要低于平均*0.8 ≈ 44-52
    # 但又不能太低（否则也成为绝对薄弱），所以设为 35-50
    for i, kp in enumerate(relative_weak_kps):
        score = 35 + (i * 10)  # 35, 45
        create_learning_record(
            student_id=student_id, kp_id=kp.id, teacher_id=teacher.id,
            quiz_score=float(score), video_progress=float(score),
            text_progress=float(score), text_read_duration=120,
            text_total_length=500, study_duration=250,
            quiz_attempts=1, correct_count=int(score / 100 * 5),
            total_questions=5, status='completed', days_ago=5 - i
        )
        print(f"  相对薄弱: {kp.name} (加权分≈{score})")

    # === 遗忘趋势（多次测验，分数递减）===
    # 需要 >= 2 次记录，且 slope < -0.5
    # 第一次高分，后面递减
    for i, kp in enumerate(forgetting_kps):
        # 创建3条记录：第一次80分，第二次60分，第三次35分
        scores_sequence = [80, 55, 30]
        for j, score in enumerate(scores_sequence):
            record = create_learning_record(
                student_id=student_id, kp_id=kp.id, teacher_id=teacher.id,
                quiz_score=float(score), video_progress=float(score),
                text_progress=float(score), text_read_duration=200,
                text_total_length=500, study_duration=300,
                quiz_attempts=j + 1, correct_count=int(score / 100 * 5),
                total_questions=5, status='completed',
                days_ago=30 - j * 10  # 30天前, 20天前, 10天前
            )
            db.session.flush()  # 获取record.id
            create_quiz_submission(student_id, kp.id, record.id, score, 30 - j * 10)
        print(f"  遗忘趋势: {kp.name} (分数序列: {scores_sequence})")

    # === 未学习 ===
    for kp in unlearned_kps:
        # 不创建任何记录
        pass
    print(f"  未学习: {len(unlearned_kps)} 个知识点（不创建记录）")

    # 提交所有记录
    db.session.commit()

    # 6. 触发薄弱点检测
    print("\n[6/6] 触发薄弱点检测...")
    weak_analysis = detect_weak_points_with_db_write(student_id)

    print("\n" + "=" * 60)
    print("薄弱点检测结果：")
    print(f"  个人平均分: {weak_analysis['summary'].get('personal_avg', 0):.1f}")
    print(f"  绝对薄弱: {len(weak_analysis['absolute_weak'])} 个")
    for w in weak_analysis['absolute_weak']:
        print(f"    - {w['kp_name']} ({w['score']:.1f}分)")
    print(f"  相对薄弱: {len(weak_analysis['relative_weak'])} 个")
    for w in weak_analysis['relative_weak']:
        print(f"    - {w['kp_name']} ({w['score']:.1f}分, 差{w['gap_ratio']}%)")
    print(f"  高危薄弱: {len(weak_analysis['high_risk_weak'])} 个")
    for w in weak_analysis['high_risk_weak']:
        print(f"    - {w['kp_name']} ({w['score']:.1f}分, 阻塞{w['blocks_count']}个)")
    print(f"  遗忘趋势: {len(weak_analysis['forgetting_trend'])} 个")
    for w in weak_analysis['forgetting_trend']:
        print(f"    - {w['kp_name']} (斜率{w['slope']}, 最高{w['best_score']:.0f}→现{w['score']:.0f})")

    # 验证加权分计算
    print("\n加权分验证：")
    all_records = LearningRecord.query.filter_by(student_id=student_id).all()
    subq = db.session.query(
        LearningRecord.kp_id,
        db.func.max(LearningRecord.id).label('max_id')
    ).filter_by(student_id=student_id).group_by(LearningRecord.kp_id).subquery()
    latest_records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()
    for r in latest_records:
        kp = KnowledgePoint.query.get(r.kp_id)
        ws = calculate_weighted_score(r)
        print(f"  {kp.name}: quiz={r.quiz_score}, video={r.video_progress}, text={r.text_progress} -> 加权={ws}")

    print("\n" + "=" * 60)
    print("测试数据创建完成！")
    print(f"  登录账号: test_student")
    print(f"  登录密码: 123456")
    print(f"  学生姓名: {student.real_name}")
    print("=" * 60)


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        seed_test_data()
