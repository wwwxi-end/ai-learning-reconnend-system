"""
个性化学习路径推荐服务

基于以下维度生成 Top-5 推荐：
- 薄弱点权重（越薄弱越优先）
- 前驱关系（前驱未掌握则先推前驱）
- 知识点重要程度
- 遗忘衰减（久未复习则优先）
- 是否为高危薄弱（阻塞后续学习）
"""
import json
from datetime import datetime, timedelta
from sqlalchemy import func
from models import db
from models.knowledge_point import KnowledgePoint
from models.learning_record import LearningRecord
from models.prerequisite import Prerequisite, WeakPointRecord, RecommendationRecord
from services.diagnosis import detect_weak_points


def generate_recommendations(student_id: int, top_n: int = 5, weak_analysis: dict = None) -> list:
    """
    生成Top-N个性化学习推荐
    返回带有推荐理由的列表
    weak_analysis: 可选参数，若已计算过薄弱分析可传入以避免重复计算
    """
    # 1. 先执行薄弱点检测（如果未提供）
    if weak_analysis is None:
        weak_analysis = detect_weak_points(student_id)

    # 2. 获取所有知识点及学生成绩
    all_kps = KnowledgePoint.query.filter_by(is_active=True).all()
    kp_scores = _get_student_kp_scores(student_id)

    # 批量预加载所有前驱关系（修复原N+1查询）
    all_kp_ids = [kp.id for kp in all_kps]
    all_prereqs = Prerequisite.query.filter(
        Prerequisite.target_kp_id.in_(all_kp_ids)
    ).all() if all_kp_ids else []
    # 按目标知识点分组: {target_kp_id: [prerequisite_kp_id, ...]}
    prereq_map = {}
    # 按前驱知识点分组: {prerequisite_kp_id: [target_kp_id, ...]}
    blocked_map = {}
    all_prereq_kp_ids = set()
    for p in all_prereqs:
        prereq_map.setdefault(p.target_kp_id, []).append((p.prerequisite_kp_id, p.relation_type))
        blocked_map.setdefault(p.prerequisite_kp_id, []).append((p.target_kp_id, p.relation_type))
        all_prereq_kp_ids.add(p.prerequisite_kp_id)

    # 批量获取所有被引用的知识点（前驱和后继），避免逐个查询
    all_referenced_ids = set(all_kp_ids) | all_prereq_kp_ids
    referenced_kps = {kp.id: kp for kp in KnowledgePoint.query.filter(
        KnowledgePoint.id.in_(list(all_referenced_ids))
    ).all()} if all_referenced_ids else {}

    # 3. 计算每个知识点的推荐分数
    scored_kps = []
    for kp in all_kps:
        score_info = _calculate_recommendation_score(
            kp, student_id, kp_scores, weak_analysis,
            blocked_map=blocked_map, referenced_kps=referenced_kps
        )
        if score_info['recommend_score'] > 0:
            scored_kps.append(score_info)

    # 4. 按推荐分数排序，取Top-N
    scored_kps.sort(key=lambda x: x['recommend_score'], reverse=True)
    top_recommendations = scored_kps[:top_n]

    # 5. 检查前驱关系，若前驱未掌握则插入前驱
    final_recommendations = _ensure_prerequisites(
        top_recommendations, student_id, kp_scores, top_n,
        prereq_map=prereq_map, referenced_kps=referenced_kps
    )

    # 6. 生成推荐理由
    result = []
    for rank, rec in enumerate(final_recommendations[:top_n], 1):
        reason, reason_tags = _generate_reason(rec)
        result.append({
            'rank': rank,
            'kp_id': rec['kp_id'],
            'kp_name': rec['kp_name'],
            'kp_chapter': rec.get('chapter', ''),
            'current_score': rec.get('current_score'),
            'recommend_score': round(rec['recommend_score'], 3),
            'reason': reason,
            'reason_tags': reason_tags,
            'difficulty': rec.get('difficulty', 3),
            'estimated_minutes': rec.get('estimated_minutes', 30),
            'prerequisites_met': rec.get('prerequisites_met', True)
        })

    # 7. 保存推荐记录
    _save_recommendation_records(student_id, result)

    return result


def _get_student_kp_scores(student_id: int) -> dict:
    """获取学生各知识点最新成绩（使用加权分数，与诊断逻辑一致）"""
    from services.diagnosis import calculate_weighted_score

    subq = db.session.query(
        LearningRecord.kp_id,
        func.max(LearningRecord.id).label('max_id')
    ).filter(
        LearningRecord.student_id == student_id
    ).group_by(LearningRecord.kp_id).subquery()

    records = db.session.query(LearningRecord).join(
        subq, LearningRecord.id == subq.c.max_id
    ).all()

    result = {}
    for r in records:
        result[r.kp_id] = {
            'score': calculate_weighted_score(r),
            'attempts': r.quiz_attempts or 0,
            'last_study': r.updated_at,
            'status': r.status
        }
    return result


