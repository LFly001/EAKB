"""
EAKB 全局配置 — Pydantic Settings
读取 .env 环境变量，提供类型安全的配置访问
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局配置，自动从 .env 文件读取"""

    # ==========================================
    # 应用基础
    # ==========================================
    APP_NAME: str = Field(default="EAKB", description="应用名称")
    APP_ENV: str = Field(
        default="development", description="运行环境: development / production"
    )
    DEBUG: bool = Field(default=True, description="调试模式")
    BACKEND_HOST: str = Field(default="0.0.0.0", description="后端监听地址")
    BACKEND_PORT: int = Field(default=8000, description="后端监听端口")
    LOG_LEVEL: str = Field(default="INFO", description="日志级别")
    FRONTEND_URL: str = Field(
        default="http://localhost:5173", description="前端地址(CORS白名单)"
    )
    API_V1_PREFIX: str = Field(default="/api/v1", description="API v1 前缀")

    # ==========================================
    # MySQL 数据库
    # ==========================================
    MYSQL_HOST: str = Field(default="127.0.0.1", description="MySQL 主机地址")
    MYSQL_PORT: int = Field(default=3306, description="MySQL 端口")
    MYSQL_USER: str = Field(default="eakb", description="MySQL 用户名")
    MYSQL_PASSWORD: str = Field(default="eakb123456", description="MySQL 密码")
    MYSQL_DATABASE: str = Field(default="eakb", description="MySQL 数据库名")
    DB_POOL_SIZE: int = Field(default=20, description="连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=40, description="连接池最大溢出")
    DB_POOL_RECYCLE: int = Field(default=3600, description="连接回收时间(秒)")
    DB_ECHO: bool = Field(default=False, description="SQL 回显(调试用)")

    @property
    def DATABASE_URL(self) -> str:
        """生成 SQLAlchemy 同步连接 URL (PyMySQL)"""
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    @property
    def DATABASE_URL_ASYNC(self) -> str:
        """生成 SQLAlchemy 异步连接 URL (aiomysql)"""
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    # ==========================================
    # ChromaDB 向量库
    # ==========================================
    HF_ENDPOINT: str = Field(
        default="",
        description="HuggingFace 镜像地址 (网络受限时设置, 如 https://hf-mirror.com)",
    )
    CHROMA_HOST: str = Field(default="127.0.0.1", description="Chroma 服务地址")
    CHROMA_PORT: int = Field(default=8001, description="Chroma 服务端口")
    CHROMA_PERSIST_DIR: str = Field(
        default="./chroma_data", description="Chroma 持久化目录"
    )
    EMBEDDING_MODEL_NAME: str = Field(
        default="BAAI/bge-large-zh-v1.5", description="Embedding 模型名称"
    )
    EMBEDDING_DEVICE: str = Field(default="cpu", description="Embedding 计算设备")
    EMBEDDING_DIMENSION: int = Field(default=1024, description="Embedding 向量维度")

    # ==========================================
    # Neo4j 图数据库
    # ==========================================
    NEO4J_URI: str = Field(
        default="bolt://127.0.0.1:7687", description="Neo4j Bolt 连接地址"
    )
    NEO4J_USERNAME: str = Field(default="neo4j", description="Neo4j 用户名")
    NEO4J_PASSWORD: str = Field(default="neo4j123456", description="Neo4j 密码")
    NEO4J_DATABASE: str = Field(default="neo4j", description="Neo4j 数据库名")
    NEO4J_MAX_CONNECTION_LIFETIME: int = Field(
        default=3600, description="最大连接存活(秒)"
    )
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = Field(
        default=50, description="连接池最大容量"
    )

    # ==========================================
    # MinIO 对象存储
    # ==========================================
    MINIO_ENDPOINT: str = Field(default="127.0.0.1:9000", description="MinIO API 地址")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", description="MinIO Access Key")
    MINIO_SECRET_KEY: str = Field(
        default="minioadmin123456", description="MinIO Secret Key"
    )
    MINIO_BUCKET: str = Field(default="eakb-documents", description="MinIO 存储桶名")
    MINIO_SECURE: bool = Field(default=False, description="是否使用 HTTPS")
    MINIO_REGION: str = Field(default="us-east-1", description="MinIO 区域")

    # ==========================================
    # LLM 大模型
    # ==========================================
    LLM_MODEL_NAME: str = Field(default="deepseek-v4-pro", description="LLM 模型名")
    LLM_API_BASE: str = Field(
        default="https://api.openai.com/v1", description="LLM API 地址"
    )
    LLM_API_KEY: str = Field(default="sk-your-api-key-here", description="LLM API Key")
    LLM_MAX_TOKENS: int = Field(default=4096, description="LLM 最大输出 Token")
    LLM_TEMPERATURE: float = Field(default=0.1, description="LLM 温度参数")
    LLM_EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-large", description="远端 Embedding 模型名"
    )
    LLM_EMBEDDING_API_BASE: str = Field(
        default="https://api.openai.com/v1", description="Embedding API 地址"
    )
    LLM_EMBEDDING_API_KEY: str = Field(
        default="sk-your-api-key-here", description="Embedding API Key"
    )

    # ==========================================
    # JWT 鉴权
    # ==========================================
    JWT_SECRET_KEY: str = Field(
        default="change-this-to-a-random-secret-string-at-least-32-chars",
        description="JWT 签名密钥",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT 签名算法")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Access Token 过期时间(分钟)"
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7, description="Refresh Token 过期时间(天)"
    )

    # ==========================================
    # 文件上传
    # ==========================================
    UPLOAD_MAX_SIZE_MB: int = Field(default=50, description="上传文件最大尺寸(MB)")
    # 仅允许解析器支持的格式 (utils/file_parser.py): pdf/docx/txt/md/xlsx
    # .doc/.xls 等旧格式需先转换为 docx/xlsx
    UPLOAD_ALLOWED_EXTENSIONS: str = Field(
        default="pdf,docx,txt,md,xlsx", description="允许上传的文件后缀(逗号分隔)"
    )

    @property
    def allowed_extensions_list(self) -> list[str]:
        """返回允许的文件后缀列表"""
        return [
            ext.strip().lower() for ext in self.UPLOAD_ALLOWED_EXTENSIONS.split(",")
        ]

    @property
    def upload_max_size_bytes(self) -> int:
        """返回上传大小限制(字节)"""
        return self.UPLOAD_MAX_SIZE_MB * 1024 * 1024

    # ==========================================
    # RAG 默认参数 (可被 sys_config 表实时覆盖)
    # ==========================================
    DEFAULT_CHUNK_SIZE: int = Field(default=512, description="默认文档分块大小")
    DEFAULT_CHUNK_OVERLAP: int = Field(default=64, description="默认分块重叠大小")
    DEFAULT_TOP_K: int = Field(default=5, description="默认检索返回条数")
    DEFAULT_SIMILARITY_THRESHOLD: float = Field(
        default=0.7, description="默认相似度阈值"
    )
    DEFAULT_MAX_CONTEXT_TOKENS: int = Field(
        default=4096, description="上下文最大 Token"
    )

    # 知识图谱默认参数 (Phase 6, sys_config 表实时覆盖)
    DEFAULT_GRAPH_ENHANCE_ENABLED: bool = Field(
        default=False,
        description="默认是否启用图谱增强RAG (sys_config graph_enhance_enabled 可覆盖)",
    )
    DEFAULT_GRAPH_ENTITY_TOP_K: int = Field(
        default=5, description="图谱增强单实体邻居数量上限"
    )
    DEFAULT_GRAPH_SIMILARITY_THRESHOLD: float = Field(
        default=0.5,
        description="文档 SIMILAR_TO 余弦相似度阈值 (文档质心级, 远低于分块级 0.7; "
        "实测 bge 质心: 主题交叠文档 ~0.55, 无关文档 ~0.42)",
    )

    # ==========================================
    # 接口限流默认参数 (Phase 8, sys_config 表实时覆盖)
    # ==========================================
    RATE_LIMIT_ENABLED: bool = Field(
        default=False,
        description="接口限流开关 (sys_config rate_limit_enabled 可覆盖, 默认关闭)",
    )
    RATE_LIMIT_REQUESTS: int = Field(
        default=60, description="限流窗口内单 IP 最大请求数"
    )
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, description="限流窗口时长(秒)")

    # ==========================================
    # CORS 跨域白名单
    # ==========================================
    @property
    def cors_origins(self) -> list[str]:
        """CORS 允许的来源列表"""
        origins = [self.FRONTEND_URL]
        if self.APP_ENV == "development":
            origins.extend(
                [
                    "http://localhost:5173",
                    "http://localhost:3000",
                    "http://127.0.0.1:5173",
                ]
            )
        return origins

    model_config = {
        # 依次尝试 当前目录 (backend/) 与 项目根目录 的 .env, 先找到的先加载;
        # 从项目根目录启动或 cd backend 启动均能正确读取配置
        "env_file": (".env", "../.env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        # .env 与 docker-compose 共用 (含 MYSQL_ROOT_PASSWORD/NEO4J_HTTP_PORT 等
        # 容器编排键), 未在 Settings 声明的键一律忽略, 不阻断启动
        "extra": "ignore",
    }


# 全局单例配置对象
settings = Settings()
