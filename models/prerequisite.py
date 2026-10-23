from datetime import datetime
from models import db


class Prerequisite(db.Model):
    """前驱关系：在MySQL中存储，与Neo4j同步"""
    __tablename__ = 'prerequisites'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    prerequisite_kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False,
                                    comment='前置知识点ID')
    target_kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False,
                              comment='目标知识点ID')
    relation_type = db.Column(db.Enum('must', 'recommended', 'related'),
                               default='must', comment='关系类型')
    weight = db.Column(db.Float, default=1.0, comment='关系权重')
    description = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    prerequisite_kp = db.relationship('KnowledgePoint', foreign_keys=[prerequisite_kp_id],
                                       backref='as_prerequisite_for')
    target_kp = db.relationship('KnowledgePoint', foreign_keys=[target_kp_id],
                                 backref='has_prerequisites')

    __table_args__ = (
        db.UniqueConstraint('prerequisite_kp_id', 'target_kp_id',
                            name='uq_prerequisite_target'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'prerequisite_kp_id': self.prerequisite_kp_id,
            'target_kp_id': self.target_kp_id,
            'relation_type': self.relation_type,
            'weight': self.weight,
            'description': self.description
        }

    def __repr__(self):
        return f'<Prerequisite {self.prerequisite_kp_id} -> {self.target_kp_id}>'


class WeakPointRecord(db.Model):
    """薄弱点检测结果记录"""
    __tablename__ = 'weak_point_records'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False)
    weak_type = db.Column(db.Enum('absolute', 'relative', 'high_risk', 'forgetting'),
                           nullable=False, comment='薄弱类型')
    score = db.Column(db.Float, nullable=True, comment='当前分数')
    personal_avg = db.Column(db.Float, nullable=True, comment='个人平均分')
    severity = db.Column(db.Enum('low', 'medium', 'high'), default='medium', comment='严重程度')
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_resolved = db.Column(db.Boolean, default=False, comment='是否已解决')

    student = db.relationship('User', foreign_keys=[student_id])
    knowledge_point = db.relationship('KnowledgePoint', foreign_keys=[kp_id])

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'kp_id': self.kp_id,
            'weak_type': self.weak_type,
            'score': self.score,
            'personal_avg': self.personal_avg,
            'severity': self.severity,
            'detected_at': self.detected_at.strftime('%Y-%m-%d %H:%M:%S') if self.detected_at else None,
            'is_resolved': self.is_resolved
        }


class RecommendationRecord(db.Model):
    """推荐记录"""
    __tablename__ = 'recommendation_records'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False)
    rank = db.Column(db.Integer, default=1, comment='推荐排名(1-5)')
    score = db.Column(db.Float, default=0.0, comment='推荐评分')
    reason = db.Column(db.Text, nullable=True, comment='推荐理由')
    reason_tags = db.Column(db.String(200), nullable=True, comment='理由标签(JSON)')
    is_accepted = db.Column(db.Boolean, nullable=True, comment='是否被接受')
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User', foreign_keys=[student_id])
    knowledge_point = db.relationship('KnowledgePoint', foreign_keys=[kp_id])

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'kp_id': self.kp_id,
            'rank': self.rank,
            'score': self.score,
            'reason': self.reason,
            'reason_tags': self.reason_tags,
            'generated_at': self.generated_at.strftime('%Y-%m-%d %H:%M:%S') if self.generated_at else None
        }
