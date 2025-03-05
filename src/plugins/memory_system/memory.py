# -*- coding: utf-8 -*-
import os
import jieba
import networkx as nx
import matplotlib.pyplot as plt
from collections import Counter
import datetime
import random
import time
from ..chat.config import global_config
from ...common.database import Database # 使用正确的导入语法
from ..chat.utils import calculate_information_content, get_cloest_chat_from_db
from ..models.utils_model import LLM_request
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

    def forget_topic(self, topic):
        """随机删除指定话题中的一条记忆，如果话题没有记忆则移除该话题节点"""
        if topic not in self.G:
            return None
            
        # 获取话题节点数据
        node_data = self.G.nodes[topic]
        
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
                    self.G.nodes[topic]['memory_items'] = memory_items
                else:
                    # 如果没有记忆项了，删除整个节点
                    self.G.remove_node(topic)
                    
                return removed_item
        
        return None


# 海马体 
class Hippocampus:
    def __init__(self,memory_graph:Memory_graph):
        self.memory_graph = memory_graph
        self.llm_model = LLM_request(model = global_config.llm_normal,temperature=0.5)
        self.llm_model_small = LLM_request(model = global_config.llm_normal_minor,temperature=0.5)
        
    def calculate_node_hash(self, concept, memory_items):
        """计算节点的特征值"""
        if not isinstance(memory_items, list):
            memory_items = [memory_items] if memory_items else []
        sorted_items = sorted(memory_items)
        content = f"{concept}:{'|'.join(sorted_items)}"
        return hash(content)

    def calculate_edge_hash(self, source, target):
        """计算边的特征值"""
        nodes = sorted([source, target])
        return hash(f"{nodes[0]}:{nodes[1]}")
        
    def get_memory_sample(self,chat_size=20,time_frequency:dict={'near':2,'mid':4,'far':3}):
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
    
    async def memory_compress(self, input_text, rate=1):
        information_content = calculate_information_content(input_text)
        print(f"文本的信息量（熵）: {information_content:.4f} bits")
        topic_num = max(1, min(5, int(information_content * rate / 4)))
        topic_prompt = find_topic(input_text, topic_num)
        topic_response = await self.llm_model.generate_response(topic_prompt)
        # 检查 topic_response 是否为元组
        if isinstance(topic_response, tuple):
            topics = topic_response[0].split(",")  # 假设第一个元素是我们需要的字符串
        else:
            topics = topic_response.split(",")
        compressed_memory = set()
        for topic in topics:
            topic_what_prompt = topic_what(input_text,topic)
            topic_what_response = await self.llm_model_small.generate_response(topic_what_prompt)
            compressed_memory.add((topic.strip(), topic_what_response[0]))  # 将话题和记忆作为元组存储
        return compressed_memory

    async def operation_build_memory(self,chat_size=12):
        #最近消息获取频率
        time_frequency = {'near':1,'mid':2,'far':2}
        memory_sample = self.get_memory_sample(chat_size,time_frequency)
        # print(f"\033[1;32m[记忆构建]\033[0m 获取记忆样本: {memory_sample}")   
        for i, input_text in enumerate(memory_sample, 1):
            #加载进度可视化
            progress = (i / len(memory_sample)) * 100
            bar_length = 30
            filled_length = int(bar_length * i // len(memory_sample))
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            # print(f"\n进度: [{bar}] {progress:.1f}% ({i}/{len(memory_sample)})")
            if input_text:
                # 生成压缩后记忆
                first_memory = set()
                first_memory = await self.memory_compress(input_text, 2.5)
                #将记忆加入到图谱中
                for topic, memory in first_memory:
                    topics = segment_text(topic)
                    # print(f"\033[1;34m话题\033[0m: {topic},节点: {topics}, 记忆: {memory}")
                    for split_topic in topics:
                        self.memory_graph.add_dot(split_topic,memory)
                    for split_topic in topics:
                        for other_split_topic in topics:
                            if split_topic != other_split_topic:
                                self.memory_graph.connect_dot(split_topic, other_split_topic)
            else:
                print(f"空消息 跳过")
        self.sync_memory_to_db()

    def sync_memory_to_db(self):
        """检查并同步内存中的图结构与数据库"""
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
                'strength': edge.get('strength', 1)
            }
            
        # 检查并更新边
        for source, target in memory_edges:
            edge_hash = self.calculate_edge_hash(source, target)
            edge_key = (source, target)
            strength = self.memory_graph.G[source][target].get('strength', 1)
            
            if edge_key not in db_edge_dict:
                # 添加新边
                edge_data = {
                    'source': source,
                    'target': target,
                    'strength': strength,
                    'hash': edge_hash
                }
                self.memory_graph.db.db.graph_data.edges.insert_one(edge_data)
            else:
                # 检查边的特征值是否变化
                if db_edge_dict[edge_key]['hash'] != edge_hash:
                    self.memory_graph.db.db.graph_data.edges.update_one(
                        {'source': source, 'target': target},
                        {'$set': {
                            'hash': edge_hash,
                            'strength': strength
                        }}
                    )
                    
        # 删除多余的边
        memory_edge_set = set(memory_edges)
        for edge_key in db_edge_dict:
            if edge_key not in memory_edge_set:
                source, target = edge_key
                self.memory_graph.db.db.graph_data.edges.delete_one({
                    'source': source,
                    'target': target
                })

    def sync_memory_from_db(self):
        """从数据库同步数据到内存中的图结构"""
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
        
    async def operation_forget_topic(self, percentage=0.1):
        """随机选择图中一定比例的节点进行检查，根据条件决定是否遗忘"""
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
                removed_item = self.memory_graph.forget_topic(node)
                if removed_item:
                    forgotten_nodes.append((node, removed_item))
                    print(f"遗忘节点 {node} 的记忆: {removed_item}")
        
        # 同步到数据库
        if forgotten_nodes:
            self.sync_memory_to_db()
            print(f"完成遗忘操作，共遗忘 {len(forgotten_nodes)} 个节点的记忆")
        else:
            print("本次检查没有节点满足遗忘条件")

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
            self.sync_memory_to_db()
            print(f"\n完成记忆合并操作，共处理 {len(merged_nodes)} 个节点")
        else:
            print("\n本次检查没有需要合并的节点")


def segment_text(text):
    seg_text = list(jieba.cut(text))
    return seg_text    

def find_topic(text, topic_num):
    prompt = f'这是一段文字：{text}。请你从这段话中总结出{topic_num}个话题，帮我列出来，用逗号隔开，尽可能精简。只需要列举{topic_num}个话题就好，不要告诉我其他内容。'
    return prompt

def topic_what(text, topic):
    prompt = f'这是一段文字：{text}。我想知道这记忆里有什么关于{topic}的话题，帮我总结成一句自然的话，可以包含时间和人物。只输出这句话就好'
    return prompt


from nonebot import get_driver
driver = get_driver()
config = driver.config

start_time = time.time()

Database.initialize(
    host= config.MONGODB_HOST,
    port= config.MONGODB_PORT,
    db_name=  config.DATABASE_NAME,
    username= config.MONGODB_USERNAME,
    password= config.MONGODB_PASSWORD,
    auth_source=config.MONGODB_AUTH_SOURCE
)
#创建记忆图
memory_graph = Memory_graph()
#创建海马体
hippocampus = Hippocampus(memory_graph)
#从数据库加载记忆图
hippocampus.sync_memory_from_db()

end_time = time.time()
print(f"\033[32m[加载海马体耗时: {end_time - start_time:.2f} 秒]\033[0m")