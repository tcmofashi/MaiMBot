"""
独立的记忆服务 - FastAPI应用程序入口

提供RESTful API接口，支持T+A+P+C四维隔离的记忆管理系统。
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
import os
from contextlib import asynccontextmanager

from .api import memories, conflicts, admin, health
from .database.connection import init_database, close_database
from .cache.redis_client import init_redis, close_redis
from .utils.isolation import validate_isolation_context


# 配置日志
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用程序生命周期管理"""
    try:
        # 启动时初始化
        logger.info("正在初始化记忆服务...")

        # 初始化数据库连接
        await init_database()
        logger.info("数据库连接初始化完成")

        # 初始化Redis连接
        await init_redis()
        logger.info("Redis连接初始化完成")

        logger.info("记忆服务初始化完成")

        yield

    except Exception as e:
        logger.error(f"记忆服务初始化失败: {e}")
        raise
    finally:
        # 关闭时清理资源
        logger.info("正在关闭记忆服务...")

        await close_database()
        await close_redis()

        logger.info("记忆服务已关闭")


# 创建FastAPI应用实例
app = FastAPI(
    title="记忆服务 API",
    description="支持T+A+P+C四维隔离的记忆管理系统",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(memories.router, prefix="/api/v1/memories", tags=["memories"])

app.include_router(conflicts.router, prefix="/api/v1/conflicts", tags=["conflicts"])

app.include_router(admin.router, prefix="/api/v1", tags=["admin"])

app.include_router(health.router, prefix="/api/v1", tags=["health"])


# 全局异常处理
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP异常处理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail, "type": "HTTP_EXCEPTION"}},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """通用异常处理器"""
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "内部服务器错误",
                "type": "INTERNAL_ERROR",
                "detail": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else None,
            }
        },
    )


# 根路径
@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "记忆服务",
        "version": "1.0.0",
        "description": "支持T+A+P+C四维隔离的记忆管理系统",
        "docs_url": "/docs",
        "health_check": "/api/v1/health",
    }


# 中间件：验证隔离上下文
@app.middleware("http")
async def isolation_validation_middleware(request, call_next):
    """验证API请求中的隔离上下文"""
    # 跳过不需要验证的路径
    skip_paths = ["/", "/docs", "/redoc", "/api/v1/health"]
    if request.url.path in skip_paths:
        return await call_next(request)

    try:
        # 从请求头中获取隔离信息
        tenant_id = request.headers.get("X-Tenant-ID")
        agent_id = request.headers.get("X-Agent-ID")
        platform = request.headers.get("X-Platform")
        scope_id = request.headers.get("X-Scope-ID")

        # 验证必需的隔离字段
        if not tenant_id or not agent_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": 400,
                        "message": "缺少必需的隔离上下文信息：X-Tenant-ID 和 X-Agent-ID",
                        "type": "ISOLATION_ERROR",
                    }
                },
            )

        # 验证隔离上下文
        isolation_context = await validate_isolation_context(
            tenant_id=tenant_id, agent_id=agent_id, platform=platform, scope_id=scope_id
        )

        # 将隔离上下文添加到请求状态
        request.state.isolation_context = isolation_context

        response = await call_next(request)
        return response

    except Exception as e:
        logger.error(f"隔离验证中间件错误: {e}")
        return JSONResponse(
            status_code=401,
            content={"error": {"code": 401, "message": f"隔离验证失败: {str(e)}", "type": "ISOLATION_ERROR"}},
        )


def create_app() -> FastAPI:
    """创建FastAPI应用实例"""
    return app


def main():
    """主函数 - 用于直接运行应用"""
    port = int(os.getenv("PORT", 8001))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"启动记忆服务在 {host}:{port}")

    uvicorn.run(
        "main:app", host=host, port=port, reload=os.getenv("DEBUG", "false").lower() == "true", log_level="info"
    )


if __name__ == "__main__":
    main()
