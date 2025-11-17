"""Add MVP users, threads, messages, and files tables

Revision ID: 20251116_mvp_users_files
Revises: 20251019_memory_schema_rls
Create Date: 2025-11-16

MVP Console Enhancement: Add users table for internal operators,
adapt existing conversations to threads, and add files table for uploads.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers
revision = "20251116_mvp_users_files"
down_revision = "20251019_memory_schema_rls"
branch_labels = None
depends_on = None


def upgrade():
    # Create users table (for internal MVP operators only)
    op.create_table(
        "mvp_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False),
        sa.Index("idx_mvp_users_display_name", "display_name"),
    )

    # Seed initial test users
    op.execute(
        """
        INSERT INTO mvp_users (id, display_name) VALUES
        ('00000000-0000-0000-0000-000000000001', 'Kyle'),
        ('00000000-0000-0000-0000-000000000002', 'Alex'),
        ('00000000-0000-0000-0000-000000000003', 'Jordan')
    """
    )

    # Create threads table (similar to conversations, but for MVP)
    op.create_table(
        "mvp_threads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("mvp_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False),
        sa.Index("idx_mvp_threads_user_id", "user_id"),
        sa.Index("idx_mvp_threads_created_at", "created_at"),
    )

    # Create messages table for MVP threads
    op.create_table(
        "mvp_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("thread_id", UUID(as_uuid=True), sa.ForeignKey("mvp_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("mvp_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),  # 'user', 'assistant', 'system'
        sa.Column("model_name", sa.String(100), nullable=True),  # 'gpt-3.5-turbo', 'claude-3-haiku', etc.
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_usage_json", JSONB, nullable=True),  # {input_tokens: N, output_tokens: M, total: X}
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False),
        sa.Index("idx_mvp_messages_thread_id", "thread_id"),
        sa.Index("idx_mvp_messages_created_at", "created_at"),
    )

    # Create files table for uploads
    op.create_table(
        "mvp_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("mvp_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", UUID(as_uuid=True), sa.ForeignKey("mvp_threads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),  # Path or key for storage backend
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("NOW()"), nullable=False),
        sa.Index("idx_mvp_files_user_id", "user_id"),
        sa.Index("idx_mvp_files_thread_id", "thread_id"),
        sa.Index("idx_mvp_files_created_at", "created_at"),
    )


def downgrade():
    op.drop_table("mvp_files")
    op.drop_table("mvp_messages")
    op.drop_table("mvp_threads")
    op.drop_table("mvp_users")
