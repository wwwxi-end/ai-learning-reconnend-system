"""
后台异步缓存重建服务
在数据变更后，异步重建受影响用户的页面数据缓存，确保下次页面切换时直接读取缓存数据。

核心策略：
1. 学生提交测验/记录进度后 → 异步重建该学生全部缓存
2. 学生登录时 → 预加载缓存（首次访问即有数据）
3. 缓存过期时 → 请求到达时按需重建（stale-while-revalidate）
"""

import threading
import logging
from models import db
from services.cache_service import PageCacheService

logger = logging.getLogger(__name__)


class BackgroundCacheBuilder:
    """后台缓存构建器 - 使用线程异步重建缓存"""

    @classmethod
    def rebuild_student_cache_async(cls, student_id):
        """
        异步重建学生全部页面缓存
        在新线程中执行，不阻塞当前请求的响应
        """
        thread = threading.Thread(
            target=cls._rebuild_student_cache,
            args=(student_id,),
            daemon=True
        )
        thread.start()
        logger.info(f"Started background cache rebuild for student {student_id}")

    @classmethod
    def _rebuild_student_cache(cls, student_id):
        """在后台线程中重建学生缓存"""
        try:
            # 使用新的Flask应用上下文（线程独立）
            from app import create_app
            app = create_app()
            with app.app_context():
                PageCacheService.rebuild_all_cache(student_id)
                logger.info(f"Completed cache rebuild for student {student_id}")
        except Exception as e:
            logger.error(f"Cache rebuild failed for student {student_id}: {e}")

    @classmethod
    def rebuild_teacher_cache_async(cls, teacher_id):
        """
        异步重建教师端缓存
        """
        thread = threading.Thread(
            target=cls._rebuild_teacher_cache,
            args=(teacher_id,),
            daemon=True
        )
        thread.start()
        logger.info(f"Started background cache rebuild for teacher {teacher_id}")

    @classmethod
    def _rebuild_teacher_cache(cls, teacher_id):
        """在后台线程中重建教师缓存"""
        try:
            from app import create_app
            app = create_app()
            with app.app_context():
                PageCacheService.rebuild_teacher_cache(teacher_id)
                logger.info(f"Completed cache rebuild for teacher {teacher_id}")
        except Exception as e:
            logger.error(f"Cache rebuild failed for teacher {teacher_id}: {e}")

    @classmethod
    def preload_student_cache(cls, student_id):
        """
        学生登录时同步预加载缓存（不异步，确保首次访问有数据）
        只预加载最重要的几个缓存类型，避免登录时间过长
        """
        try:
            # 优先加载最常访问的页面数据
            PageCacheService.rebuild_dashboard_stats(student_id)
            PageCacheService.rebuild_weak_points(student_id)
            logger.info(f"Preloaded core cache for student {student_id}")
            # 其余缓存异步加载
            thread = threading.Thread(
                target=cls._preload_remaining_student_cache,
                args=(student_id,),
                daemon=True
            )
            thread.start()
        except Exception as e:
            logger.error(f"Cache preload failed for student {student_id}: {e}")

    @classmethod
    def _preload_remaining_student_cache(cls, student_id):
        """异步加载剩余缓存"""
        try:
            from app import create_app
            app = create_app()
            with app.app_context():
                PageCacheService.rebuild_chapter_radar(student_id)
                PageCacheService.rebuild_score_distribution(student_id)
                PageCacheService.rebuild_recommendations(student_id)
                PageCacheService.rebuild_graph_colored(student_id)
                PageCacheService.rebuild_forgetting_trend(student_id)
                logger.info(f"Preloaded remaining cache for student {student_id}")
        except Exception as e:
            logger.error(f"Remaining cache preload failed for student {student_id}: {e}")


background_cache_builder = BackgroundCacheBuilder()
