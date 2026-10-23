"""
页面数据缓存服务
提供统一的缓存管理接口，支持页面级数据缓存、异步重建等功能
"""

import logging
from datetime import datetime
from extensions import cache

logger = logging.getLogger(__name__)


class PageCacheService:
    """
    页面数据缓存服务
    封装 Flask-Caching，提供页面级缓存管理
    """

    @classmethod
    def get_cached_or_compute(cls, user_id, cache_key, compute_func, timeout_seconds=300):
        """
        获取缓存数据，如果不存在则计算并缓存
        
        :param user_id: 用户ID（用于缓存键前缀）
        :param cache_key: 缓存键名
        :param compute_func: 计算函数，用于生成缓存数据
        :param timeout_seconds: 缓存超时时间（秒）
        :return: 缓存数据
        """
        full_key = f"{user_id}_{cache_key}"
        
        cached_data = cache.get(full_key)
        if cached_data is not None:
            logger.debug(f"Cache hit for {full_key}")
            return cached_data
        
        logger.debug(f"Cache miss for {full_key}, computing...")
        data = compute_func()
        
        if data is not None:
            cache.set(full_key, data, timeout=timeout_seconds)
        
        return data

    @classmethod
    def invalidate_cache(cls, user_id, cache_key):
        """
        使指定缓存失效
        
        :param user_id: 用户ID
        :param cache_key: 缓存键名
        """
        full_key = f"{user_id}_{cache_key}"
        cache.delete(full_key)
        logger.debug(f"Invalidated cache: {full_key}")

    @classmethod
    def invalidate_user_cache(cls, user_id):
        """
        使指定用户的所有缓存失效
        
        :param user_id: 用户ID
        """
        try:
            cache.delete_memoized_kwargs(invalidate_user_cache, user_id=user_id)
        except Exception:
            pass
        logger.debug(f"Invalidated all cache for user {user_id}")

    @classmethod
    def rebuild_all_cache(cls, student_id):
        """
        重建学生全部页面缓存
        
        :param student_id: 学生ID
        """
        logger.info(f"Rebuilding all cache for student {student_id}")
        
        from services.diagnosis import detect_weak_points
        
        weak_analysis = detect_weak_points(student_id)
        cache.set(f"{student_id}_weak_points", weak_analysis, timeout=300)

        cls.rebuild_dashboard_stats(student_id)
        cls.rebuild_chapter_radar(student_id)
        cls.rebuild_score_distribution(student_id)
        cls.rebuild_recommendations(student_id)
        cls.rebuild_graph_colored(student_id)
        cls.rebuild_forgetting_trend(student_id)

    @classmethod
    def rebuild_teacher_cache(cls, teacher_id):
        """
        重建教师端缓存
        
        :param teacher_id: 教师ID
        """
        logger.info(f"Rebuilding cache for teacher {teacher_id}")
        
        from services.diagnosis import get_class_weak_analysis
        
        class_analysis = get_class_weak_analysis(teacher_id)
        cache.set(f"{teacher_id}_class_weak_analysis", class_analysis, timeout=600)

    @classmethod
    def rebuild_dashboard_stats(cls, student_id):
        """重建仪表盘统计缓存"""
        logger.debug(f"Rebuilding dashboard stats for student {student_id}")
        
        from sqlalchemy import func
        from models.learning_record import LearningRecord
        from models.knowledge_point import KnowledgePoint
        
        try:
            avg_score = LearningRecord.query.filter_by(student_id=student_id).with_entities(
                func.avg(LearningRecord.quiz_score)
            ).scalar() or 0
            
            studied_count = LearningRecord.query.filter_by(student_id=student_id).with_entities(
                func.count(LearningRecord.kp_id.distinct())
            ).scalar() or 0
            
            total_kps = KnowledgePoint.query.filter_by(is_active=True).count()
            
            stats = {
                'avg_score': round(float(avg_score), 2),
                'studied_count': studied_count,
                'total_kps': total_kps,
                'progress': round(studied_count / total_kps * 100, 1) if total_kps else 0,
                'updated_at': datetime.now().isoformat()
            }
            
            cache.set(f"{student_id}_dashboard_stats", stats, timeout=120)
        except Exception as e:
            logger.error(f"Failed to rebuild dashboard stats: {e}")

    @classmethod
    def rebuild_weak_points(cls, student_id):
        """重建薄弱点缓存"""
        logger.debug(f"Rebuilding weak points for student {student_id}")
        
        from services.diagnosis import detect_weak_points
        
        try:
            weak_analysis = detect_weak_points(student_id)
            cache.set(f"{student_id}_weak_points", weak_analysis, timeout=300)
        except Exception as e:
            logger.error(f"Failed to rebuild weak points: {e}")

    @classmethod
    def rebuild_chapter_radar(cls, student_id):
        """重建章节雷达图缓存"""
        logger.debug(f"Rebuilding chapter radar for student {student_id}")
        
        from services.diagnosis import get_chapter_radar_data
        
        try:
            radar_data = get_chapter_radar_data(student_id)
            cache.set(f"{student_id}_chapter_radar", radar_data, timeout=300)
        except Exception as e:
            logger.error(f"Failed to rebuild chapter radar: {e}")

    @classmethod
    def rebuild_score_distribution(cls, student_id):
        """重建分数分布缓存"""
        logger.debug(f"Rebuilding score distribution for student {student_id}")
        
        from services.diagnosis import get_score_distribution
        
        try:
            dist_data = get_score_distribution(student_id)
            cache.set(f"{student_id}_score_distribution", dist_data, timeout=300)
        except Exception as e:
            logger.error(f"Failed to rebuild score distribution: {e}")

    @classmethod
    def rebuild_recommendations(cls, student_id):
        """重建推荐列表缓存"""
        logger.debug(f"Rebuilding recommendations for student {student_id}")
        
        from services.recommendation import generate_recommendations
        from services.diagnosis import detect_weak_points
        
        try:
            weak_analysis = detect_weak_points(student_id)
            recs = generate_recommendations(student_id, top_n=5, weak_analysis=weak_analysis)
            cache.set(f"{student_id}_recommendations", recs, timeout=300)
        except Exception as e:
            logger.error(f"Failed to rebuild recommendations: {e}")

    @classmethod
    def rebuild_graph_colored(cls, student_id):
        """重建知识图谱缓存"""
        logger.debug(f"Rebuilding graph colored for student {student_id}")
        
        from services.diagnosis import get_kp_mastery_dict
        
        try:
            mastery_dict = get_kp_mastery_dict(student_id)
            cache.set(f"{student_id}_graph_colored", mastery_dict, timeout=300)
        except Exception as e:
            logger.error(f"Failed to rebuild graph colored: {e}")

    @classmethod
    def rebuild_forgetting_trend(cls, student_id):
        """重建遗忘趋势缓存"""
        logger.debug(f"Rebuilding forgetting trend for student {student_id}")
        
        from services.diagnosis import get_forgetting_trend_data
        
        try:
            trend_data = get_forgetting_trend_data(student_id)
            cache.set(f"{student_id}_forgetting_trend", trend_data, timeout=300)
        except Exception as e:
            logger.error(f"Failed to rebuild forgetting trend: {e}")