# -*- coding: utf-8 -*-
import sys
import jieba
import networkx as nx
import matplotlib.pyplot as plt
import math
from collections import Counter
import datetime
import random
import time
import os
from dotenv import load_dotenv
import pymongo
from loguru import logger
from pathlib import Path
from snownlp import SnowNLP
# from chat.config import global_config
sys.path.append("C:/GitHub/MaiMBot")  # 添加项目根目录到 Python 路径
from src.common.database import Database  
from src.plugins.memory_system.offline_llm import LLMModel

# 获取当前文件的目录
current_dir = Path(__file__).resolve().parent
# 获取项目根目录（上三层目录）
project_root = current_dir.parent.parent.parent
# env.dev文件路径
env_path = project_root / ".env.dev"

# 加载环境变量
if env_path.exists():
    logger.info(f"从 {env_path} 加载环境变量")
    load_dotenv(env_path)
else:
    logger.warning(f"未找到环境变量文件: {env_path}")
    logger.info("将使用默认配置")

class Database:
    _instance = None
    db = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        if not Database.db:
            Database.initialize(
                host=os.getenv("MONGODB_HOST"),
                port=int(os.getenv("MONGODB_PORT")),
                db_name=os.getenv("DATABASE_NAME"),
                username=os.getenv("MONGODB_USERNAME"),
                password=os.getenv("MONGODB_PASSWORD"),
                auth_source=os.getenv("MONGODB_AUTH_SOURCE")
            )
            
    @classmethod
    def initialize(cls, host, port, db_name, username=None, password=None, auth_source="admin"):
        try:
            if username and password:
                uri = f"mongodb://{username}:{password}@{host}:{port}/{db_name}?authSource={auth_source}"
            else:
                uri = f"mongodb://{host}:{port}"
                
            client = pymongo.MongoClient(uri)
            cls.db = client[db_name]
            # 测试连接
            client.server_info()
            logger.success("MongoDB连接成功!")
            
        except Exception as e:
            logger.error(f"初始化MongoDB失败: {str(e)}")
            raise



def calculate_information_content(text):
    """计算文本的信息量（熵）"""
    char_count = Counter(text)
    total_chars = len(text)
    
    entropy = 0
    for count in char_count.values():
        probability = count / total_chars
        entropy -= probability * math.log2(probability)
    
    return entropy

def get_cloest_chat_from_db(db, length: int, timestamp: str):
    """从数据库中获取最接近指定时间戳的聊天记录"""
    chat_text = ''
    closest_record = db.db.messages.find_one({"time": {"$lte": timestamp}}, sort=[('time', -1)])
    
    if closest_record:
        closest_time = closest_record['time']
        group_id = closest_record['group_id']  # 获取groupid
        # 获取该时间戳之后的length条消息，且groupid相同
        chat_record = list(db.db.messages.find({"time": {"$gt": closest_time}, "group_id": group_id}).sort('time', 1).limit(length))
        for record in chat_record:
            chat_text += record["detailed_plain_text"]
        return chat_text
    
    return ''

