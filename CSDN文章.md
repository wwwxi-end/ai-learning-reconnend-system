# 从零搭建 AI 智能学习系统：Flask + Neo4j + 大模型实现薄弱点诊断与个性化推荐

> 本文记录了我借助 AI 辅助开发的一个完整的智能学习诊断系统，涵盖知识图谱、多维度薄弱点检测、个性化推荐和 AI 导师等核心功能。文章将从架构设计、核心算法实现到踩坑经验进行全面分享。

## 一、项目背景

在高校教学中，教师往往面临一个难题：一个班几十名学生，每个人的知识掌握情况千差万别，传统的课堂教学很难做到因材施教。学生也常常不知道自己到底哪里没学会、下一步该学什么。

于是我决定做一个 **AI 智能学习系统**，核心目标是：

1. **精准诊断**：自动识别学生的薄弱知识点（不只是看分数低）
2. **智能推荐**：基于知识图谱和薄弱点，给出个性化学习路径
3. **AI 导师**：接入大模型，让学生可以用自然语言提问学习问题
4. **学情可视**：教师能直观看到班级整体学情分布

## 二、技术选型

经过一番调研，最终选择了以下技术栈：

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| Web 框架 | Flask 2.3 | 轻量灵活，蓝图机制适合模块化开发 |
| 关系数据库 | MySQL + SQLAlchemy | 存储用户、学习记录等结构化数据 |
| 图数据库 | Neo4j 4.2.3 | 知识点前驱/后继关系天然适合图存储 |
| 大模型 | 兼容 OpenAI 接口的平台 | Function Calling 实现 AI 导师工具调用 |
| 缓存 | Flask-Caching | 薄弱点检测结果缓存，提升响应速度 |
| 可视化 | ECharts | 知识图谱、雷达图、趋势曲线 |
| 安全 | Flask-WTF + Flask-Login | CSRF 防护 + 会话管理 |

## 三、系统架构

整体采用分层架构：

```
前端 (Jinja2 + ECharts)
        │
        ▼
Flask 应用层 (路由蓝图 + 认证授权)
        │
        ▼
服务层 (LLM 服务 / Neo4j 服务 / 诊断服务 / 推荐服务)
        │
        ▼
数据层 (MySQL 结构化数据 + Neo4j 知识图谱)
```

### 3.1 数据模型设计

核心数据表：

- **users**：用户表（admin / teacher / student 三种角色）
- **knowledge_points**：知识点表，包含章节、难度、重要程度
- **learning_records**：学习记录表，记录视频进度、文本进度、测验分数
- **prerequisites**：前驱关系表，知识点之间的 must / recommended / related 关系
- **weak_point_records**：薄弱点检测结果缓存
- **recommendation_records**：推荐记录

### 3.2 项目目录结构

```
learning_system2/
├── app.py              # 应用工厂入口
├── config.py           # 配置管理（从 .env 读取）
├── models/             # SQLAlchemy 数据模型
├── routes/             # 蓝图路由（auth/admin/teacher/student/api）
├── services/           # 业务服务层
│   ├── llm_service.py      # 大模型 AI 导师
│   ├── neo4j_service.py    # 知识图谱服务
│   ├── diagnosis.py        # 薄弱点诊断
│   └── recommendation.py   # 推荐算法
├── templates/          # Jinja2 模板
└── static/             # 静态资源
```

## 四、核心功能实现

### 4.1 多维度薄弱点诊断

这是系统最核心的功能。我没有简单地用"分数低于 60 就是薄弱"，而是设计了 **四个维度** 的检测：

```python
# 加权学习分数：视频 35% + 文本 15% + 测验 50%
def calculate_weighted_score(record):
    video = record.video_progress or 0
    text = record.text_progress or 0
    quiz = record.quiz_score or 0
    return round(video * 0.35 + text * 0.15 + quiz * 0.50, 2)
```

四个诊断维度：

| 维度 | 判定逻辑 | 业务含义 |
|------|----------|----------|
| **绝对薄弱** | 最新加权分 < 60 | 这个知识点确实没学会 |
| **相对薄弱** | 分数 < 个人平均分 × 0.8 | 相比自己其他知识点偏弱 |
| **高危薄弱** | 薄弱 + 阻塞 ≥ 2 个后继 | 不学会会影响后续多个知识点 |
| **遗忘趋势** | 多次记录分数线性回归斜率 < -0.5 | 学过但在遗忘 |

遗忘趋势的判定用到了最小二乘法拟合斜率：

```python
n = len(scores)
sum_x = sum(range(n))
sum_y = sum(scores)
sum_xy = sum(i * s for i, s in enumerate(scores))
sum_x2 = sum(i * i for i in range(n))
denominator = n * sum_x2 - sum_x * sum_x
slope = (n * sum_xy - sum_x * sum_y) / denominator if denominator != 0 else 0
has_forgetting_trend = slope < -0.5
```

### 4.2 Neo4j 知识图谱

知识点之间的前驱/后继关系非常适合用图数据库存储。我用 Neo4j 存储知识点节点和 PREREQUISITE_OF 关系，并实现了着色渲染：

