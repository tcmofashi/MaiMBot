import os
import httpx
from typing import Dict, Any, List, Optional, Tuple
from src.common.logger import get_logger

logger = get_logger("saas_plugin_utils")

MAIM_CONFIG_URL = os.getenv("MAIM_CONFIG_URL", "http://localhost:8000")

# 简单内存缓存：tenant_id:agent_id -> (timestamp, data)
_CONFIG_CACHE: Dict[str, Tuple[float, List[Dict]]] = {}
_CACHE_TTL = 60  # 1分钟缓存

def _get_cache_key(tenant_id: str, agent_id: str) -> str:
    return f"{tenant_id}:{agent_id or ''}"

def _fetch_settings_from_api(tenant_id: str, agent_id: str) -> List[Dict]:
    """从 MaimConfig API 获取配置"""
    try:
        url = f"{MAIM_CONFIG_URL}/api/v1/plugins/settings"
        params = {"tenant_id": tenant_id}
        if agent_id:
            params["agent_id"] = agent_id
            
        # 使用同步请求，因为当前是在同步上下文中调用 (bot._process_commands)
        # 理想情况下应当全异步，但 saas_utils 原型是同步接口
        # TODO: Refactor utility to async
        with httpx.Client() as client:
            response = client.get(url, params=params, timeout=2.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to fetch plugin settings: {response.status_code} {response.text}")
                return []
    except Exception as e:
        logger.error(f"Error calling MaimConfig API: {e}")
        return []

def get_enabled_plugins(tenant_id: str, agent_id: str) -> List[str]:
    """获取指定租户和Agent的启用插件列表"""
    import time
    
    key = _get_cache_key(tenant_id, agent_id)
    cached = _CONFIG_CACHE.get(key)
    
    if cached and time.time() - cached[0] < _CACHE_TTL:
        settings = cached[1]
    else:
        settings = _fetch_settings_from_api(tenant_id, agent_id)
        _CONFIG_CACHE[key] = (time.time(), settings)
        
    enabled = [s["plugin_name"] for s in settings if s.get("enabled", False)]
    
    # === Fallback Start ===
    # 为了保证原有功能可用，如果没有配置任何插件，我们暂时返回所有已注册插件（开发模式）
    # 在生产环境应去除此逻辑
    if not enabled:
       from src.plugin_system.core.plugin_manager import plugin_manager
       return plugin_manager.list_registered_plugins()
    # === Fallback End ===
    
    return enabled

def get_plugin_config(tenant_id: str, plugin_name: str, agent_id: str = "") -> Dict[str, Any]:
    """获取指定租户的插件配置"""
    # 尝试从缓存获取
    key = _get_cache_key(tenant_id, agent_id)
    cached = _CONFIG_CACHE.get(key)
    
    settings = []
    import time
    if cached and time.time() - cached[0] < _CACHE_TTL:
        settings = cached[1]
    else:
        # 如果没有缓存，或者缓存过期，重新获取
        # 注意：这里可能会导致重复请求 api，如果 get_enabled_plugins 刚调过。
        # 优化：get_enabled_plugins 和 get_plugin_config 共享缓存更新逻辑
        settings = _fetch_settings_from_api(tenant_id, agent_id)
        _CONFIG_CACHE[key] = (time.time(), settings)

    for s in settings:
        if s["plugin_name"] == plugin_name:
            return s.get("config", {})
            
    return {}

def is_plugin_enabled(tenant_id: str, agent_id: str, plugin_name: str) -> bool:
    """检查插件是否对特定租户/Agent启用"""
    enabled_list = get_enabled_plugins(tenant_id, agent_id)
    return plugin_name in enabled_list