def _calculate_recommendation_score(kp, student_id, kp_scores, weak_analysis,
                                     blocked_map=None, referenced_kps=None):
    """为单个知识点计算推荐分数

    优化说明：使用预加载的 blocked_map 和 referenced_kps 避免N+1查询
    """
    kp_id = kp.id
    score_info = kp_scores.get(kp_id, {})
    current_score = score_info.get('score')
    last_study = score_info.get('last_study')

    recommend_score = 0.0
    flags = []

    # === 维度1：绝对薄弱加权 ===
    absolute_weak = next(
        (w for w in weak_analysis['absolute_weak'] if w['kp_id'] == kp_id), None
    )
    if absolute_weak:
        gap = absolute_weak['gap']
        recommend_score += 3.0 + (gap / 60.0) * 2.0  # 最高 5.0
        flags.append('absolute_weak')

    # === 维度2：相对薄弱加权 ===
    relative_weak = next(
        (w for w in weak_analysis['relative_weak'] if w['kp_id'] == kp_id), None
    )
    if relative_weak:
        recommend_score += 1.5
        flags.append('relative_weak')

    # === 维度3：高危薄弱加权（会阻塞后续学习）===
    high_risk = next(
        (w for w in weak_analysis['high_risk_weak'] if w['kp_id'] == kp_id), None
    )
    blocks_kps = []
    if high_risk:
        recommend_score += high_risk['blocks_count'] * 0.8
        flags.append('high_risk')
        # 使用预加载数据，不再逐个查询数据库
        blocked_entries = (blocked_map or {}).get(kp_id, [])
        for target_id, rel_type in blocked_entries:
            if rel_type == 'must':
                succ_kp = (referenced_kps or {}).get(target_id)
                if succ_kp:
                    blocks_kps.append(succ_kp.name)

    # === 维度4：遗忘趋势加权 ===
    forgetting = next(
        (w for w in weak_analysis['forgetting_trend'] if w['kp_id'] == kp_id), None
    )
    best_score = None
    if forgetting:
        slope_penalty = abs(forgetting['slope']) * 0.3
        recommend_score += 2.0 + slope_penalty
        flags.append('forgetting')
        best_score = forgetting.get('best_score', current_score)

    # === 维度5：未学习的知识点（适当加权）===
    if current_score is None:
        recommend_score += 1.0
        flags.append('not_studied')

    # === 维度6：知识点重要程度加权 ===
    recommend_score += kp.importance * 0.2

    # === 维度7：遗忘衰减（久未复习）===
    if last_study:
        days_since = (datetime.utcnow() - last_study).days
        if days_since > 7:
            recommend_score += min(days_since / 30.0, 1.5)
            if 'not_studied' not in flags:
                flags.append('need_review')

    return {
        'kp_id': kp_id,
        'kp_name': kp.name,
        'chapter': kp.chapter,
        'chapter_order': kp.chapter_order,
        'current_score': current_score,
        'difficulty': kp.difficulty,
        'importance': kp.importance,
        'estimated_minutes': kp.estimated_minutes,
        'recommend_score': recommend_score,
        'flags': flags,
        'blocks_kps': blocks_kps,
        'best_score': best_score
    }


def _ensure_prerequisites(recommendations, student_id, kp_scores, top_n,
                           prereq_map=None, referenced_kps=None):
    """
    检查推荐列表中的知识点是否满足前驱条件，
    若前驱未掌握，将前驱插到更前面

    优化说明：使用预加载的 prereq_map 和 referenced_kps 避免N+1查询
    """
    result = []
    added_ids = set()

    for rec in recommendations:
        kp_id = rec['kp_id']
        # 使用预加载数据获取该知识点的必须前驱
        all_prereq_entries = (prereq_map or {}).get(kp_id, [])
        must_prereq_ids = [pid for pid, rel_type in all_prereq_entries if rel_type == 'must']

        unmet_prereqs = []
        for pid in must_prereq_ids:
            prereq_score_info = kp_scores.get(pid, {})
            prereq_score = prereq_score_info.get('score', None)
            # 前驱未达标（<60分或未学习）
            if prereq_score is None or prereq_score < 60:
                prereq_kp = (referenced_kps or {}).get(pid)
                if prereq_kp and pid not in added_ids:
                    unmet_prereqs.append({
                        'kp_id': pid,
                        'kp_name': prereq_kp.name,
                        'chapter': prereq_kp.chapter,
                        'chapter_order': prereq_kp.chapter_order,
                        'current_score': prereq_score,
                        'difficulty': prereq_kp.difficulty,
                        'importance': prereq_kp.importance,
                        'estimated_minutes': prereq_kp.estimated_minutes,
                        'recommend_score': rec['recommend_score'] + 0.5,  # 略高优先级
                        'flags': ['prerequisite_first'],
                        'prerequisites_met': True
                    })
                    added_ids.add(pid)

        # 先插入未满足的前驱
        for p_rec in unmet_prereqs:
            if len(result) < top_n:
                result.append(p_rec)

        # 再插入原知识点
        if kp_id not in added_ids and len(result) < top_n * 2:
            rec['prerequisites_met'] = len(unmet_prereqs) == 0
            result.append(rec)
            added_ids.add(kp_id)

    return result


