from datetime import datetime
from models import db


class LearningRecord(db.Model):
    """学习记录：学生学习某知识点的行为数据"""
    __tablename__ = 'learning_records'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False)
    # 学习行为
    study_duration = db.Column(db.Integer, default=0, comment='本次学习时长(秒)')
    material_id = db.Column(db.Integer, db.ForeignKey('learning_materials.id'), nullable=True)
    progress_percent = db.Column(db.Float, default=0.0, comment='材料学习进度%')
    # 视频学习进度
    video_progress = db.Column(db.Float, default=0.0, comment='视频观看进度%(0-100)')
    video_duration = db.Column(db.Integer, default=0, comment='视频总时长(秒)')
    watched_duration = db.Column(db.Integer, default=0, comment='实际观看时长(秒)')
    # 文本阅读进度
    text_progress = db.Column(db.Float, default=0.0, comment='文本阅读进度%(0-100)')
    text_read_duration = db.Column(db.Integer, default=0, comment='文本阅读时长(秒)')
    text_total_length = db.Column(db.Integer, default=0, comment='文本总字数')
    # 测验相关
    quiz_score = db.Column(db.Float, nullable=True, comment='测验分数(0-100)')
    quiz_attempts = db.Column(db.Integer, default=0, comment='测验尝试次数')
    correct_count = db.Column(db.Integer, default=0, comment='答对题数')
    total_questions = db.Column(db.Integer, default=5, comment='总题数')
    # 状态
    status = db.Column(db.Enum('studying', 'completed', 'reviewed'), default='studying')
    notes = db.Column(db.Text, nullable=True, comment='学习笔记')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    material = db.relationship('LearningMaterial', foreign_keys=[material_id])

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'kp_id': self.kp_id,
            'study_duration': self.study_duration,
            'video_progress': self.video_progress,
            'video_duration': self.video_duration,
            'watched_duration': self.watched_duration,
            'text_progress': self.text_progress,
            'text_read_duration': self.text_read_duration,
            'text_total_length': self.text_total_length,
            'quiz_score': self.quiz_score,
            'quiz_attempts': self.quiz_attempts,
            'correct_count': self.correct_count,
            'total_questions': self.total_questions,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

    def __repr__(self):
        return f'<LearningRecord student={self.student_id} kp={self.kp_id} score={self.quiz_score}>'


class QuizSubmission(db.Model):
    """测验提交记录：每次做题的详细记录"""
    __tablename__ = 'quiz_submissions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False)
    learning_record_id = db.Column(db.Integer, db.ForeignKey('learning_records.id'), nullable=True)
    total_score = db.Column(db.Float, default=0.0, comment='本次总分(0-100)')
    time_spent = db.Column(db.Integer, default=0, comment='答题时长(秒)')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 明细答题
    answers = db.relationship('QuizAnswer', backref='submission', lazy='dynamic')
    learning_record = db.relationship('LearningRecord', foreign_keys=[learning_record_id])

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'kp_id': self.kp_id,
            'total_score': self.total_score,
            'time_spent': self.time_spent,
            'submitted_at': self.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if self.submitted_at else None
        }


class QuizAnswer(db.Model):
    """题目作答明细"""
    __tablename__ = 'quiz_answers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('quiz_submissions.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_questions.id'), nullable=False)
    student_answer = db.Column(db.String(20), nullable=True, comment='学生答案')
    is_correct = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float, default=0.0, comment='本题得分')

    question = db.relationship('QuizQuestion', foreign_keys=[question_id])

    def to_dict(self):
        return {
            'id': self.id,
            'question_id': self.question_id,
            'student_answer': self.student_answer,
            'is_correct': self.is_correct,
            'score': self.score
        }


class StudySession(db.Model):
    """学习会话：记录一次完整的学习过程"""
    __tablename__ = 'study_sessions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    kp_id = db.Column(db.Integer, db.ForeignKey('knowledge_points.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_seconds = db.Column(db.Integer, default=0)
    action_type = db.Column(db.Enum('watch_video', 'read_text', 'do_quiz', 'review'),
                             default='watch_video')
    device_type = db.Column(db.String(50), nullable=True, comment='设备类型')

    student = db.relationship('User', foreign_keys=[student_id])
    knowledge_point = db.relationship('KnowledgePoint', foreign_keys=[kp_id])