class Memory_graph:
    def __init__(self):
        self.G = nx.Graph()  # 使用 networkx 的图结构
        self.db = Database.get_instance()
        
    def connect_dot(self, concept1, concept2):
        # 如果边已存在，增加 strength
        if self.G.has_edge(concept1, concept2):
            self.G[concept1][concept2]['strength'] = self.G[concept1][concept2].get('strength', 1) + 1
        else:
            # 如果是新边，初始化 strength 为 1
            self.G.add_edge(concept1, concept2, strength=1)
    
    def add_dot(self, concept, memory):
        if concept in self.G:
            # 如果节点已存在，将新记忆添加到现有列表中
            if 'memory_items' in self.G.nodes[concept]:
                if not isinstance(self.G.nodes[concept]['memory_items'], list):
                    # 如果当前不是列表，将其转换为列表
                    self.G.nodes[concept]['memory_items'] = [self.G.nodes[concept]['memory_items']]
                self.G.nodes[concept]['memory_items'].append(memory)
            else:
                self.G.nodes[concept]['memory_items'] = [memory]
        else:
            # 如果是新节点，创建新的记忆列表
            self.G.add_node(concept, memory_items=[memory])
        
    def get_dot(self, concept):
        # 检查节点是否存在于图中
        if concept in self.G:
            # 从图中获取节点数据
            node_data = self.G.nodes[concept]
            return concept, node_data
        return None

    def get_related_item(self, topic, depth=1):
        if topic not in self.G:
            return [], []
            
        first_layer_items = []
        second_layer_items = []
        
        # 获取相邻节点
        neighbors = list(self.G.neighbors(topic))
        
        # 获取当前节点的记忆项
        node_data = self.get_dot(topic)
        if node_data:
            concept, data = node_data
            if 'memory_items' in data:
                memory_items = data['memory_items']
                if isinstance(memory_items, list):
                    first_layer_items.extend(memory_items)
                else:
                    first_layer_items.append(memory_items)
        
        # 只在depth=2时获取第二层记忆
        if depth >= 2:
            # 获取相邻节点的记忆项
            for neighbor in neighbors:
                node_data = self.get_dot(neighbor)
                if node_data:
                    concept, data = node_data
                    if 'memory_items' in data:
                        memory_items = data['memory_items']
                        if isinstance(memory_items, list):
                            second_layer_items.extend(memory_items)
                        else:
                            second_layer_items.append(memory_items)
        
        return first_layer_items, second_layer_items
    
    @property
    def dots(self):
        # 返回所有节点对应的 Memory_dot 对象
        return [self.get_dot(node) for node in self.G.nodes()]

