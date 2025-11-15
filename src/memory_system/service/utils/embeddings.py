"""
记忆服务的向量嵌入工具

提供文本向量化、相似度计算和嵌入管理功能。
"""

import logging
from typing import List, Optional, Dict, Any
import numpy as np

logger = logging.getLogger(__name__)

# 全局嵌入模型
_embedding_model = None
_model_name = None


async def init_embedding_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
    """
    初始化嵌入模型

    Args:
        model_name: 模型名称
    """
    global _embedding_model, _model_name

    try:
        from sentence_transformers import SentenceTransformer

        logger.info(f"加载嵌入模型: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        _model_name = model_name

        # 测试模型
        test_embedding = await encode_text("测试")
        if test_embedding is None or len(test_embedding) == 0:
            raise RuntimeError("嵌入模型测试失败")

        logger.info(f"嵌入模型初始化成功: {model_name}, 嵌入维度: {len(test_embedding)}")

    except Exception as e:
        logger.error(f"初始化嵌入模型失败: {e}")
        raise


def get_embedding_model():
    """获取嵌入模型"""
    if not _embedding_model:
        raise RuntimeError("嵌入模型未初始化，请先调用 init_embedding_model()")
    return _embedding_model


def get_embedding_dimension() -> int:
    """获取嵌入向量维度"""
    if not _embedding_model:
        raise RuntimeError("嵌入模型未初始化")
    return _embedding_model.get_sentence_embedding_dimension()


async def encode_text(text: str, normalize: bool = True, batch_size: int = 32) -> Optional[List[float]]:
    """
    将文本编码为向量嵌入

    Args:
        text: 输入文本
        normalize: 是否归一化向量
        batch_size: 批处理大小

    Returns:
        向量嵌入或None
    """
    try:
        if not _embedding_model:
            raise RuntimeError("嵌入模型未初始化")

        if not text or not text.strip():
            return None

        # 清理文本
        clean_text = text.strip()
        if len(clean_text) > 8192:  # 限制文本长度
            clean_text = clean_text[:8192]
            logger.warning(f"文本过长，截断到8192字符: {text[:50]}...")

        # 编码文本
        embedding = _embedding_model.encode(
            clean_text, convert_to_numpy=True, normalize_embeddings=normalize, batch_size=batch_size
        )

        # 转换为列表
        embedding_list = embedding.tolist()

        # 验证向量
        if not embedding_list or len(embedding_list) == 0:
            logger.error(f"编码失败，返回空向量: {text[:50]}...")
            return None

        # 验证向量维度
        expected_dim = get_embedding_dimension()
        if len(embedding_list) != expected_dim:
            logger.error(f"向量维度不匹配: 期望{expected_dim}, 实际{len(embedding_list)}")
            return None

        return embedding_list

    except Exception as e:
        logger.error(f"文本编码失败: {e}")
        return None


async def encode_texts(texts: List[str], normalize: bool = True, batch_size: int = 32) -> List[Optional[List[float]]]:
    """
    批量编码文本为向量嵌入

    Args:
        texts: 文本列表
        normalize: 是否归一化向量
        batch_size: 批处理大小

    Returns:
        向量嵌入列表
    """
    try:
        if not _embedding_model:
            raise RuntimeError("嵌入模型未初始化")

        if not texts:
            return []

        # 清理和过滤文本
        clean_texts = []
        for text in texts:
            if text and text.strip():
                clean_text = text.strip()
                if len(clean_text) > 8192:
                    clean_text = clean_text[:8192]
                clean_texts.append(clean_text)
            else:
                clean_texts.append("")  # 保留空文本的位置

        # 批量编码
        embeddings = _embedding_model.encode(
            clean_texts, convert_to_numpy=True, normalize_embeddings=normalize, batch_size=batch_size
        )

        # 转换为列表格式并处理无效文本
        results = []
        for _i, (text, embedding) in enumerate(zip(texts, embeddings, strict=False)):
            if not text or not text.strip():
                results.append(None)
            else:
                embedding_list = embedding.tolist()
                if embedding_list and len(embedding_list) > 0:
                    results.append(embedding_list)
                else:
                    results.append(None)

        return results

    except Exception as e:
        logger.error(f"批量文本编码失败: {e}")
        return [None] * len(texts)


async def compute_cosine_similarity(embedding1: List[float], embedding2: List[float]) -> Optional[float]:
    """
    计算两个向量的余弦相似度

    Args:
        embedding1: 第一个向量
        embedding2: 第二个向量

    Returns:
        相似度分数或None
    """
    try:
        if not embedding1 or not embedding2:
            return None

        if len(embedding1) != len(embedding2):
            logger.error(f"向量维度不匹配: {len(embedding1)} vs {len(embedding2)}")
            return None

        # 转换为numpy数组
        vec1 = np.array(embedding1, dtype=np.float32)
        vec2 = np.array(embedding2, dtype=np.float32)

        # 计算余弦相似度
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # 确保结果在合理范围内
        similarity = max(-1.0, min(1.0, float(similarity)))

        return similarity

    except Exception as e:
        logger.error(f"计算余弦相似度失败: {e}")
        return None


async def compute_euclidean_distance(embedding1: List[float], embedding2: List[float]) -> Optional[float]:
    """
    计算两个向量的欧几里得距离

    Args:
        embedding1: 第一个向量
        embedding2: 第二个向量

    Returns:
        距离或None
    """
    try:
        if not embedding1 or not embedding2:
            return None

        if len(embedding1) != len(embedding2):
            logger.error(f"向量维度不匹配: {len(embedding1)} vs {len(embedding2)}")
            return None

        # 转换为numpy数组
        vec1 = np.array(embedding1, dtype=np.float32)
        vec2 = np.array(embedding2, dtype=np.float32)

        # 计算欧几里得距离
        distance = np.linalg.norm(vec1 - vec2)

        return float(distance)

    except Exception as e:
        logger.error(f"计算欧几里得距离失败: {e}")
        return None


async def find_similar_embeddings(
    query_embedding: List[float],
    candidate_embeddings: List[List[float]],
    top_k: int = 10,
    similarity_threshold: float = 0.7,
    distance_metric: str = "cosine",
) -> List[Dict[str, Any]]:
    """
    在候选嵌入中找到与查询嵌入最相似的项

    Args:
        query_embedding: 查询向量
        candidate_embeddings: 候选向量列表
        top_k: 返回的最相似项数量
        similarity_threshold: 相似度阈值
        distance_metric: 距离度量方法 ("cosine" 或 "euclidean")

    Returns:
        相似度结果列表
    """
    try:
        if not query_embedding or not candidate_embeddings:
            return []

        results = []

        for i, candidate_embedding in enumerate(candidate_embeddings):
            if not candidate_embedding:
                continue

            # 计算相似度/距离
            if distance_metric == "cosine":
                similarity = await compute_cosine_similarity(query_embedding, candidate_embedding)
                if similarity is None:
                    continue
                score = similarity
            elif distance_metric == "euclidean":
                distance = await compute_euclidean_distance(query_embedding, candidate_embedding)
                if distance is None:
                    continue
                # 将距离转换为相似度分数（距离越小，相似度越高）
                score = 1.0 / (1.0 + distance)
            else:
                logger.error(f"不支持的距离度量方法: {distance_metric}")
                continue

            # 过滤低于阈值的项
            if score < similarity_threshold:
                continue

            results.append(
                {
                    "index": i,
                    "score": score,
                    "similarity": score if distance_metric == "cosine" else None,
                    "distance": distance if distance_metric == "euclidean" else None,
                }
            )

        # 按分数排序并返回top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    except Exception as e:
        logger.error(f"查找相似嵌入失败: {e}")
        return []


async def cluster_embeddings(
    embeddings: List[List[float]], n_clusters: int = 5, method: str = "kmeans"
) -> Optional[Dict[str, Any]]:
    """
    对嵌入向量进行聚类

    Args:
        embeddings: 嵌入向量列表
        n_clusters: 聚类数量
        method: 聚类方法 ("kmeans", "dbscan")

    Returns:
        聚类结果或None
    """
    try:
        if not embeddings or len(embeddings) < n_clusters:
            return None

        from sklearn.cluster import KMeans, DBSCAN
        from sklearn.metrics import silhouette_score

        # 转换为numpy数组
        embeddings_array = np.array(embeddings, dtype=np.float32)

        if method == "kmeans":
            # K-means聚类
            clusterer = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = clusterer.fit_predict(embeddings_array)

            # 计算轮廓分数
            if len(set(cluster_labels)) > 1:
                silhouette_avg = silhouette_score(embeddings_array, cluster_labels)
            else:
                silhouette_avg = 0.0

            return {
                "method": "kmeans",
                "n_clusters": n_clusters,
                "labels": cluster_labels.tolist(),
                "centroids": clusterer.cluster_centers_.tolist(),
                "silhouette_score": silhouette_avg,
                "inertia": clusterer.inertia_,
            }

        elif method == "dbscan":
            # DBSCAN聚类
            clusterer = DBSCAN(eps=0.5, min_samples=5)
            cluster_labels = clusterer.fit_predict(embeddings_array)

            # 计算轮廓分数
            unique_labels = set(cluster_labels)
            if len(unique_labels) > 1 and -1 not in unique_labels:  # 忽略噪声点
                mask = cluster_labels != -1
                if sum(mask) > 1:
                    silhouette_avg = silhouette_score(embeddings_array[mask], cluster_labels[mask])
                else:
                    silhouette_avg = 0.0
            else:
                silhouette_avg = 0.0

            return {
                "method": "dbscan",
                "labels": cluster_labels.tolist(),
                "n_clusters": len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0),
                "n_noise": list(cluster_labels).count(-1),
                "silhouette_score": silhouette_avg,
            }

        else:
            logger.error(f"不支持的聚类方法: {method}")
            return None

    except ImportError:
        logger.warning("scikit-learn未安装，无法执行聚类")
        return None
    except Exception as e:
        logger.error(f"嵌入聚类失败: {e}")
        return None


