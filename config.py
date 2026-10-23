import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask基础配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-please-change')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True') == 'True'

    # MySQL配置（SQLAlchemy URI）
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'password')
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'learning_system')
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_POOL_RECYCLE = 3600
    SQLALCHEMY_POOL_PRE_PING = True
    SQLALCHEMY_ECHO = True

    # Neo4j配置
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')

    # 大模型配置（Agnes AI平台，兼容OpenAI接口）
    LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
    LLM_API_BASE = os.environ.get('LLM_API_BASE', 'https://apihub.agnes-ai.com/v1')
    LLM_MODEL = os.environ.get('LLM_MODEL', 'deepseekv4flash')
    LLM_MOCK_MODE = os.environ.get('LLM_MOCK_MODE', 'False') == 'True'

    # 文件上传配置
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 104857600))
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    ALLOWED_DOC_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'md'}
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # 分页配置
    ITEMS_PER_PAGE = 10

    # 薄弱点检测阈值
    ABSOLUTE_WEAK_THRESHOLD = 60       # 绝对薄弱：分数低于60
    RELATIVE_WEAK_THRESHOLD = 0.20     # 相对薄弱：低于个人平均20%
    RELATIVE_WEAK_RATIO = 0.20         # 兼容别名
    FORGETTING_MIN_RECORDS = 2         # 遗忘趋势：最少记录次数（2次以上可检测）
    HIGH_RISK_BLOCK_COUNT = 2          # 阻塞≥2个后继则判定高危薄弱
    REVIEW_DAY_THRESHOLD = 7           # 超过7天未复习加权推荐

    # 缓存配置
    CACHE_TYPE = 'FileSystemCache'
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache_data')
    CACHE_THRESHOLD = 1000


class DevelopmentConfig(Config):
    DEBUG = False


class ProductionConfig(Config):
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY')
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'FileSystemCache')
    if os.environ.get('REDIS_URL'):
        CACHE_TYPE = 'RedisCache'
        CACHE_REDIS_URL = os.environ.get('REDIS_URL')


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# 为兼容旧代码，导出模块级配置变量
ABSOLUTE_WEAK_THRESHOLD = Config.ABSOLUTE_WEAK_THRESHOLD
RELATIVE_WEAK_RATIO = Config.RELATIVE_WEAK_RATIO
FORGETTING_MIN_RECORDS = Config.FORGETTING_MIN_RECORDS
HIGH_RISK_BLOCK_COUNT = Config.HIGH_RISK_BLOCK_COUNT
REVIEW_DAY_THRESHOLD = Config.REVIEW_DAY_THRESHOLD

LLM_API_KEY = Config.LLM_API_KEY
LLM_API_URL = Config.LLM_API_BASE
LLM_MODEL_NAME = Config.LLM_MODEL
LLM_TIMEOUT = int(os.environ.get('LLM_TIMEOUT', 30))