# 海马体 
class Hippocampus:
    def __init__(self, memory_graph: Memory_graph):
        self.memory_graph = memory_graph
        self.llm_model = LLMModel()
        self.llm_model_small = LLMModel(model_name="deepseek-ai/DeepSeek-V2.5")
        
    def get_memory_sample(self, chat_size=20, time_frequency:dict={'near':2,'mid':4,'far':3}):
        current_timestamp = datetime.datetime.now().timestamp()
        chat_text = []
        #短期：1h   中期：4h   长期：24h
        for _ in range(time_frequency.get('near')):  # 循环10次
            random_time = current_timestamp - random.randint(1, 3600)  # 随机时间
            chat_ = get_cloest_chat_from_db(db=self.memory_graph.db, length=chat_size, timestamp=random_time)
            chat_text.append(chat_)  
        for _ in range(time_frequency.get('mid')):  # 循环10次
            random_time = current_timestamp - random.randint(3600, 3600*4)  # 随机时间
            chat_ = get_cloest_chat_from_db(db=self.memory_graph.db, length=chat_size, timestamp=random_time)
            chat_text.append(chat_)  
        for _ in range(time_frequency.get('far')):  # 循环10次
            random_time = current_timestamp - random.randint(3600*4, 3600*24)  # 随机时间
            chat_ = get_cloest_chat_from_db(db=self.memory_graph.db, length=chat_size, timestamp=random_time)
            chat_text.append(chat_)
        return chat_text
    
    def calculate_topic_num(self,text, compress_rate):
        """计算文本的话题数量"""
        information_content = calculate_information_content(text)
        topic_by_length = text.count('\n')*compress_rate
        topic_by_information_content = max(1, min(5, int((information_content-3) * 2)))
        topic_num = int((topic_by_length + topic_by_information_content)/2)
        print(f"topic_by_length: {topic_by_length}, topic_by_information_content: {topic_by_information_content}, topic_num: {topic_num}")
        return topic_num
    
    async def memory_compress(self, input_text, compress_rate=0.1):
        print(input_text)
        
        #获取topics
        topic_num = self.calculate_topic_num(input_text, compress_rate)
        topics_response = await self.llm_model_small.generate_response_async(self.find_topic_llm(input_text, topic_num))
        topics = topics_response[0].split(",")
        print(f"话题: {topics}")
        
        # 创建所有话题的请求任务
        tasks = []
        for topic in topics:
            topic_what_prompt = self.topic_what(input_text, topic)
            # 创建异步任务
            task = self.llm_model_small.generate_response_async(topic_what_prompt)
            tasks.append((topic.strip(), task))
            
        # 等待所有任务完成
        compressed_memory = set()
        for topic, task in tasks:
            response = await task
            if response:
                compressed_memory.add((topic, response[0]))
                
        return compressed_memory
    
    async def operation_build_memory(self, chat_size=12):
        #最近消息获取频率
        time_frequency = {'near':1,'mid':2,'far':2}
        memory_sample = self.get_memory_sample(chat_size,time_frequency)
        
        for i, input_text in enumerate(memory_sample, 1):
            #加载进度可视化
            progress = (i / len(memory_sample)) * 100
            bar_length = 30
            filled_length = int(bar_length * i // len(memory_sample))
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            print(f"\n进度: [{bar}] {progress:.1f}% ({i}/{len(memory_sample)})")
            
            if input_text:
                # 生成压缩后记忆 ,表现为 (话题,记忆) 的元组
                compressed_memory = set()
                compress_rate = 0.15
                compressed_memory = await self.memory_compress(input_text,compress_rate)
                print(f"\033[1;33m压缩后记忆数量\033[0m: {len(compressed_memory)}")
                
                #将记忆加入到图谱中
                for topic, memory in compressed_memory:
                    # 将jieba分词结果转换为列表以便多次使用
                    topics = list(jieba.cut(topic))
                    print(f"\033[1;34m话题\033[0m: {topic}")
                    print(f"\033[1;34m分词结果\033[0m: {topics}")
                    print(f"\033[1;34m记忆\033[0m: {memory}")
                    
                    # 如果分词结果少于2个词，跳过连接
                    if len(topics) < 2:
                        print(f"\033[1;31m分词结果少于2个词，跳过连接\033[0m")
                        # 仍然添加单个节点
                        for split_topic in topics:
                            self.memory_graph.add_dot(split_topic, memory)
                        continue
                        
                    # 先添加所有节点
                    for split_topic in topics:
                        print(f"\033[1;32m添加节点\033[0m: {split_topic}")
                        self.memory_graph.add_dot(split_topic, memory)
                    
                    # 再添加节点之间的连接
                    for i, split_topic in enumerate(topics):
                        for j, other_split_topic in enumerate(topics):
                            if i < j:  # 只连接一次，避免重复连接
                                print(f"\033[1;32m连接节点\033[0m: {split_topic} 和 {other_split_topic}")
                                self.memory_graph.connect_dot(split_topic, other_split_topic)
            else:
                print(f"空消息 跳过")
            
            # 每处理完一条消息就同步一次到数据库
            self.sync_memory_to_db_2()

    def sync_memory_from_db(self):
        """
        从数据库同步数据到内存中的图结构
        将清空当前内存中的图，并从数据库重新加载所有节点和边
        """
        # 清空当前图
        self.memory_graph.G.clear()
        
        # 从数据库加载所有节点
        nodes = self.memory_graph.db.db.graph_data.nodes.find()
        for node in nodes:
            concept = node['concept']
            memory_items = node.get('memory_items', [])
            # 确保memory_items是列表
            if not isinstance(memory_items, list):
                memory_items = [memory_items] if memory_items else []
            # 添加节点到图中
            self.memory_graph.G.add_node(concept, memory_items=memory_items)
            
        # 从数据库加载所有边
        edges = self.memory_graph.db.db.graph_data.edges.find()
        for edge in edges:
            source = edge['source']
            target = edge['target']
            strength = edge.get('strength', 1)  # 获取 strength，默认为 1
            # 只有当源节点和目标节点都存在时才添加边
            if source in self.memory_graph.G and target in self.memory_graph.G:
                self.memory_graph.G.add_edge(source, target, strength=strength)
        
        logger.success("从数据库同步记忆图谱完成")
        
    def calculate_node_hash(self, concept, memory_items):
        """
        计算节点的特征值
        """
        if not isinstance(memory_items, list):
            memory_items = [memory_items] if memory_items else []
        # 将记忆项排序以确保相同内容生成相同的哈希值
        sorted_items = sorted(memory_items)
        # 组合概念和记忆项生成特征值
        content = f"{concept}:{'|'.join(sorted_items)}"
        return hash(content)

    def calculate_edge_hash(self, source, target):
        """
        计算边的特征值
        """
        # 对源节点和目标节点排序以确保相同的边生成相同的哈希值
        nodes = sorted([source, target])
        return hash(f"{nodes[0]}:{nodes[1]}")

    def sync_memory_to_db_2(self):
        """
        检查并同步内存中的图结构与数据库
        使用特征值(哈希值)快速判断是否需要更新
        """
        # 获取数据库中所有节点和内存中所有节点
        db_nodes = list(self.memory_graph.db.db.graph_data.nodes.find())
        memory_nodes = list(self.memory_graph.G.nodes(data=True))
        
        # 转换数据库节点为字典格式，方便查找
        db_nodes_dict = {node['concept']: node for node in db_nodes}
        
        # 检查并更新节点
        for concept, data in memory_nodes:
            memory_items = data.get('memory_items', [])
            if not isinstance(memory_items, list):
                memory_items = [memory_items] if memory_items else []
            
            # 计算内存中节点的特征值
            memory_hash = self.calculate_node_hash(concept, memory_items)
                
            if concept not in db_nodes_dict:
                # 数据库中缺少的节点，添加
                logger.info(f"添加新节点: {concept}")
                node_data = {
                    'concept': concept,
                    'memory_items': memory_items,
                    'hash': memory_hash
                }
                self.memory_graph.db.db.graph_data.nodes.insert_one(node_data)
            else:
                # 获取数据库中节点的特征值
                db_node = db_nodes_dict[concept]
                db_hash = db_node.get('hash', None)
                
                # 如果特征值不同，则更新节点
                if db_hash != memory_hash:
                    logger.info(f"更新节点内容: {concept}")
                    self.memory_graph.db.db.graph_data.nodes.update_one(
                        {'concept': concept},
                        {'$set': {
                            'memory_items': memory_items,
                            'hash': memory_hash
                        }}
                    )
                    
        # 检查并删除数据库中多余的节点
        memory_concepts = set(node[0] for node in memory_nodes)
        for db_node in db_nodes:
            if db_node['concept'] not in memory_concepts:
                logger.info(f"删除多余节点: {db_node['concept']}")
                self.memory_graph.db.db.graph_data.nodes.delete_one({'concept': db_node['concept']})
                
        # 处理边的信息
        db_edges = list(self.memory_graph.db.db.graph_data.edges.find())
        memory_edges = list(self.memory_graph.G.edges())
        
        # 创建边的哈希值字典
        db_edge_dict = {}
        for edge in db_edges:
            edge_hash = self.calculate_edge_hash(edge['source'], edge['target'])
            db_edge_dict[(edge['source'], edge['target'])] = {
                'hash': edge_hash,
                'num': edge.get('num', 1)
            }
            
        # 检查并更新边
        for source, target in memory_edges:
            edge_hash = self.calculate_edge_hash(source, target)
            edge_key = (source, target)
            
            if edge_key not in db_edge_dict:
                # 添加新边
                logger.info(f"添加新边: {source} - {target}")
                edge_data = {
                    'source': source,
                    'target': target,
                    'num': 1,
                    'hash': edge_hash
                }
                self.memory_graph.db.db.graph_data.edges.insert_one(edge_data)
            else:
                # 检查边的特征值是否变化
                if db_edge_dict[edge_key]['hash'] != edge_hash:
                    logger.info(f"更新边: {source} - {target}")
                    self.memory_graph.db.db.graph_data.edges.update_one(
                        {'source': source, 'target': target},
                        {'$set': {'hash': edge_hash}}
                    )
                    
        # 删除多余的边
        memory_edge_set = set(memory_edges)
        for edge_key in db_edge_dict:
            if edge_key not in memory_edge_set:
                source, target = edge_key
                logger.info(f"删除多余边: {source} - {target}")
                self.memory_graph.db.db.graph_data.edges.delete_one({
                    'source': source,
                    'target': target
                })
        
        logger.success("完成记忆图谱与数据库的差异同步")

    def find_topic_llm(self,text, topic_num):
        prompt = f'这是一段文字：{text}。请你从这段话中总结出{topic_num}个话题，帮我列出来，用逗号隔开，尽可能精简。只需要列举{topic_num}个话题就好，不要告诉我其他内容。'
        return prompt

    def topic_what(self,text, topic):
        prompt = f'这是一段文字：{text}。我想知道这记忆里有什么关于{topic}的话题，帮我总结成一句自然的话，可以包含时间和人物，以及具体的观点。只输出这句话就好'
        return prompt
    
    def remove_node_from_db(self, topic):
        """
        从数据库中删除指定节点及其相关的边
        
        Args:
            topic: 要删除的节点概念
        """
        # 删除节点
        self.memory_graph.db.db.graph_data.nodes.delete_one({'concept': topic})
        # 删除所有涉及该节点的边
        self.memory_graph.db.db.graph_data.edges.delete_many({
            '$or': [
                {'source': topic},
                {'target': topic}
            ]
        })
    
    def forget_topic(self, topic):
        """
        随机删除指定话题中的一条记忆，如果话题没有记忆则移除该话题节点
        只在内存中的图上操作，不直接与数据库交互
        
        Args:
            topic: 要删除记忆的话题
            
        Returns:
            removed_item: 被删除的记忆项，如果没有删除任何记忆则返回 None
        """
        if topic not in self.memory_graph.G:
            return None
            
        # 获取话题节点数据
        node_data = self.memory_graph.G.nodes[topic]
        
        # 如果节点存在memory_items
        if 'memory_items' in node_data:
            memory_items = node_data['memory_items']
            
            # 确保memory_items是列表
            if not isinstance(memory_items, list):
                memory_items = [memory_items] if memory_items else []
                
            # 如果有记忆项可以删除
            if memory_items:
                # 随机选择一个记忆项删除
                removed_item = random.choice(memory_items)
                memory_items.remove(removed_item)
                
                # 更新节点的记忆项
                if memory_items:
                    self.memory_graph.G.nodes[topic]['memory_items'] = memory_items
                else:
                    # 如果没有记忆项了，删除整个节点
                    self.memory_graph.G.remove_node(topic)
                    
                return removed_item
        
        return None
    
    async def operation_forget_topic(self, percentage=0.1):
        """
        随机选择图中一定比例的节点进行检查，根据条件决定是否遗忘
        
        Args:
            percentage: 要检查的节点比例，默认为0.1（10%）
        """
        # 获取所有节点
        all_nodes = list(self.memory_graph.G.nodes())
        # 计算要检查的节点数量
        check_count = max(1, int(len(all_nodes) * percentage))
        # 随机选择节点
        nodes_to_check = random.sample(all_nodes, check_count)
        
        forgotten_nodes = []
        for node in nodes_to_check:
            # 获取节点的连接数
            connections = self.memory_graph.G.degree(node)
            
            # 获取节点的内容条数
            memory_items = self.memory_graph.G.nodes[node].get('memory_items', [])
            if not isinstance(memory_items, list):
                memory_items = [memory_items] if memory_items else []
            content_count = len(memory_items)
            
            # 检查连接强度
            weak_connections = True
            if connections > 1:  # 只有当连接数大于1时才检查强度
                for neighbor in self.memory_graph.G.neighbors(node):
                    strength = self.memory_graph.G[node][neighbor].get('strength', 1)
                    if strength > 2:
                        weak_connections = False
                        break
            
            # 如果满足遗忘条件
            if (connections <= 1 and weak_connections) or content_count <= 2:
                removed_item = self.forget_topic(node)
                if removed_item:
                    forgotten_nodes.append((node, removed_item))
                    logger.info(f"遗忘节点 {node} 的记忆: {removed_item}")
        
        # 同步到数据库
        if forgotten_nodes:
            self.sync_memory_to_db_2()
            logger.info(f"完成遗忘操作，共遗忘 {len(forgotten_nodes)} 个节点的记忆")
        else:
            logger.info("本次检查没有节点满足遗忘条件")

    async def merge_memory(self, topic):
        """
        对指定话题的记忆进行合并压缩
        
        Args:
            topic: 要合并的话题节点
        """
        # 获取节点的记忆项
        memory_items = self.memory_graph.G.nodes[topic].get('memory_items', [])
        if not isinstance(memory_items, list):
            memory_items = [memory_items] if memory_items else []
            
        # 如果记忆项不足，直接返回
        if len(memory_items) < 10:
            return
            
        # 随机选择10条记忆
        selected_memories = random.sample(memory_items, 10)
        
        # 拼接成文本
        merged_text = "\n".join(selected_memories)
        print(f"\n[合并记忆] 话题: {topic}")
        print(f"选择的记忆:\n{merged_text}")
        
        # 使用memory_compress生成新的压缩记忆
        compressed_memories = await self.memory_compress(merged_text, 0.1)
        
        # 从原记忆列表中移除被选中的记忆
        for memory in selected_memories:
            memory_items.remove(memory)
            
        # 添加新的压缩记忆
        for _, compressed_memory in compressed_memories:
            memory_items.append(compressed_memory)
            print(f"添加压缩记忆: {compressed_memory}")
            
        # 更新节点的记忆项
        self.memory_graph.G.nodes[topic]['memory_items'] = memory_items
        print(f"完成记忆合并，当前记忆数量: {len(memory_items)}")
        
    async def operation_merge_memory(self, percentage=0.1):
        """
        随机检查一定比例的节点，对内容数量超过100的节点进行记忆合并
        
        Args:
            percentage: 要检查的节点比例，默认为0.1（10%）
        """
        # 获取所有节点
        all_nodes = list(self.memory_graph.G.nodes())
        # 计算要检查的节点数量
        check_count = max(1, int(len(all_nodes) * percentage))
        # 随机选择节点
        nodes_to_check = random.sample(all_nodes, check_count)
        
        merged_nodes = []
        for node in nodes_to_check:
            # 获取节点的内容条数
            memory_items = self.memory_graph.G.nodes[node].get('memory_items', [])
            if not isinstance(memory_items, list):
                memory_items = [memory_items] if memory_items else []
            content_count = len(memory_items)
            
            # 如果内容数量超过100，进行合并
            if content_count > 100:
                print(f"\n检查节点: {node}, 当前记忆数量: {content_count}")
                await self.merge_memory(node)
                merged_nodes.append(node)
        
        # 同步到数据库
        if merged_nodes:
            self.sync_memory_to_db_2()
            print(f"\n完成记忆合并操作，共处理 {len(merged_nodes)} 个节点")
        else:
            print("\n本次检查没有需要合并的节点")
        

def visualize_graph_lite(memory_graph: Memory_graph, color_by_memory: bool = False):
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
    plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号
    
    G = memory_graph.G
    
    # 创建一个新图用于可视化
    H = G.copy()    

    # 计算节点大小和颜色
    node_colors = []
    node_sizes = []
    nodes = list(H.nodes())
    
    # 获取最大记忆数用于归一化节点大小
    max_memories = 1
    for node in nodes:
        memory_items = H.nodes[node].get('memory_items', [])
        memory_count = len(memory_items) if isinstance(memory_items, list) else (1 if memory_items else 0)
        max_memories = max(max_memories, memory_count)
    
    # 计算每个节点的大小和颜色
    for node in nodes:
        # 计算节点大小（基于记忆数量）
        memory_items = H.nodes[node].get('memory_items', [])
        memory_count = len(memory_items) if isinstance(memory_items, list) else (1 if memory_items else 0)
        # 使用指数函数使变化更明显
        ratio = memory_count / max_memories
        size = 500 + 5000 * (ratio ** 2)  # 使用平方函数使差异更明显
        node_sizes.append(size)
        
        # 计算节点颜色（基于连接数）
        degree = H.degree(node)
        if degree >= 30:
            node_colors.append((1.0, 0, 0))  # 亮红色 (#FF0000)
        else:
            # 将1-10映射到0-1的范围
            color_ratio = (degree - 1) / 29.0 if degree > 1 else 0
            # 使用蓝到红的渐变
            red = min(0.9, color_ratio)
            blue = max(0.0, 1.0 - color_ratio)
            node_colors.append((red, 0, blue))
    
    # 获取边的权重和透明度
    edge_colors = []
    max_strength = 1
    
    # 找出最大强度值
    for (u, v) in H.edges():
        strength = H[u][v].get('strength', 1)
        max_strength = max(max_strength, strength)
    
    # 创建边权重字典用于布局
    edge_weights = {}
    
    # 计算每条边的透明度和权重
    for (u, v) in H.edges():
        strength = H[u][v].get('strength', 1)
        # 将强度映射到透明度范围 [0.05, 0.8]
        alpha = 0.02 + 0.55 * (strength / max_strength)
        # 使用统一的蓝色，但透明度不同
        edge_colors.append((0, 0, 1, alpha))
        # 设置边的权重（强度越大，权重越大，节点间距离越小）
        edge_weights[(u, v)] = strength
    
    # 绘制图形
    plt.figure(figsize=(20, 16))  # 增加图形尺寸
    # 调整弹簧布局参数，使用边权重影响布局
    pos = nx.spring_layout(H, 
                          k=2.0,        # 增加节点间斥力
                          iterations=100,  # 增加迭代次数
                          scale=2.0,    # 增加布局尺寸
                          weight='strength')  # 使用边的strength属性作为权重
    
    nx.draw(H, pos, 
           with_labels=True, 
           node_color=node_colors,
           node_size=node_sizes,
           font_size=8,  # 稍微减小字体大小
           font_family='SimHei',
           font_weight='bold',
           edge_color=edge_colors,
           width=1.5)  # 统一的边宽度
    
    title = '记忆图谱可视化 - 节点大小表示记忆数量\n节点颜色：蓝(弱连接)到红(强连接)渐变，边的透明度表示连接强度\n连接强度越大的节点距离越近'
    plt.title(title, fontsize=16, fontfamily='SimHei')
    plt.show()

async def main():
    # 初始化数据库
    logger.info("正在初始化数据库连接...")
    db = Database.get_instance()
    start_time = time.time()
    
    test_pare = {'do_build_memory':False,'do_forget_topic':True,'do_visualize_graph':True,'do_query':False,'do_merge_memory':True}
    
    # 创建记忆图
    memory_graph = Memory_graph()
    
    # 创建海马体
    hippocampus = Hippocampus(memory_graph)
    
    # 从数据库同步数据
    hippocampus.sync_memory_from_db()
    
    end_time = time.time()
    logger.info(f"\033[32m[加载海马体耗时: {end_time - start_time:.2f} 秒]\033[0m")
    
    # 构建记忆
    if test_pare['do_build_memory']:
        logger.info("开始构建记忆...")
        chat_size = 25
        await hippocampus.operation_build_memory(chat_size=chat_size)
        
        end_time = time.time()
        logger.info(f"\033[32m[构建记忆耗时: {end_time - start_time:.2f} 秒,chat_size={chat_size},chat_count = {chat_size}]\033[0m")
        
    if test_pare['do_forget_topic']:
        logger.info("开始遗忘记忆...")
        await hippocampus.operation_forget_topic(percentage=0.1)
        
        end_time = time.time()
        logger.info(f"\033[32m[遗忘记忆耗时: {end_time - start_time:.2f} 秒]\033[0m")
        
    if test_pare['do_merge_memory']:
        logger.info("开始合并记忆...")
        await hippocampus.operation_merge_memory(percentage=0.1)
        
        end_time = time.time()
        logger.info(f"\033[32m[合并记忆耗时: {end_time - start_time:.2f} 秒]\033[0m")
    
    if test_pare['do_visualize_graph']:
        # 展示优化后的图形
        logger.info("生成记忆图谱可视化...")
        print("\n生成优化后的记忆图谱：")
        visualize_graph_lite(memory_graph)
    
    if test_pare['do_query']:
        # 交互式查询
        while True:
            query = input("\n请输入新的查询概念（输入'退出'以结束）：")
            if query.lower() == '退出':
                break
            
            items_list = memory_graph.get_related_item(query)
            if items_list:
                first_layer, second_layer = items_list
                if first_layer:
                    print("\n直接相关的记忆：")
                    for item in first_layer:
                        print(f"- {item}")
                if second_layer:
                    print("\n间接相关的记忆：")
                    for item in second_layer:
                        print(f"- {item}")
            else:
                print("未找到相关记忆。")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

    
