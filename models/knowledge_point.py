from datetime import datetime
from models import db


class KnowledgePoint(db.Model):
    """知识点模型（与Neo4j图谱节点对应）"""
    __tablename__ = 'knowledge_points'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    neo4j_id = db.Column(db.String(100), unique=True, nullable=True, comment='Neo4j节点ID')
    name = db.Column(db.String(200), nullable=False, comment='知识点名称')
    code = db.Column(db.String(50), unique=True, nullable=False, comment='知识点编码')
    chapter = db.Column(db.String(100), nullable=True, comment='所属章节')
    chapter_order = db.Column(db.Integer, default=0, comment='章节排序')
    description = db.Column(db.Text, nullable=True, comment='描述')
    difficulty = db.Column(db.Integer, default=3, comment='难度(1-5)')
    importance = db.Column(db.Integer, default=3, comment='重要程度(1-5)')
    estimated_minutes = db.Column(db.Integer, default=30, comment='预计学习分钟数')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # 关联
    materials = db.relationship('LearningMaterial', backref='knowledge_point', lazy='dynamic')
    quiz_questions = db.relationship('QuizQuestion', backref='knowledge_point', lazy='dynamic')
    learning_records = db.relationship('LearningRecord', backref='knowledge_point', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'neo4j_id': self.neo4j_id,
            'name': self.name,
            'code': self.code,
            'chapter': self.chapter,
            'chapter_order': self.chapter_order,
            'description': self.description,
            'difficulty': self.difficulty,
            'importance': self.importance,
            'estimated_minutes': self.estimated_minutes
        }

    def __repr__(self):
        return f'<KnowledgePoint {self.code}: {self.name}>'


class LearningMaterial(db.Model):
    """学习材料（视频/文本）"""
    __tablename__ = 'learning_materials'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False, comment='材料标题')
    material_type = db.Column(db.Enum('video', 'text', 'pdf'), nullable=False, comment='材料类型')
    file_path = db.Column(db.String(500), nullable=True, comment='文件路径（本地存储）')
    external_url = db.Column(db.String(1000), nullable=True, comment='外部URL（B站、腾讯视频等）')
    content = db.Column(db.Text, nullable=True, comment='文本内容（文本类型）')
    duration_seconds = db.Column(db.Integer, nullable=True, comment='视频时长(秒)')
    file_size = db.Column(db.BigInteger, nullable=True, comment='文件大小(字节)')
    description = db.Column(db.Text, nullable=True)
    view_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'kp_id': self.kp_id,
            'title': self.title,
            'material_type': self.material_type,
            'file_path': self.file_path,
            'external_url': self.external_url,
            'duration_seconds': self.duration_seconds,
            'description': self.description,
            'view_count': self.view_count,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class QuizQuestion(db.Model):
    """测验题目（每个知识点5题）"""
    __tablename__ = 'quiz_questions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False, comment='题目内容')
    question_type = db.Column(db.Enum('single', 'multiple', 'truefalse', 'fillblank'),
                               default='single', comment='题型')
    option_a = db.Column(db.String(500), nullable=True)
    option_b = db.Column(db.String(500), nullable=True)
    option_c = db.Column(db.String(500), nullable=True)
    option_d = db.Column(db.String(500), nullable=True)
    correct_answer = db.Column(db.String(10), nullable=False, comment='正确答案(A/B/C/D/AB等)')
    explanation = db.Column(db.Text, nullable=True, comment='解析')
    difficulty = db.Column(db.Integer, default=3, comment='题目难度1-5')
    order_in_kp = db.Column(db.Integer, default=1, comment='题目序号(1-5)')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'kp_id': self.kp_id,
            'question_text': self.question_text,
            'question_type': self.question_type,
            'option_a': self.option_a,
            'option_b': self.option_b,
            'option_c': self.option_c,
            'option_d': self.option_d,
            'correct_answer': self.correct_answer,
            'explanation': self.explanation,
            'difficulty': self.difficulty,
            'order_in_kp': self.order_in_kp
        }

    def __repr__(self):
        return f'<QuizQuestion {self.id}: kp={self.kp_id}>'
