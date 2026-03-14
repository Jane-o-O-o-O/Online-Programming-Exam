# 在线编程考试系统

基于技术文档先落地的基础版工程骨架，面向 Windows 本地开发环境。

## 当前实现

- Django 5 项目基础配置
- 自定义用户模型，支持管理员、教师、学生角色
- 题库、考试、提交、答题、判题任务、通知等核心模型
- 基于 Session 的注册、登录、登出、当前用户接口
- 教师/管理员创建题目与考试，学生开始考试、保存答案、交卷
- QQ 邮箱验证码发送与密码重置流程
- Redis/Celery 配置占位
- QQ 邮箱 SMTP 配置入口
- Windows 一键启动脚本

## 当前 API

- `POST /api/accounts/register/`
- `POST /api/accounts/login/`
- `POST /api/accounts/logout/`
- `GET /api/accounts/me/`
- `GET /api/accounts/stats/`
- `POST /api/accounts/password-reset-code/`
- `POST /api/accounts/password-reset/`
- `GET/POST /api/exams/questions/`
- `GET/POST /api/exams/exams/`
- `POST /api/exams/exams/<id>/start/`
- `POST /api/exams/submissions/<id>/answers/`
- `POST /api/exams/submissions/<id>/finish/`
- `GET /api/exams/submissions/<id>/`

## Windows 本地启动

1. 可选：启动 Redis

```powershell
docker compose up -d redis
```

2. 复制环境变量

```powershell
Copy-Item .env.example .env
```

3. 一键启动

```powershell
.\run_windows.ps1
```

4. 验证接口

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/api/accounts/stats/`
- `http://127.0.0.1:8000/api/exams/overview/`

## 一键演示数据

```powershell
python manage.py seed_demo
```

默认会创建：

- 教师：`demo_teacher / Demo123456`
- 学生：`demo_student / Demo123456`
- 已发布演示考试：`系统演示考试`

本地开发模式下，编程题会直接在当前机器上同步判题，不依赖 Docker 或 Celery。

## 手动启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## 后续建议

- 增加 Django REST Framework 和鉴权接口
- 增加题目导入、考试编排、在线答题页面
- 将真实判题逻辑接入 Docker 沙箱与 Celery Worker
- 增加单元测试和初始化数据脚本
