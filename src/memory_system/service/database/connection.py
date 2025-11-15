"""
记忆服务的数据库连接管理

提供数据库连接池管理和会话管理功能。
"""

import os
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

# 全局变量
engine: Optional[AsyncSession] = None
async_session_maker: Optional[async_sessionmaker] = None
DatabaseURL = None


async def init_database() -> None:
    """初始化数据库连接"""
    global engine, async_session_maker, DatabaseURL

    try:
        # 获取数据库URL
        DatabaseURL = os.getenv("DATABASE_URL", "postgresql+asyncpg://memory_user:memory_pass@localhost:5432/memory_db")

        logger.info(f"连接数据库: {DatabaseURL.split('@')[1] if '@' in DatabaseURL else DatabaseURL}")

        # 创建异步引擎
        engine = create_async_engine(
            DatabaseURL,
            echo=os.getenv("DEBUG", "false").lower() == "true",
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            pool_pre_ping=True,
            pool_recycle=3600,  # 1小时回收连接
        )

        # 创建会话工厂
        async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # 创建所有表
        await create_tables()

        logger.info("数据库连接初始化成功")

    except Exception as e:
        logger.error(f"数据库连接初始化失败: {e}")
        raise


async def create_tables() -> None:
    """创建数据库表"""
    try:
        async with engine.begin() as conn:
            # 导入所有模型确保表被创建

            # 创建所有表
            await conn.run_sync(Base.metadata.create_all)
            logger.info("数据库表创建成功")

    except Exception as e:
        logger.error(f"创建数据库表失败: {e}")
        raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    if not async_session_maker:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")

    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库会话错误: {e}")
            raise
        finally:
            await session.close()


async def close_database() -> None:
    """关闭数据库连接"""
    global engine, async_session_maker

    try:
        if engine:
            await engine.dispose()
            logger.info("数据库连接已关闭")

        engine = None
        async_session_maker = None

    except Exception as e:
        logger.error(f"关闭数据库连接失败: {e}")


async def check_database_health() -> dict:
    """检查数据库健康状态"""
    try:
        if not engine:
            return {"status": "unhealthy", "error": "数据库未初始化"}

        async with engine.begin() as conn:
            result = await conn.execute("SELECT 1 as health_check")
            row = result.fetchone()

            if row and row[0] == 1:
                # 检查表是否存在
                tables_result = await conn.execute(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name IN ('memories', 'conflicts')"
                )
                table_count = tables_result.fetchone()[0]

                return {
                    "status": "healthy",
                    "tables_found": table_count,
                    "connection_pool_size": engine.pool.size(),
                    "connection_pool_checked_in": engine.pool.checkedin(),
                    "connection_pool_checked_out": engine.pool.checkedout(),
                }
            else:
                return {"status": "unhealthy", "error": "数据库查询失败"}

    except Exception as e:
        logger.error(f"数据库健康检查失败: {e}")
        return {"status": "unhealthy", "error": str(e)}


async def execute_raw_query(query: str, params: dict = None) -> list:
    """执行原始SQL查询"""
    try:
        async with engine.begin() as conn:
            result = await conn.execute(query, params or {})
            return result.fetchall()

    except Exception as e:
        logger.error(f"执行原始查询失败: {e}")
        raise


# 数据库事务管理器
class DatabaseTransaction:
    """数据库事务管理器"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._committed = False
        self._rolled_back = False

    async def commit(self):
        """提交事务"""
        if not self._committed and not self._rolled_back:
            await self.session.commit()
            self._committed = True
            logger.debug("事务已提交")

    async def rollback(self):
        """回滚事务"""
        if not self._committed and not self._rolled_back:
            await self.session.rollback()
            self._rolled_back = True
            logger.debug("事务已回滚")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.rollback()
        else:
            await self.commit()


# 数据库连接池监控
async def get_connection_pool_stats() -> dict:
    """获取连接池统计信息"""
    if not engine:
        return {"error": "数据库未初始化"}

    pool = engine.pool

    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid(),
    }
