# services/llm_service.py
import requests
import json
import logging

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.mock_mode = False
        self.api_key = ''
        self.api_base = ''
        self.model = ''
        self.timeout = 30

    def init_app(self, app):
        self.mock_mode = app.config.get('LLM_MOCK_MODE', False)
        self.api_key = app.config.get('LLM_API_KEY', '')
        self.api_base = app.config.get('LLM_API_BASE', 'https://token.sensenova.cn/v1').rstrip('/')
        self.model = app.config.get('LLM_MODEL', 'deepseek-v4-flash')
        self.timeout = app.config.get('LLM_TIMEOUT', 30)

    # ========== Agent 工具定义 ==========
    _agent_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_student_weak_points",
                "description": "获取学生的薄弱点检测结果，包括绝对薄弱、相对薄弱、高危薄弱和遗忘趋势知识点",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "integer",
                            "description": "学生ID"
                        }
                    },
                    "required": ["student_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_knowledge_point_info",
                "description": "获取知识点的详细信息，包括名称、章节、难度、重要程度以及前驱和后继知识点。如果提供了student_id，还会返回该学生在这些知识点上的掌握状态",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kp_name": {
                            "type": "string",
                            "description": "知识点名称"
                        },
                        "student_id": {
                            "type": "integer",
                            "description": "学生ID（可选，用于获取学生掌握状态）"
                        }
                    },
                    "required": ["kp_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_learning_path",
                "description": "获取从当前状态到目标知识点的学习路径，包括前置知识点和掌握状态",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_kp_name": {
                            "type": "string",
                            "description": "目标知识点名称"
                        },
                        "student_id": {
                            "type": "integer",
                            "description": "学生ID"
                        }
                    },
                    "required": ["target_kp_name", "student_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_student_learning_summary",
                "description": "获取学生的学习概况，包括已学知识点数、平均分、薄弱知识点数等",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "integer",
                            "description": "学生ID"
                        }
                    },
                    "required": ["student_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_knowledge_point_neighbors",
                "description": "获取知识点的前驱和后继知识点关系",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "kp_name": {
                            "type": "string",
                            "description": "知识点名称"
                        }
                    },
                    "required": ["kp_name"]
                }
            }
        }
    ]

    def _execute_tool(self, tool_name: str, args: dict) -> str:
        """执行工具调用"""
        try:
            if tool_name == 'get_student_weak_points':
                from services.diagnosis import detect_weak_points
                result = detect_weak_points(args.get('student_id'))
            elif tool_name == 'get_knowledge_point_info':
                from models.knowledge_point import KnowledgePoint
                from models.prerequisite import Prerequisite
                from models.learning_record import LearningRecord
                from sqlalchemy import func
                kp_name = args.get('kp_name', '')
                student_id = args.get('student_id')
                kp = KnowledgePoint.query.filter_by(name=kp_name, is_active=True).first()
                if not kp:
                    return json.dumps({"error": f"未找到知识点: {kp_name}"}, ensure_ascii=False)
                prereqs = Prerequisite.query.filter_by(target_kp_id=kp.id).all()
                successors = Prerequisite.query.filter_by(prerequisite_kp_id=kp.id).all()
                
                result = {
                    "kp_id": kp.id,
                    "kp_name": kp.name,
                    "chapter": kp.chapter,
                    "chapter_order": kp.chapter_order,
                    "description": kp.description,
                    "difficulty": kp.difficulty,
                    "importance": kp.importance,
                    "estimated_minutes": kp.estimated_minutes,
                    "prerequisites": [p.prerequisite_kp.name for p in prereqs],
                    "successors": [s.target_kp.name for s in successors]
                }
                
                if student_id:
                    rec = LearningRecord.query.filter_by(student_id=student_id, kp_id=kp.id).order_by(LearningRecord.id.desc()).first()
                    result['student_score'] = rec.quiz_score if rec else None
                    result['student_progress'] = rec.progress_percent if rec else 0
                    
                    prereq_scores = {}
                    for p in prereqs:
                        p_rec = LearningRecord.query.filter_by(student_id=student_id, kp_id=p.prerequisite_kp_id).order_by(LearningRecord.id.desc()).first()
                        prereq_scores[p.prerequisite_kp.name] = p_rec.quiz_score if p_rec else None
                    result['prerequisite_scores'] = prereq_scores
                
                succ_scores = {}
                for s in successors:
                    s_rec = LearningRecord.query.filter_by(student_id=student_id, kp_id=s.target_kp_id).order_by(LearningRecord.id.desc()).first() if student_id else None
                    succ_scores[s.target_kp.name] = s_rec.quiz_score if s_rec else None
                result['successor_scores'] = succ_scores
            elif tool_name == 'get_learning_path':
                from models.knowledge_point import KnowledgePoint
                from services.recommendation import get_learning_path_for_kp
                target_name = args.get('target_kp_name', '')
                student_id = args.get('student_id')
                kp = KnowledgePoint.query.filter_by(name=target_name, is_active=True).first()
                if not kp:
                    return json.dumps({"error": f"未找到知识点: {target_name}"}, ensure_ascii=False)
                result = get_learning_path_for_kp(kp.id, student_id)
            elif tool_name == 'get_student_learning_summary':
                from sqlalchemy import func
                from models.knowledge_point import KnowledgePoint
                from models.learning_record import LearningRecord
                from services.diagnosis import detect_weak_points
                student_id = args.get('student_id')
                avg_score = LearningRecord.query.filter_by(student_id=student_id).with_entities(
                    func.avg(LearningRecord.quiz_score)).scalar() or 0
                studied_count = LearningRecord.query.filter_by(student_id=student_id).with_entities(
                    func.count(LearningRecord.kp_id.distinct())).scalar() or 0
                total_kps = KnowledgePoint.query.filter_by(is_active=True).count()
                weak_analysis = detect_weak_points(student_id)
                result = {
                    "avg_score": float(avg_score),
                    "studied_count": studied_count,
                    "total_kps": total_kps,
                    "progress": round(studied_count / total_kps * 100, 1) if total_kps else 0,
                    "absolute_weak_count": len(weak_analysis.get('absolute_weak', [])),
                    "relative_weak_count": len(weak_analysis.get('relative_weak', [])),
                    "high_risk_count": len(weak_analysis.get('high_risk_weak', [])),
                    "forgetting_count": len(weak_analysis.get('forgetting_trend', []))
                }
            elif tool_name == 'get_knowledge_point_neighbors':
                from services.neo4j_service import neo4j_service
                kp_name = args.get('kp_name', '')
                from models.knowledge_point import KnowledgePoint
                kp = KnowledgePoint.query.filter_by(name=kp_name, is_active=True).first()
                if not kp:
                    return json.dumps({"error": f"未找到知识点: {kp_name}"}, ensure_ascii=False)
                result = neo4j_service.get_knowledge_point_neighbors(kp.code)
            else:
                return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def _agent_chat(self, question: str, student_id: int, max_iterations: int = 5) -> str:
        """Agent模式对话：LLM自主决定调用工具"""
        if self.mock_mode or not self.api_key:
            return self._mock_response([{'role': 'user', 'content': question}])

        messages = [
            {
                'role': 'system',
                'content': """你是一位专业的计算机组成原理课程AI导师，能够利用知识图谱和学生的学习数据提供精准个性化建议。

你的核心能力：
1. 理解学生的自然语言问题，判断需要哪些学习数据
2. 自主调用工具获取学生的薄弱点检测结果、知识点关系、学习路径等信息
3. 根据获取的数据，结合你的专业知识，给出个性化学习建议

工具使用策略：
- 当学生问"需要先学什么"、"学习路径"、"前置知识"时，调用 get_learning_path 获取完整学习路径
- 当学生问"薄弱点"、"分析我的学习"、"学习情况"时，调用 get_student_weak_points 获取薄弱点检测
- 当学生询问特定知识点时，调用 get_knowledge_point_info 获取知识点详情和关系
- 当需要综合分析学生学习状态时，调用 get_student_learning_summary
- 如果需要了解知识点之间的前后关系，调用 get_knowledge_point_neighbors

请根据学生的问题，灵活组合使用工具，确保回答精准、个性化。"""
            },
            {'role': 'user', 'content': question}
        ]

        for iteration in range(max_iterations):
            url = f"{self.api_base}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": self._agent_tools,
                "tool_choice": "auto",
                "temperature": 0.7,
                "max_tokens": 1000
            }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                result = resp.json()
                choice = result["choices"][0]
                message = choice["message"]

                tool_calls = message.get("tool_calls", [])
                if not tool_calls:
                    return message.get("content", "抱歉，我无法回答这个问题。")

                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    try:
                        tool_args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    if 'student_id' not in tool_args:
                        tool_args['student_id'] = student_id

                    tool_result = self._execute_tool(tool_name, tool_args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_name,
                        "content": tool_result
                    })

            except Exception as e:
                logger.error(f"Agent chat iteration {iteration} error: {e}")
                return self._mock_response([{'role': 'user', 'content': question}])

        return "抱歉，我在处理您的问题时遇到了困难，请稍后重试。"

    def _chat(self, messages: list, max_tokens: int = 800) -> str:
        """调用真实大模型API，失败时降级到模拟回复"""
        if self.mock_mode or not self.api_key:
            logger.info(f"LLM mode: mock (mock_mode={self.mock_mode}, api_key_set={bool(self.api_key)})")
            return self._mock_response(messages)

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        try:
            logger.info(f"LLM API call: model={self.model}, url={url}, messages_count={len(messages)}, max_tokens={max_tokens}")
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            logger.info(f"LLM API response: success, content_length={len(content)}")
            return content
        except Exception as e:
            logger.error(f"LLM API error: {e}, status_code={resp.status_code if 'resp' in dir() else 'N/A'}")
            return self._mock_response(messages)

    # ---------- 以下为业务方法 ----------

    def answer_learning_question(self, question: str, context: dict = None) -> str:
        """智能问答：结合知识图谱和薄弱点给出回答（兼容旧接口）"""
        student_id = context.get('student_id') if context else None

        if student_id:
            from services.diagnosis import detect_weak_points
            from services.neo4j_service import neo4j_service
            from models.knowledge_point import KnowledgePoint
            from models.prerequisite import Prerequisite
            from models.learning_record import LearningRecord
            from sqlalchemy import func

            weak_analysis = detect_weak_points(student_id)

            abs_weak = weak_analysis.get('absolute_weak', [])
            rel_weak = weak_analysis.get('relative_weak', [])
            high_risk = weak_analysis.get('high_risk_weak', [])
            forgetting = weak_analysis.get('forgetting_trend', [])
            personal_avg = weak_analysis.get('summary', {}).get('personal_avg', 0)

            studied_kps = LearningRecord.query.filter_by(student_id=student_id).with_entities(
                LearningRecord.kp_id.distinct()).all()
            studied_kp_ids = [row[0] for row in studied_kps]
            studied_kp_names = []
            if studied_kp_ids:
                studied_kps_obj = KnowledgePoint.query.filter(KnowledgePoint.id.in_(studied_kp_ids)).all()
                studied_kp_names = [kp.name for kp in studied_kps_obj]

            total_kps = KnowledgePoint.query.filter_by(is_active=True).count()
            studied_count = len(studied_kp_ids)

            all_kps = KnowledgePoint.query.filter_by(is_active=True).all()
            kp_map_by_id = {kp.id: kp for kp in all_kps}

            # 批量预加载所有前驱关系（修复原N+1查询：原为每个知识点循环查2次Prerequisite+懒加载.name）
            all_prereqs = Prerequisite.query.all()
            prereq_map = {}   # {target_kp_id: [prerequisite_kp_id, ...]}
            successor_map = {}  # {prerequisite_kp_id: [target_kp_id, ...]}
            for p in all_prereqs:
                prereq_map.setdefault(p.target_kp_id, []).append(p.prerequisite_kp_id)
                successor_map.setdefault(p.prerequisite_kp_id, []).append(p.target_kp_id)

            kp_relations = {}
            for kp in all_kps:
                prereq_ids = prereq_map.get(kp.id, [])
                successor_ids = successor_map.get(kp.id, [])
                kp_relations[kp.name] = {
                    'prerequisites': [kp_map_by_id[pid].name for pid in prereq_ids if pid in kp_map_by_id],
                    'successors': [kp_map_by_id[sid].name for sid in successor_ids if sid in kp_map_by_id],
                    'chapter': kp.chapter
                }

            prompt = f"""你是一位专业的计算机组成原理课程AI导师，需要结合学生的真实学习数据给出精准个性化建议。

【学生学习数据】
- 学生ID：{student_id}
- 个人平均分：{personal_avg:.1f}
- 已学知识点数：{studied_count}/{total_kps}
- 已学知识点：{studied_kp_names}

【薄弱点检测结果】
1. 绝对薄弱（<60分）：{[w['kp_name'] for w in abs_weak] if abs_weak else '无'}
2. 相对薄弱（低于个人平均20%）：{[w['kp_name'] for w in rel_weak] if rel_weak else '无'}
3. 高危薄弱（薄弱且为其他知识点前置）：{[w['kp_name'] for w in high_risk] if high_risk else '无'}
4. 遗忘趋势（学习次数增加但分数下降）：{[w['kp_name'] for w in forgetting] if forgetting else '无'}

【知识图谱关系（所有知识点的前后置关系）】
{chr(10).join([f"- 「{name}」：前置={info['prerequisites']}，后续={info['successors']}（章节：{info['chapter']}）" for name, info in kp_relations.items()])}

【用户问题】
{question}

请严格基于以上数据回答：
1. 如果问题涉及"需要先学什么"、"学习路径"、"前置知识"，必须结合知识图谱中的前置关系和学生薄弱点给出建议
2. 如果问题涉及薄弱点分析，必须引用学生真实的薄弱点数据
3. 如果问题涉及特定知识点，必须检查该知识点的前置要求和学生掌握状态
4. 回答要个性化、针对性强，不能泛泛而谈
5. 分点清晰，语言简洁易懂"""

            messages = [
                {'role': 'system', 'content': '你是计算机组成原理AI导师，必须结合学生的真实学习数据和知识图谱关系给出精准个性化建议。'},
                {'role': 'user', 'content': prompt}
            ]
            return self._chat(messages, max_tokens=1200)

        from services.neo4j_service import neo4j_service

        target_kp = context.get('target_kp')
        prereq_names = []
        succ_names = []
        if target_kp:
            neighbors = neo4j_service.get_knowledge_point_neighbors(target_kp)
            prereq_names = [p['name'] for p in neighbors.get('prerequisites', [])]
            succ_names = [s['name'] for s in neighbors.get('successors', [])]
            weak_summary = context.get('weak_summary', {})
            abs_weak = weak_summary.get('absolute_weak', [])
            rel_weak = weak_summary.get('relative_weak', [])
            high_risk = weak_summary.get('high_risk_weak', [])
            forgetting = weak_summary.get('forgetting_trend', [])
            avg_score = weak_summary.get('personal_avg', 0)

            prompt = f"""
        用户问题：{question}
        目标知识点：{target_kp or '未知'}
        前置知识点（来自知识图谱）：{prereq_names}
        后续知识点：{succ_names}

        学生当前学习状况：
        - 个人平均分：{avg_score:.1f}
        - 绝对薄弱知识点（<60分）：{abs_weak if abs_weak else '无'}
        - 相对薄弱知识点（低于个人平均20%）：{rel_weak if rel_weak else '无'}
        - 高危薄弱知识点（阻塞后续学习）：{high_risk if high_risk else '无'}
        - 遗忘趋势知识点：{forgetting if forgetting else '无'}

        请基于以上信息，针对该学生的具体情况，给出清晰、分点、个性化的学习建议。
        尤其注意：如果学生提问中包含"需要先学什么"，请结合薄弱点和前驱关系给出路径建议；
        如果提问涉及某个知识点的学习，请指出该学生在该知识点上可能存在的薄弱点，并提出针对性策略。
        """

            messages = [
                {'role': 'system',
                 'content': '你是计算机组成原理AI导师，能够利用知识图谱和学生的学习数据提供精准个性化建议。'},
                {'role': 'user', 'content': prompt}
            ]
            return self._chat(messages, max_tokens=800)
        else:
            messages = [
                {'role': 'system', 'content': '你是计算机组成原理AI助手。'},
                {'role': 'user', 'content': question}
            ]
            return self._chat(messages, max_tokens=800)

    def generate_student_advice(self, student_name: str, weak_analysis: dict, recommendations: list) -> str:
        """生成学生个性化学习建议"""
        summary = weak_analysis.get('summary', {})
        abs_weak = weak_analysis.get('absolute_weak', [])
        rel_weak = weak_analysis.get('relative_weak', [])
        forgetting = weak_analysis.get('forgetting_trend', [])

        prompt = f"""你是一位经验丰富的计算机组成原理教师，请根据以下学生数据为学生"{student_name}"提供个性化学习建议。

学习数据：
- 已学知识点数：{summary.get('total_kps_studied', 0)}
- 个人平均分：{summary.get('personal_avg', 0):.1f}
- 绝对薄弱（<60分）：{[w['kp_name'] for w in abs_weak]}
- 相对薄弱知识点：{[w['kp_name'] for w in rel_weak]}
- 遗忘趋势知识点：{[w['kp_name'] for w in forgetting]}
- Top推荐学习：{[r['kp_name'] for r in recommendations[:3]]}

请提供：
1. 整体学习状态评价（2-3句话）
2. 薄弱点分析（指出最需要关注的2-3个知识点）
3. 学习建议（具体可行的3条建议）
4. 激励语（1句）

请用中文回答，语气友好鼓励。"""
        messages = [
            {'role': 'system', 'content': '你是一位专业的计算机组成原理课程AI助教。'},
            {'role': 'user', 'content': prompt}
        ]
        return self._chat(messages, max_tokens=600)

    def generate_teacher_advice(self, class_analysis: list, top_n: int = 5) -> str:
        """生成教师教学建议"""
        sorted_kps = sorted(class_analysis, key=lambda x: x['avg_score'])
        worst_kps = sorted_kps[:top_n]
        prompt = f"""你是一位教学管理专家，请根据以下班级数据为教师提供教学建议。

班级学习数据（按掌握程度从差到好排序的知识点）：
"""
        for kp in worst_kps:
            prompt += f"- 「{kp['kp_name']}」：班级均分{kp['avg_score']:.1f}，不及格率{kp.get('fail_rate', kp.get('weak_rate', 0))}%，参与学生{kp['student_count']}人\n"

        prompt += """
请提供：
1. 班级学习情况总体评估
2. 最需要重点讲解的3个知识点及原因
3. 针对性教学建议（3条）
4. 是否需要调整教学计划的建议

请用中文回答，简洁专业。"""
        messages = [
            {'role': 'system', 'content': '你是一位专业的高校教学顾问。'},
            {'role': 'user', 'content': prompt}
        ]
        return self._chat(messages, max_tokens=600)

    def generate_learning_plan_content(self, student_data: dict, recommendations: list) -> str:
        """生成学习计划文本（用于PDF）"""
        prompt = f"""请为学生"{student_data.get('name', '同学')}"生成一份详细的计算机组成原理个人学习计划。

当前情况：
- 平均分：{student_data.get('avg_score', 0):.1f}
- 已学知识点：{student_data.get('studied_count', 0)}个
- 薄弱知识点数：{student_data.get('weak_count', 0)}个

推荐学习顺序：
{chr(10).join([f"{i+1}. 「{r['kp_name']}」- {r['reason']}" for i, r in enumerate(recommendations[:5])])}

请生成包含以下部分的学习计划（Markdown格式）：
## 一、学习目标
## 二、当前诊断
## 三、分阶段学习计划（第1-2周、第3-4周）
## 四、每日学习建议
## 五、复习策略"""
        messages = [
            {'role': 'system', 'content': '你是专业的学习规划师，擅长制定个性化学习计划。'},
            {'role': 'user', 'content': prompt}
        ]
        return self._chat(messages, max_tokens=1000)

    def explain_quiz_result(self, kp_name: str, score: float, correct_count: int,
                            total: int, answer_details: list) -> str:
        """AI讲解测验结果：针对学生做错的题目给出详细解析和学习建议"""
        wrong_items = [d for d in answer_details if not d.get('is_correct', False)]
        all_items = answer_details

        prompt = f"""你是一位专业的计算机组成原理课程AI助教。学生刚完成了知识点「{kp_name}」的测验，请根据测验结果为学生提供个性化讲解。

【测验结果】
- 得分：{score:.0f}分（{correct_count}/{total}题正确）
- {'全部正确，表现出色！' if correct_count == total else f'做错了{len(wrong_items)}道题'}

【错题详情】
"""
        for i, item in enumerate(wrong_items, 1):
            prompt += f"""
错题{i}：{item.get('question_text', '')[:100]}
  学生答案：{item.get('student_answer', '未作答')}
  正确答案：{item.get('correct_answer', '')}
  基础解析：{item.get('explanation', '暂无')}
"""

        prompt += """
请为学生提供以下内容：
1. **总体评价**（1-2句话评价本次测验表现）
2. **错题详细讲解**（针对每道错题，用通俗易懂的语言解释为什么正确答案是对的，学生可能混淆了什么概念）
3. **知识点巩固建议**（针对薄弱环节，给出具体的学习建议）

请用中文回答，语气亲切鼓励，让学生感到被支持。"""

        messages = [
            {'role': 'system', 'content': '你是一位耐心专业的计算机组成原理AI助教，擅长用通俗易懂的方式讲解错题。'},
            {'role': 'user', 'content': prompt}
        ]
        return self._chat(messages, max_tokens=1200)

    def analyze_weak_points(self, student_id: int, personal_avg: float,
                            absolute_weak: list, relative_weak: list,
                            high_risk_weak: list, forgetting_trend: list) -> str:
        """AI分析薄弱点：给出综合分析和改进建议"""
        prompt = f"""你是一位专业的计算机组成原理课程AI助教，请根据以下学生的多维度薄弱点检测结果进行综合分析。

【学生数据】
- 学生ID：{student_id}
- 个人平均分：{personal_avg:.1f}分

【多维度薄弱点检测结果】
1. 绝对薄弱（<60分）：{[w['kp_name'] for w in absolute_weak] if absolute_weak else '无'}
2. 相对薄弱（低于个人平均20%）：{[w['kp_name'] for w in relative_weak] if relative_weak else '无'}
3. 高危薄弱（薄弱且阻塞后继知识点）：{[w['kp_name'] for w in high_risk_weak] if high_risk_weak else '无'}
4. 遗忘趋势（学习次数增加但分数下降）：{[w['kp_name'] for w in forgetting_trend] if forgetting_trend else '无'}

请提供：
1. **综合分析**：从四个维度总结学生的学习状态，指出最需要关注的问题
2. **重点改进建议**：针对高危薄弱和绝对薄弱知识点，给出具体的改进策略
3. **复习策略**：针对遗忘趋势知识点，给出防遗忘复习建议
4. **学习优先级**：建议学生下一步应该优先学习哪些知识点

请用中文回答，分点清晰，语言通俗易懂。"""

        messages = [
            {'role': 'system', 'content': '你是一位专业的计算机组成原理课程AI助教，擅长分析学生学习数据并提供个性化建议。'},
            {'role': 'user', 'content': prompt}
        ]
        return self._chat(messages, max_tokens=800)

    # ---------- 兼容旧方法（供原有代码调用） ----------
    def gen_student_suggest(self, student_name: str, weak_data: dict, record_list: list, top5_recommend: list):
        return self.generate_student_advice(student_name, weak_data, top5_recommend)

    def teacher_class_analysis(self, class_data: list, knowledge_stat: dict):
        return self.generate_teacher_advice(class_data, top_n=5)

    def gen_study_plan_text(self, student_info: dict, weak_points: dict, recommend_list: list):
        return self.generate_learning_plan_content(student_info, recommend_list)

    # ---------- 模拟回复（API失败时降级） ----------
    def _mock_response(self, messages: list) -> str:
        last_msg = messages[-1]['content'] if messages else ''
        if '综合分析' in last_msg and '绝对薄弱' in last_msg:
            return """## 综合分析
从四个维度来看，你的学习状态呈现出明显的薄弱环节分布。绝对薄弱和高危薄弱知识点是当前最需要关注的问题，这些知识点不仅分数低，还会阻塞后续知识点的学习。

## 重点改进建议
1. **优先攻克高危薄弱知识点**：这些知识点是其他多个知识点的前置条件，掌握它们能解锁更多学习内容
2. **集中突破绝对薄弱**：对于分数低于60分的知识点，建议回到学习材料重新学习，配合测验检验效果
3. **建立复习习惯**：对于遗忘趋势知识点，建议采用间隔重复法进行复习

## 复习策略
针对遗忘趋势知识点，建议：
- 学习后第2天、第7天、第14天分别进行复习
- 每次复习时先做测验，再根据错题针对性回顾
- 制作知识点卡片，利用碎片时间进行记忆

## 学习优先级
建议按照以下顺序学习：
1. 高危薄弱知识点（阻塞最多后继）
2. 绝对薄弱知识点（分数<60）
3. 相对薄弱知识点（低于个人平均）
4. 遗忘趋势知识点（需复习巩固）"""
        elif '学习建议' in last_msg or '薄弱' in last_msg:
            return "根据您的学习情况，建议先巩固绝对薄弱的知识点，再逐步攻克相对薄弱和高危薄弱内容。每日可安排30-60分钟学习，配合知识点测验检验效果。"
        elif '教学建议' in last_msg or '班级' in last_msg:
            return "班级整体在存储系统和CPU设计章节掌握较弱，建议增加专题讲解和习题训练，重点关注Cache和流水线冲突处理。"
        elif '学习计划' in last_msg:
            return "建议第1-2周主攻薄弱知识点，第3-4周进行综合复习和模拟测验，每天保持40分钟学习。"
        elif '需要先学' in last_msg or '学习路径' in last_msg:
            return "学习任何知识点前，建议先检查其前置知识是否已掌握。您可以查看知识点详情页面了解前置关系，系统会自动为您推荐最佳学习路径。"
        elif '错题' in last_msg or '讲解' in last_msg or '测验结果' in last_msg:
            return "## 总体评价\n本次测验有一定进步空间，错题主要集中在概念理解上，建议结合教材重新复习相关知识点。\n\n## 错题讲解\n请仔细对照正确答案，理解每个选项的区别。对于做错的题目，建议回到学习材料中找到对应的章节重新阅读。\n\n## 巩固建议\n1. 针对错题涉及的概念，重新阅读学习材料\n2. 尝试用自己的话复述每个概念\n3. 过几天后重新测验，检验是否真正掌握"
        else:
            return "您好！我是计算机组成原理AI助手，可以为您提供学习路径建议、薄弱点分析和学习计划。请问有什么可以帮助您的？"


llm_service = LLMService()