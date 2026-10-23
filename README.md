# AI 智能学习系统

基于 Flask + MySQL + Neo4j + 大模型的智能学习诊断与个性化推荐系统。

## 项目简介

本系统是一个面向高校教学场景的 AI 智能学习平台，融合了知识图谱、多维度薄弱点诊断、个性化推荐和大模型 AI 导师等技术，为学生提供精准的学习路径规划，为教师提供班级学情分析工具。

## 核心功能

### 学生端
- **知识图谱可视化**：基于 Neo4j 的知识点前驱/后继关系图谱，按掌握程度着色（绿/黄/红/灰）
- **多维度薄弱点诊断**：
  - 绝对薄弱（分数 < 60）
  - 相对薄弱（低于个人平均 20%）
  - 高危薄弱（阻塞 ≥ 2 个后继知识点）
  - 遗忘趋势（多次学习分数线性下降）
- **个性化学习路径推荐**：综合薄弱点、前驱关系、重要程度、遗忘衰减计算 Top-N 推荐
- **AI 导师问答**：基于大模型 Function Calling 的智能问答，可查询薄弱点、知识点详情、学习路径
- **学习数据分析**：仪表盘统计、章节雷达图、遗忘趋势曲线
- **学习材料学习**：视频进度、文本阅读、在线测验
- **PDF 学习报告导出**

### 教师端
- **班级学情分析**：班级整体掌握情况、薄弱知识点分布
- **学生详情查看**：单个学生的学习记录、薄弱点、知识图谱
- **教学资源管理**：上传视频、文本材料、创建测验题目
- **知识点与前驱关系管理**

### 管理端
- **用户管理**：创建学生/教师账号、批量导入、密码重置
- **课程组管理**：教师分组
- **知识点批量管理**
- **系统数据统计**

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                   前端 (Jinja2 + ECharts)        │
├─────────────────────────────────────────────────┤
│              Flask 应用层                         │
│  ┌──────────┬──────────┬──────────┬───────────┐  │
│  │ 认证授权  │ 路由蓝图  │  API 接口 │  错误处理  │  │
│  └──────────┴──────────┴──────────┴───────────┘  │
├─────────────────────────────────────────────────┤
│              服务层 (Services)                    │
│  ┌──────────┬──────────┬──────────┬───────────┐  │
│  │ LLM 服务 │ Neo4j 服务│ 诊断服务  │ 推荐服务   │  │
│  └──────────┴──────────┴──────────┴───────────┘  │
├─────────────────────────────────────────────────┤
│              数据层                               │
│  ┌──────────────────┬────────────────────────┐   │
│  │  MySQL (SQLAlchemy)│  Neo4j (知识图谱)       │   │
│  └──────────────────┴────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | Flask 2.3 |
| ORM | Flask-SQLAlchemy 3.1 |
| 关系数据库 | MySQL 8.0 |
| 图数据库 | Neo4j 4.2.3 (JDK 11) |
| 大模型 | 兼容 OpenAI 接口的平台（商汤 SenseNova / DeepSeek 等） |
| 缓存 | Flask-Caching (FileSystemCache / Redis) |
| 安全 | Flask-WTF (CSRF)、Flask-Login、Werkzeug 密码哈希 |
| 限流 | Flask-Limiter |
| 前端可视化 | ECharts |
| PDF 生成 | ReportLab |
| 数据分析 | NumPy、SciPy |

## 项目结构

```
learning_system2/
├── app.py                  # 应用入口，工厂模式
├── config.py               # 配置管理（从 .env 读取）
├── extensions.py           # 扩展初始化（cache, csrf, limiter）
├── models/                 # 数据模型
│   ├── user.py             # 用户、课程组
│   ├── knowledge_point.py  # 知识点、学习材料、测验题
│   ├── learning_record.py  # 学习记录、测验提交
│   └── prerequisite.py     # 前驱关系、薄弱点记录、推荐记录
├── routes/                 # 路由蓝图
│   ├── auth.py             # 认证（登录/登出/修改密码）
│   ├── admin.py            # 管理端
│   ├── teacher.py          # 教师端
│   ├── student.py          # 学生端
│   └── api.py              # 数据 API 接口
├── services/               # 业务服务
│   ├── llm_service.py      # 大模型 AI 导师（Function Calling）
│   ├── neo4j_service.py    # Neo4j 知识图谱服务
│   ├── diagnosis.py        # 多维度薄弱点诊断
│   ├── recommendation.py   # 个性化学习路径推荐
│   ├── pdf_generator.py    # PDF 报告生成
│   └── cache_service.py    # 缓存服务
├── templates/              # Jinja2 模板
├── static/                 # 静态资源（CSS/JS）
├── utils/                  # 工具函数
├── requirements.txt        # 依赖清单
├── .env.example            # 环境变量示例
└── init_test_data.py       # 测试数据初始化脚本
```

## 快速开始

### 1. 环境要求

- Python 3.11+
- MySQL 8.0+
- Neo4j 4.2.3 (需 JDK 11)
- 大模型 API Key（兼容 OpenAI 接口的平台）

### 2. 安装依赖

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入以下信息：

```ini
# Flask
SECRET_KEY=your_secret_key_here

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=learning_system

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password

# 大模型 API（兼容 OpenAI 接口）
LLM_API_KEY=your_llm_api_key
LLM_API_BASE=https://api.example.com/v1
LLM_MODEL=deepseek-v4-flash
```

### 4. 初始化数据库

```bash
# 创建数据库（需先手动创建 MySQL 数据库）
# 首次启动会自动创建表结构
python app.py
```

### 5. 初始化测试数据（可选）

```bash
python init_test_data.py
# 会创建测试学生账号：test_student / 123456
```

### 6. 启动服务

```bash
python app.py
# 默认端口 9999
```

访问 `http://localhost:9999` 即可使用。

## 核心算法说明

### 加权学习分数

```
加权分 = 视频进度 × 0.35 + 文本进度 × 0.15 + 测验分数 × 0.50
```

### 薄弱点检测维度

| 维度 | 判定条件 |
|------|----------|
| 绝对薄弱 | 最新加权分 < 60 |
| 相对薄弱 | 最新加权分 < 个人平均分 × 0.8 |
| 高危薄弱 | 薄弱且阻塞 ≥ 2 个后继知识点 |
| 遗忘趋势 | 多次记录分数线性回归斜率 < -0.5 |

### 推荐算法权重

推荐分数综合考虑：薄弱程度（40%）、前驱依赖（25%）、重要程度（20%）、遗忘衰减（15%）。

## 安全说明

- 所有表单提交启用 CSRF 防护
- 密码使用 Werkzeug `generate_password_hash` 哈希存储
- API 接口启用登录鉴权与角色权限校验
- 接口请求限流防止滥用
- **部署前请务必修改 `.env` 中的默认密钥和密码**

## License

MIT