async def reduce_dimensionality(
    embeddings: List[List[float]], n_components: int = 2, method: str = "pca"
) -> Optional[Dict[str, Any]]:
    """
    降低嵌入向量维度

    Args:
        embeddings: 嵌入向量列表
        n_components: 目标维度
        method: 降维方法 ("pca", "tsne")

    Returns:
        降维结果或None
    """
    try:
        if not embeddings:
            return None

        from sklearn.decomposition import PCA
        from sklearn.manifold import TSNE

        # 转换为numpy数组
        embeddings_array = np.array(embeddings, dtype=np.float32)

        if method == "pca":
            # PCA降维
            reducer = PCA(n_components=n_components, random_state=42)
            reduced_embeddings = reducer.fit_transform(embeddings_array)

            return {
                "method": "pca",
                "n_components": n_components,
                "embeddings": reduced_embeddings.tolist(),
                "explained_variance_ratio": reducer.explained_variance_ratio_.tolist(),
                "explained_variance": reducer.explained_variance_.tolist(),
            }

        elif method == "tsne":
            # t-SNE降维
            reducer = TSNE(
                n_components=n_components, random_state=42, perplexity=min(30, len(embeddings) - 1), n_iter=1000
            )
            reduced_embeddings = reducer.fit_transform(embeddings_array)

            return {
                "method": "tsne",
                "n_components": n_components,
                "embeddings": reduced_embeddings.tolist(),
                "kl_divergence": reducer.kl_divergence_,
            }

        else:
            logger.error(f"不支持的降维方法: {method}")
            return None

    except ImportError:
        logger.warning("scikit-learn未安装，无法执行降维")
        return None
    except Exception as e:
        logger.error(f"嵌入降维失败: {e}")
        return None


