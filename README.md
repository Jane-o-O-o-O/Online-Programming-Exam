# 在线编程考试系统

基于技术文档先落地的基础版工程骨架，面向 Windows 本地开发环境。

## 当前实现

- Django 5 项目基础配置
- 自定义用户模型，支持管理员、教师、学生角色
- 题库、考试、提交、答题、判题任务、通知等核心模型
- 基于 Session 的注册、登录、登出、当前用户接口
- 教师/管理员创建题目与考试，学生开始考试、保存答案、交卷
- 题库批量导入、考试删除、成绩分析等教师后台能力
- QQ 邮箱验证码发送与密码重置流程
- 本地同步编程题判题
- Celery 异步判题链路已接入业务流，可查看任务列表并重判
- 硅基流动大模型接入，可生成考试 AI 分析和提交 AI 讲评
- 站内通知中心，支持考试发布通知、列表查询、已读/全部已读
- 原生 Django 模板控制台页面 `/app/`，可直接完成教师和学生主流程
- Windows 一键启动脚本

## 当前 API

### 账户
- `POST /api/accounts/register/`
- `POST /api/accounts/login/`
- `POST /api/accounts/logout/`
- `GET /api/accounts/me/`
- `GET /api/accounts/stats/`
- `POST /api/accounts/password-reset-code/`
- `POST /api/accounts/password-reset/`

### 考试与题库
- `GET /api/exams/overview/`
- `GET/POST /api/exams/questions/`
- `POST /api/exams/questions/import/`
- `GET/PUT/DELETE /api/exams/questions/<id>/`
- `GET/POST /api/exams/exams/`
- `GET/PUT/DELETE /api/exams/exams/<id>/`
- `POST /api/exams/exams/<id>/publish/`
- `POST /api/exams/exams/<id>/finish/`
- `GET /api/exams/exams/<id>/submissions/`
- `GET /api/exams/exams/<id>/analytics/`
- `POST /api/exams/exams/<id>/analytics/ai-summary/`
- `POST /api/exams/exams/<id>/start/`
- `GET /api/exams/my-submissions/`
- `POST /api/exams/submissions/<id>/answers/`
- `POST /api/exams/submissions/<id>/finish/`
- `GET /api/exams/submissions/<id>/`
- `POST /api/exams/submissions/<id>/ai-feedback/`

### 判题
- `GET /api/judge/queue-status/`
- `GET /api/judge/tasks/`
- `POST /api/judge/tasks/<id>/retry/`

### 通知
- `GET /api/notifications/summary/`
- `GET /api/notifications/`
- `POST /api/notifications/read-all/`
- `POST /api/notifications/<id>/read/`

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

4. 打开控制台页面

- `http://127.0.0.1:8000/app/`

## 一键演示数据

```powershell
python manage.py seed_demo
```

默认会创建：

- 教师：`demo_teacher / Demo123456`
- 学生：`demo_student / Demo123456`
- 已发布演示考试：`系统演示考试`

## 前端控制台说明

页面入口：`/app/`

教师侧可直接完成：

- 创建题目
- 批量导入题目
- 创建考试
- 发布和结束考试
- 查看考试统计
- 生成 AI 教学分析
- 查看判题任务并重判

学生侧可直接完成：

- 登录后查看已发布考试
- 开始考试
- 保存答案
- 交卷评分
- 查看提交详情
- 生成 AI 学习讲评
- 查看考试通知并标记已读

## 硅基流动大模型配置

在本地 `.env` 中填写：

```env
SILICONFLOW_API_KEY=your_siliconflow_api_key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Qwen/Qwen2.5-7B-Instruct
SILICONFLOW_TIMEOUT=60
```

调用说明：

- 教师端生成考试 AI 分析：`POST /api/exams/exams/<id>/analytics/ai-summary/`
- 学生或教师生成提交 AI 讲评：`POST /api/exams/submissions/<id>/ai-feedback/`
- 系统概览接口 `GET /api/exams/overview/` 会返回当前 LLM 是否已配置

## 判题模式配置

本地同步判题：

```env
JUDGE_EXECUTION_MODE=local
```

Celery 异步判题：

```env
JUDGE_EXECUTION_MODE=celery
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

启动 Worker：

```powershell
celery -A config worker -l info
```

## 手动启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 当前状态

- 后端主链已经完整跑通
- 教师和学生的核心业务 API 已补齐
- 异步判题和通知中心已经落地
- 剩余主要是页面细化、Docker 沙箱判题和更完整的后台报表
