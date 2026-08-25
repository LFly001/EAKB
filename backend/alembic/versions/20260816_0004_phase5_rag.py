"""phase5 RAG 对话会话表 + 消息表

Revision ID: 20260816_0004
Revises: 20260815_0003
Create Date: 2026-08-16

Phase 5 建表 (DESIGN.md 4.1.7 / 4.1.8):
- rag_conversation  RAG 对话会话表 (status ENUM('active','ended'), 无删除态)
- rag_message      RAG 对话消息表 (role/feedback ENUM, retrieved_chunks/sources/token_usage JSON)
消息表 FK ON DELETE CASCADE: 删除会话时消息随数据库级联清理 (物理删除)
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260816_0004"
down_revision = "20260815_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================
    # rag_conversation — RAG 对话会话表 (DESIGN.md 4.1.7)
    # ==========================================
    op.create_table(
        "rag_conversation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="所属用户ID"),
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
            server_default=sa.text("'新对话'"),
            comment="对话标题",
        ),
        sa.Column(
            "template_id", sa.BigInteger(), nullable=True, comment="使用的提示词模板ID"
        ),
        sa.Column(
            "category_ids",
            sa.String(500),
            nullable=True,
            comment="限定知识库分类范围（逗号分隔ID）",
        ),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("'0'"),
            comment="消息轮数",
        ),
        sa.Column(
            "status",
            mysql.ENUM("active", "ended"),
            nullable=False,
            server_default=sa.text("'active'"),
            comment="状态: active=进行中 ended=已结束",
        ),
        sa.Column("ended_at", sa.DateTime(), nullable=True, comment="结束时间"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["pt_template.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_ragconv_user", "rag_conversation", ["user_id"])
    op.create_index("idx_ragconv_status", "rag_conversation", ["status"])

    # ==========================================
    # rag_message — RAG 对话消息表 (DESIGN.md 4.1.8)
    # ==========================================
    op.create_table(
        "rag_message",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "conversation_id", sa.BigInteger(), nullable=False, comment="所属对话ID"
        ),
        sa.Column(
            "role",
            mysql.ENUM("user", "assistant", "system"),
            nullable=False,
            comment="消息角色: user/assistant/system",
        ),
        sa.Column(
            "question", sa.Text(), nullable=True, comment="用户问题（user消息时）"
        ),
        sa.Column(
            "answer", sa.Text(), nullable=True, comment="助手回答（assistant消息时）"
        ),
        sa.Column(
            "prompt_full",
            sa.Text(),
            nullable=True,
            comment="实际发送的完整 Prompt（含模板/历史/上下文）",
        ),
        sa.Column(
            "retrieved_chunks", mysql.JSON(), nullable=True, comment="检索到的分块信息"
        ),
        sa.Column("sources", mysql.JSON(), nullable=True, comment="来源文档信息"),
        sa.Column("model_name", sa.String(100), nullable=True, comment="使用的模型名"),
        sa.Column(
            "token_usage",
            mysql.JSON(),
            nullable=True,
            comment="Token 用量 {prompt_tokens, completion_tokens, total_tokens}",
        ),
        sa.Column(
            "response_time_ms", sa.Integer(), nullable=True, comment="响应耗时(毫秒)"
        ),
        sa.Column(
            "feedback",
            mysql.ENUM("positive", "negative"),
            nullable=True,
            comment="用户反馈: positive=点赞 negative=点踩",
        ),
        sa.Column("feedback_comment", sa.Text(), nullable=True, comment="反馈备注"),
        sa.Column(
            "error_message", sa.Text(), nullable=True, comment="生成失败错误信息"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["rag_conversation.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("idx_ragmsg_conversation", "rag_message", ["conversation_id"])
    op.create_index("idx_ragmsg_created", "rag_message", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_ragmsg_created", table_name="rag_message")
    op.drop_index("idx_ragmsg_conversation", table_name="rag_message")
    op.drop_table("rag_message")
    op.drop_index("idx_ragconv_status", table_name="rag_conversation")
    op.drop_index("idx_ragconv_user", table_name="rag_conversation")
    op.drop_table("rag_conversation")