def _generate_reason(rec: dict) -> tuple:
    """生成自然语言推荐理由"""
    flags = rec.get('flags', [])
    kp_name = rec['kp_name']
    score = rec.get('current_score')
    reasons = []
    tags = []

    if 'prerequisite_first' in flags:
        reasons.append(f"「{kp_name}」是你计划学习内容的前置知识，建议先掌握它")
        tags.append('前驱优先')

    if 'absolute_weak' in flags:
        reasons.append(f"你在「{kp_name}」的得分为 {score:.0f} 分，属于绝对薄弱（低于60分），急需加强")
        tags.append('绝对薄弱')

    if 'relative_weak' in flags:
        reasons.append(f"「{kp_name}」得分明显低于你的平均水平，需要重点补强")
        tags.append('相对薄弱')

    if 'high_risk' in flags:
        blocks = rec.get('blocks_kps', [])
        block_str = '、'.join(blocks[:3]) if blocks else '多个后续知识点'
        reasons.append(f"「{kp_name}」是 {block_str} 等知识点的前置，掌握它能解锁后续学习")
        tags.append('高危薄弱')

    if 'forgetting' in flags:
        best = rec.get('best_score', score)
        reasons.append(f"「{kp_name}」呈遗忘趋势（最高曾达{best:.0f}分，现降至{score:.0f}分），建议及时复习")
        tags.append('遗忘趋势')

    if 'not_studied' in flags:
        reasons.append(f"「{kp_name}」你尚未学习，建议纳入学习计划")
        tags.append('未学习')

    if 'need_review' in flags:
        reasons.append(f"「{kp_name}」已超过7天未复习，建议进行复习巩固")
        tags.append('需复习')

    if not reasons:
        reasons.append(f"「{kp_name}」是课程重要知识点，建议学习")
        tags.append('重要知识点')

    return '；'.join(reasons), json.dumps(tags, ensure_ascii=False)


def _save_recommendation_records(student_id: int, recommendations: list):
    """保存推荐记录"""
    # 删除旧推荐
    RecommendationRecord.query.filter_by(student_id=student_id).delete()

    for rec in recommendations:
        record = RecommendationRecord(
            student_id=student_id,
            kp_id=rec['kp_id'],
            rank=rec['rank'],
            score=rec['recommend_score'],
            reason=rec['reason'],
            reason_tags=rec.get('reason_tags', '[]'),
            generated_at=datetime.utcnow()
        )
        db.session.add(record)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_learning_path_for_kp(target_kp_id: int, student_id: int) -> dict:
    """
    给定目标知识点，生成从当前状态到该知识点的学习路径
    用于回答"我想学X，需要先学什么？"
    """
    kp_scores = _get_student_kp_scores(student_id)
    path = []
    visited = set()

    def dfs(kp_id):
        if kp_id in visited:
            return
        visited.add(kp_id)
        prereqs = Prerequisite.query.filter_by(
            target_kp_id=kp_id,
            relation_type='must'
        ).all()
        for p in prereqs:
            dfs(p.prerequisite_kp_id)

        kp = KnowledgePoint.query.get(kp_id)
        if kp:
            score_info = kp_scores.get(kp_id, {})
            current_score = score_info.get('score')
            path.append({
                'kp_id': kp_id,
                'kp_name': kp.name,
                'chapter': kp.chapter,
                'current_score': current_score,
                'mastered': current_score is not None and current_score >= 60,
                'is_target': kp_id == target_kp_id
            })

    dfs(target_kp_id)

    target_kp = KnowledgePoint.query.get(target_kp_id)
    return {
        'target_kp_id': target_kp_id,
        'target_kp_name': target_kp.name if target_kp else '',
        'path': path,
        'total_steps': len(path),
        'mastered_steps': sum(1 for p in path if p['mastered']),
        'remaining_steps': sum(1 for p in path if not p['mastered'])
    }
