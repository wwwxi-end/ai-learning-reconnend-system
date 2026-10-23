"""
Services module initialization
"""

from services.diagnosis import (
    detect_weak_points,
    get_class_weak_analysis,
    get_chapter_radar_data,
    get_score_distribution,
    get_kp_mastery_dict,
    get_forgetting_trend_data,
    get_kp_block_counts,
    get_all_forgetting_slopes
)
from services.recommendation import generate_recommendations
from services.llm_service import llm_service
from services.cache_service import PageCacheService
from services.background_cache import background_cache_builder

__all__ = [
    'detect_weak_points',
    'get_class_weak_analysis',
    'get_chapter_radar_data',
    'get_score_distribution',
    'get_kp_mastery_dict',
    'get_forgetting_trend_data',
    'get_kp_block_counts',
    'get_all_forgetting_slopes',
    'generate_recommendations',
    'llm_service',
    'PageCacheService',
    'background_cache_builder'
]