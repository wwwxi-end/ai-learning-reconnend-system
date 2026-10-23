from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from models import db
from models.user import User
from extensions import limiter

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        user = User.query.filter_by(username=username).first()

        if not user:
            flash('用户名不存在，请联系管理员注册', 'danger')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('账号已被禁用，请联系管理员', 'warning')
            return render_template('auth/login.html')

        if not user.check_password(password):
            flash('密码错误', 'danger')
            return render_template('auth/login.html')

        login_user(user, remember=bool(remember))
        user.last_login = datetime.utcnow()
        db.session.commit()

        # 登录成功后预加载缓存数据，确保首次页面切换不卡顿
        try:
            from services.background_cache import background_cache_builder
            if user.role == 'student':
                background_cache_builder.preload_student_cache(user.id)
            elif user.role == 'teacher':
                background_cache_builder.rebuild_teacher_cache_async(user.id)
        except Exception as e:
            # 缓存预加载失败不影响登录
            from flask import current_app
            current_app.logger.warning(f"Cache preload failed for user {user.id}: {e}")

        flash(f'欢迎回来，{user.real_name}！', 'success')
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return _redirect_by_role(user.role)

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已安全退出', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user = User.query.filter_by(username=username).first()
        
        if user:
            flash('请联系管理员重置密码', 'info')
        else:
            flash('该用户名不存在', 'danger')
        
        return render_template('auth/forgot_password.html')
    
    return render_template('auth/forgot_password.html')


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            old_pwd = request.form.get('old_password', '')
            new_pwd = request.form.get('new_password', '')
            confirm_pwd = request.form.get('confirm_password', '')

            if not current_user.check_password(old_pwd):
                flash('原密码错误', 'danger')
            elif new_pwd != confirm_pwd:
                flash('两次输入的新密码不一致', 'danger')
            elif len(new_pwd) < 6:
                flash('新密码至少6位', 'warning')
            else:
                current_user.set_password(new_pwd)
                db.session.commit()
                flash('密码修改成功', 'success')

        elif action == 'update_info':
            email = request.form.get('email', '').strip()
            if email:
                current_user.email = email
                db.session.commit()
                flash('个人信息更新成功', 'success')

    return render_template('auth/profile.html', user=current_user)


def _redirect_by_role(role: str):
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    elif role == 'teacher':
        return redirect(url_for('teacher.dashboard'))
    else:
        return redirect(url_for('student.dashboard'))