async def validate_embedding(embedding: List[float]) -> Dict[str, Any]:
    """
    验证嵌入向量的有效性

    Args:
        embedding: 嵌入向量

    Returns:
        验证结果
    """
    try:
        if not embedding:
            return {"valid": False, "error": "嵌入向量为空"}

        # 检查维度
        if len(embedding) != get_embedding_dimension():
            return {
                "valid": False,
                "error": f"嵌入向量维度不匹配: 期望{get_embedding_dimension()}, 实际{len(embedding)}",
            }

        # 检查数值类型
        if not all(isinstance(x, (int, float)) for x in embedding):
            return {"valid": False, "error": "嵌入向量包含非数值类型"}

        # 检查数值范围
        array = np.array(embedding, dtype=np.float32)

        # 检查NaN和无穷大
        if np.any(np.isnan(array)) or np.any(np.isinf(array)):
            return {"valid": False, "error": "嵌入向量包含NaN或无穷大值"}

        # 检查向量范数
        norm = np.linalg.norm(array)
        if norm == 0:
            return {"valid": False, "error": "嵌入向量范数为零"}

        return {
            "valid": True,
            "dimension": len(embedding),
            "norm": float(norm),
            "mean": float(np.mean(array)),
            "std": float(np.std(array)),
            "min": float(np.min(array)),
            "max": float(np.max(array)),
        }

    except Exception as e:
        return {"valid": False, "error": f"验证嵌入向量时出错: {str(e)}"}


async def normalize_embedding(embedding: List[float]) -> Optional[List[float]]:
    """
    归一化嵌入向量

    Args:
        embedding: 嵌入向量

    Returns:
        归一化后的向量或None
    """
    try:
        if not embedding:
            return None

        array = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(array)

        if norm == 0:
            return None

        normalized = array / norm
        return normalized.tolist()

    except Exception as e:
        logger.error(f"归一化嵌入向量失败: {e}")
        return None


# 便捷函数
async def text_similarity(text1: str, text2: str, normalize: bool = True) -> Optional[float]:
    """
    计算两个文本的相似度

    Args:
        text1: 第一个文本
        text2: 第二个文本
        normalize: 是否归一化向量

    Returns:
        相似度分数或None
    """
    try:
        # 编码文本
        embedding1 = await encode_text(text1, normalize=normalize)
        embedding2 = await encode_text(text2, normalize=normalize)

        if not embedding1 or not embedding2:
            return None

        # 计算相似度
        return await compute_cosine_similarity(embedding1, embedding2)

    except Exception as e:
        logger.error(f"计算文本相似度失败: {e}")
        return None