```python
def get_knowledge_graph_with_color(self, student_scores):
    nodes = self.get_all_knowledge_points()
    edges = self.get_all_relations()

    colored_nodes = []
    for node in nodes:
        score = student_scores.get(node['mysql_id'])
        if score is None:
            color = '#d9d9d9'  # 灰：未学习
        elif score >= 60:
            color = '#52c41a'  # 绿：掌握
        elif score >= 40:
            color = '#faad14'  # 黄：部分掌握
        else:
            color = '#ff4d4f'  # 红：未掌握
        colored_nodes.append({...})
```

这样学生打开知识图谱，一眼就能看出哪些知识点是红色（需要重点复习）。

我还实现了 **学习路径查找**，用 Cypher 查询从目标知识点反向追溯完整前驱链：

```cypher
MATCH path = (start:KnowledgePoint)-[:PREREQUISITE_OF*1..10]->(target:KnowledgePoint {code: $target_code})
WHERE NOT ()-[:PREREQUISITE_OF]->(start)
RETURN [node in nodes(path) | {code: node.code, name: node.name}] as path_nodes
```

### 4.3 个性化推荐算法

推荐分数综合考虑四个维度：

```
推荐分 = 薄弱程度 × 0.4 + 前驱依赖 × 0.25 + 重要程度 × 0.2 + 遗忘衰减 × 0.15
```

- **薄弱程度**：分数越低，推荐优先级越高
- **前驱依赖**：如果该知识点是其他薄弱点的前驱，优先推荐
- **重要程度**：知识点的重要性权重（1-5）
- **遗忘衰减**：距离上次学习时间越久，推荐权重越高

### 4.4 大模型 AI 导师（Function Calling）

这是最有意思的部分。我没有让大模型直接回答所有问题，而是通过 **Function Calling** 让模型主动调用系统工具获取真实数据：

定义工具：

```python
_agent_tools = [
    {
        "type": "function",
        "function": {
            "name": "get_student_weak_points",
            "description": "获取学生的薄弱点检测结果，包括绝对薄弱、相对薄弱、高危薄弱和遗忘趋势知识点",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "integer", "description": "学生ID"}
                },
                "required": ["student_id"]
            }
        }
    },
    # ... get_knowledge_point_info, get_learning_path 等工具
]
```

对话流程：
1. 学生提问："我哪些知识点比较薄弱？"
2. 大模型识别需要调用 `get_student_weak_points` 工具
3. 系统执行工具，返回真实薄弱点数据
4. 大模型基于数据生成自然语言回答

这样 AI 导师的回答就不是"一本正经地胡说八道"，而是基于学生真实学习数据的精准回答。

## 五、踩坑与经验

### 5.1 配置管理

所有敏感配置（数据库密码、API Key）都通过 `.env` 文件管理，代码中只读取环境变量：

```python
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-please-change')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'password')
    LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
```

**重要提醒**：`.env` 文件绝对不能提交到 Git，需要在 `.gitignore` 中排除。

### 5.2 Neo4j 版本兼容

Neo4j 4.x 需要 JDK 11，5.x 需要 JDK 17。项目使用 Neo4j 4.2.3 + neo4j 4.4.12 驱动，注意版本匹配：

```
neo4j==4.4.12  # 兼容 Neo4j 4.2.3
```

### 5.3 缓存策略

薄弱点检测涉及大量数据库查询，每次请求都计算会很慢。我用 Flask-Caching 做了结果缓存：

```python
@cache.cached(timeout=300, key_prefix=...)
def detect_weak_points(student_id):
    ...
```

### 5.4 安全防护

- CSRF：所有 POST 请求通过 Flask-WTF 校验 token
- 密码：Werkzeug `generate_password_hash` 哈希存储
- 鉴权：`@login_required` + 角色校验装饰器
- 限流：Flask-Limiter 防止接口滥用

## 六、运行效果

系统支持三种角色：

- **学生**：查看知识图谱、薄弱点诊断、个性化学习计划、AI 导师问答、学习报告导出
- **教师**：班级学情分析、学生详情、上传教学材料、创建测验
- **管理员**：用户管理、课程组管理、数据统计

## 七、总结与反思

这个项目让我对 AI + 教育的结合有了更深的理解：

1. **大模型不是万能的**：纯大模型回答容易"幻觉"，必须结合真实数据（Function Calling）
2. **知识图谱很有价值**：前驱关系让推荐不再是"猜"，而是有逻辑依据的
3. **多维度诊断比单一分数更有意义**：同样考 50 分，"绝对薄弱"和"遗忘趋势"的干预策略完全不同
4. **AI 辅助开发效率很高**：从想法到落地，借助 AI 大幅缩短了开发周期，但核心算法和架构设计仍需要自己把控

## 八、开源地址

项目已开源到 GitHub，包含完整代码、测试数据初始化脚本和部署文档：

> （此处填写你的 GitHub 仓库地址）

欢迎 Star 和 Issue 交流！

---

*本文由作者借助 AI 辅助开发完成，核心算法与架构设计为原创。如需转载请注明出处。*
