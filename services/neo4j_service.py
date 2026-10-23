"""
Neo4j 知识图谱服务

基于 neo4j Python 驱动（4.4.x，兼容 Neo4j 4.2.3 + JDK11）
提供知识图谱的CRUD、着色查询、路径查询等功能
"""
from neo4j import GraphDatabase
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class Neo4jService:
    """Neo4j 服务封装"""

    def __init__(self):
        self._driver = None


    def init_app(self, app):
        uri = app.config['NEO4J_URI']
        user = app.config['NEO4J_USER']
        password = app.config['NEO4J_PASSWORD']
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def get_driver(self):
        if self._driver is None:
            uri = current_app.config['NEO4J_URI']
            user = current_app.config['NEO4J_USER']
            password = current_app.config['NEO4J_PASSWORD']
            self._driver = GraphDatabase.driver(uri, auth=(user, password))
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def run_query(self, query: str, parameters: dict = None) -> list:
        """执行Cypher查询"""
        driver = self.get_driver()
        try:
            with driver.session() as session:
                result = session.run(query, parameters or {})
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Neo4j query error: {e}\nQuery: {query}")
            return []

    # ========== 知识点节点操作 ==========

    def create_knowledge_point(self, kp_data: dict) -> str:
        """创建知识点节点"""
        query = """
        MERGE (kp:KnowledgePoint {code: $code})
        SET kp.name = $name,
            kp.chapter = $chapter,
            kp.chapter_order = $chapter_order,
            kp.description = $description,
            kp.difficulty = $difficulty,
            kp.importance = $importance,
            kp.mysql_id = $mysql_id
        RETURN id(kp) as neo4j_id
        """
        result = self.run_query(query, kp_data)
        return str(result[0]['neo4j_id']) if result else None

    def create_prerequisite_relation(self, from_code: str, to_code: str,
                                      relation_type: str = 'MUST',
                                      weight: float = 1.0) -> bool:
        """创建前驱关系"""
        query = """
        MATCH (from:KnowledgePoint {code: $from_code})
        MATCH (to:KnowledgePoint {code: $to_code})
        MERGE (from)-[r:PREREQUISITE_OF {type: $relation_type}]->(to)
        SET r.weight = $weight
        RETURN r
        """
        result = self.run_query(query, {
            'from_code': from_code,
            'to_code': to_code,
            'relation_type': relation_type,
            'weight': weight
        })
        return len(result) > 0

    def get_all_knowledge_points(self) -> list:
        """获取所有知识点节点"""
        query = """
        MATCH (kp:KnowledgePoint)
        RETURN kp.code as code, kp.name as name, kp.chapter as chapter,
               kp.chapter_order as chapter_order, kp.difficulty as difficulty,
               kp.importance as importance, kp.mysql_id as mysql_id,
               id(kp) as neo4j_id
        ORDER BY kp.chapter_order, kp.name
        """
        return self.run_query(query)

    def get_all_relations(self) -> list:
        """获取所有前驱关系（用于图谱渲染）"""
        query = """
        MATCH (from:KnowledgePoint)-[r:PREREQUISITE_OF]->(to:KnowledgePoint)
        RETURN from.code as source, to.code as target,
               r.type as relation_type, r.weight as weight,
               from.name as source_name, to.name as target_name
        """
        return self.run_query(query)

    def get_knowledge_graph_with_color(self, student_scores: dict) -> dict:
        """
        获取带着色信息的知识图谱数据
        student_scores: {kp_code: score} 或 {mysql_id: score}
        着色规则：
          绿色(#52c41a)：≥60分
          黄色(#faad14)：40-59分
          红色(#ff4d4f)：<40分
          灰色(#d9d9d9)：未学习
        """
        nodes = self.get_all_knowledge_points()
        edges = self.get_all_relations()

        colored_nodes = []
        for node in nodes:
            mysql_id = node.get('mysql_id')
            score = student_scores.get(mysql_id) or student_scores.get(node['code'])

            if score is None:
                color = '#d9d9d9'  # 灰：未学习
                status = 'unlearned'
            elif score >= 60:
                color = '#52c41a'  # 绿：掌握
                status = 'mastered'
            elif score >= 40:
                color = '#faad14'  # 黄：部分掌握
                status = 'partial'
            else:
                color = '#ff4d4f'  # 红：未掌握
                status = 'weak'

            colored_nodes.append({
                'id': str(node.get('neo4j_id')),  # 转为字符串
                'name': node['name'],
                'code': node['code'],
                'chapter': node.get('chapter', ''),
                'difficulty': node.get('difficulty'),
                'importance': node.get('importance'),
                'score': score,
                'color': color,
                'status': status,
                'symbolSize': 20 + (node.get('importance', 3) * 5),
                'itemStyle': {'color': color},
                'label': {'show': True}
            })

        return {
            'nodes': colored_nodes,
            'edges': edges
        }

    def find_learning_path(self, target_code: str, max_depth: int = 10) -> list:
        """查找到达目标知识点的完整前驱链"""
        query = """
        MATCH path = (start:KnowledgePoint)-[:PREREQUISITE_OF*1..{max_depth}]->(target:KnowledgePoint {code: $target_code})
        WHERE NOT ()-[:PREREQUISITE_OF]->(start)
        RETURN [node in nodes(path) | {code: node.code, name: node.name, chapter: node.chapter}] as path_nodes
        LIMIT 10
        """.replace('{max_depth}', str(max_depth))
        return self.run_query(query, {'target_code': target_code})

    def get_chapter_statistics(self) -> list:
        """按章节统计知识点数量"""
        query = """
        MATCH (kp:KnowledgePoint)
        RETURN kp.chapter as chapter, kp.chapter_order as chapter_order,
               count(kp) as kp_count
        ORDER BY kp.chapter_order
        """
        return self.run_query(query)

    def get_knowledge_point_neighbors(self, kp_code: str) -> dict:
        """获取某知识点的前驱和后继"""
        query = """
        MATCH (kp:KnowledgePoint {code: $kp_code})
        OPTIONAL MATCH (pre:KnowledgePoint)-[:PREREQUISITE_OF]->(kp)
        OPTIONAL MATCH (kp)-[:PREREQUISITE_OF]->(post:KnowledgePoint)
        RETURN collect(distinct {code: pre.code, name: pre.name}) as prerequisites,
               collect(distinct {code: post.code, name: post.name}) as successors
        """
        result = self.run_query(query, {'kp_code': kp_code})
        if result:
            return {
                'prerequisites': [p for p in result[0]['prerequisites'] if p['code']],
                'successors': [s for s in result[0]['successors'] if s['code']]
            }
        return {'prerequisites': [], 'successors': []}

    def batch_create_knowledge_points(self, kp_list: list) -> int:
        """批量创建知识点"""
        query = """
        UNWIND $kp_list as kp
        MERGE (n:KnowledgePoint {code: kp.code})
        SET n.name = kp.name,
            n.chapter = kp.chapter,
            n.chapter_order = kp.chapter_order,
            n.description = kp.description,
            n.difficulty = kp.difficulty,
            n.importance = kp.importance,
            n.mysql_id = kp.mysql_id
        """
        self.run_query(query, {'kp_list': kp_list})
        return len(kp_list)

    def batch_create_relations(self, relations: list) -> int:
        """批量创建前驱关系"""
        query = """
        UNWIND $relations as rel
        MATCH (from:KnowledgePoint {code: rel.from_code})
        MATCH (to:KnowledgePoint {code: rel.to_code})
        MERGE (from)-[r:PREREQUISITE_OF {type: rel.type}]->(to)
        SET r.weight = rel.weight
        """
        self.run_query(query, {'relations': relations})
        return len(relations)


# 全局单例
neo4j_service = Neo4jService()
