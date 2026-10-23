from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from models import db


class User(UserMixin, db.Model):
    """用户模型（学生/教师/管理员）"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, comment='用户名')
    password_hash = db.Column(db.String(256), nullable=False, comment='密码哈希')
    real_name = db.Column(db.String(50), nullable=False, comment='真实姓名')
    role = db.Column(db.Enum('admin', 'teacher', 'student'), nullable=False, comment='角色')
    email = db.Column(db.String(100), unique=True, nullable=True, comment='邮箱')
    student_id = db.Column(db.String(20), unique=True, nullable=True, comment='学号（学生）')
    teacher_id = db.Column(db.String(20), unique=True, nullable=True, comment='工号（教师）')
    department = db.Column(db.String(100), nullable=True, comment='院系/部门')
    course_group = db.Column(db.String(100), nullable=True, comment='课程组（教师）')
    is_active = db.Column(db.Boolean, default=True, comment='是否激活')
    avatar = db.Column(db.String(200), nullable=True, comment='头像路径')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True, comment='最后登录时间')

    # 关联关系
    learning_records = db.relationship('LearningRecord', backref='student', lazy='dynamic',
                                        foreign_keys='LearningRecord.student_id')
    uploaded_materials = db.relationship('LearningMaterial', backref='teacher', lazy='dynamic',
                                          foreign_keys='LearningMaterial.teacher_id')
    quiz_submissions = db.relationship('QuizSubmission', backref='student', lazy='dynamic',
                                        foreign_keys='QuizSubmission.student_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'real_name': self.real_name,
            'role': self.role,
            'email': self.email,
            'student_id': self.student_id,
            'teacher_id': self.teacher_id,
            'department': self.department,
            'course_group': self.course_group,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class CourseGroup(db.Model):
    """课程组模型"""
    __tablename__ = 'course_groups'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False, comment='课程组名称')
    description = db.Column(db.Text, nullable=True, comment='描述')
    course_name = db.Column(db.String(100), nullable=False, comment='对应课程名称')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 教师关联（多对多）
    teachers = db.relationship('TeacherCourseGroup', backref='course_group', lazy='dynamic')

    def __repr__(self):
        return f'<CourseGroup {self.name}>'


class TeacherCourseGroup(db.Model):
    """教师-课程组关联表"""
    __tablename__ = 'teacher_course_groups'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_group_id = db.Column(db.Integer, db.ForeignKey('course_groups.id'), nullable=False)
    role_in_group = db.Column(db.Enum('leader', 'member'), default='member', comment='组内角色')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    teacher = db.relationship('User', foreign_keys=[teacher_id])

    __table_args__ = (db.UniqueConstraint('teacher_id', 'course_group_id'),)
