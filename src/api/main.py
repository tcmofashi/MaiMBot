"""
MaiMBot API主路由文件
整合API接口，包括租户管理、Agent管理、API密钥管理和聊天功能
用户认证由专门的服务提供，本服务专注于配置管理
"""

import time
from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.auth_api_v2 import router as api_key_auth_router
from src.api.routes.tenant_api_v2 import router as tenant_router
from src.api.routes.agent_api_v2 import router as agent_router
from src.api.routes.api_key_api_v2 import router as api_key_router
from src.api.routes.chat_api_v2 import router as chat_router
from src.api.init_agent_templates import init_template_data
from src.common.logger import get_logger

logger = get_logger(__name__)

# 创建主路由器
api_router = APIRouter()

# 注册所有子路由 (统一使用v2版本)
api_router.include_router(api_key_auth_router, prefix="/v2", tags=["API密钥认证"])
api_router.include_router(tenant_router, prefix="/v2", tags=["租户管理"])
api_router.include_router(agent_router, prefix="/v2", tags=["Agent管理"])
api_router.include_router(api_key_router, prefix="/v2", tags=["API密钥管理"])
api_router.include_router(chat_router, prefix="/v2", tags=["聊天"])


@api_router.get("/")
async def api_root():
    """
    API根路径
    """
    return {
        "message": "MaiMBot API Server",
        "version": "2.0.0",
        "description": "多租户AI聊天机器人API服务",
        "endpoints": {
            "api_key_auth": "/api/v2/auth",
            "tenant": "/api/v2/tenants",
            "agents": "/api/v2/agents",
            "api_keys": "/api/v2/api-keys",
            "chat": "/api/v2/chat",
            "docs": "/docs",
            "redoc": "/redoc",
        },
        "features": ["多租户隔离", "Agent模板管理", "API密钥认证", "请求体参数认证", "批量消息处理", "无验证租户创建"],
    }


@api_router.get("/health")
async def health_check():
    """
    健康检查接口
    """
    try:
        # 这里可以添加更多的健康检查逻辑
        # 比如数据库连接检查、依赖服务检查等

        return {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "2.0.0",
            "services": {"database": "healthy", "auth": "healthy", "chat": "healthy"},
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务不健康") from None


@api_router.get("/info")
async def api_info():
    """
    API信息接口
    """
    return {
        "name": "MaiMBot API",
        "description": "多租户AI聊天机器人API服务",
        "version": "2.0.0",
        "architecture": {
            "isolation_levels": ["tenant", "agent", "chat", "platform"],
            "auth_methods": ["api_key", "request_body"],
            "data_flow": "request_body_parameters",
            "user_auth": "external_service",
        },
        "api_versions": {
            "v1": {"description": "传统API，支持URL参数", "base_path": "/api/v1", "auth": "可选"},
            "v2": {"description": "新版API，支持请求体参数", "base_path": "/api/v2", "auth": "推荐"},
        },
        "supported_features": [
            "租户管理",
            "Agent模板配置",
            "多租户隔离聊天",
            "批量消息处理",
            "API密钥认证",
            "无验证租户创建",
            "权限管理",
        ],
    }


def create_api_app() -> FastAPI:
    """
    创建FastAPI应用实例
    """
    app = FastAPI(
        title="MaiMBot API",
        description="多租户AI聊天机器人API服务",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 添加CORS中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境中应该限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 包含API路由
    app.include_router(api_router, prefix="/api")

    # 应用级健康检查端点 (不使用 /api 前缀)
    @app.get("/health")
    async def app_health_check():
        """应用级健康检查端点"""
        return {"status": "healthy", "timestamp": time.time(), "service": "MaiMBot API Server", "version": "2.0.0"}

    # 启动事件
    @app.on_event("startup")
    async def startup_event():
        """
        应用启动时执行的操作
        """
        logger.info("MaiMBot API Server 正在启动...")

        try:
            # 初始化Agent模板数据
            init_template_data()
            logger.info("Agent模板数据初始化完成")
        except Exception as e:
            logger.error(f"Agent模板数据初始化失败: {e}")

        logger.info("MaiMBot API Server 启动完成")

    # 关闭事件
    @app.on_event("shutdown")
    async def shutdown_event():
        """
        应用关闭时执行的操作
        """
        logger.info("MaiMBot API Server 正在关闭...")

    return app


# 创建应用实例
app = create_api_app()

if __name__ == "__main__":
    import uvicorn
    import os

    # 从环境变量获取端口，默认8000
    port = int(os.getenv("PORT", "8000"))

    # 开发环境配置
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")
