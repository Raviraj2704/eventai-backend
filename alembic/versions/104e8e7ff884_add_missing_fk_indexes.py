"""add_missing_fk_indexes

Revision ID: 104e8e7ff884
Revises: e152967eec96
Create Date: 2026-11-21
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '104e8e7ff884'
down_revision = 'e152967eec96'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_sessions_speaker_id', 'sessions', ['speaker_id'], unique=False, if_not_exists=True)
    op.create_index('ix_ratings_learning_path_id', 'ratings', ['learning_path_id'], unique=False, if_not_exists=True)
    op.create_index('ix_chat_connections_sender_id', 'chat_connections', ['sender_id'], unique=False, if_not_exists=True)
    op.create_index('ix_chat_connections_receiver_id', 'chat_connections', ['receiver_id'], unique=False, if_not_exists=True)
    op.create_index('ix_chat_messages_connection_id', 'chat_messages', ['connection_id'], unique=False, if_not_exists=True)
    op.create_index('ix_chat_messages_sender_id', 'chat_messages', ['sender_id'], unique=False, if_not_exists=True)


def downgrade() -> None:
    op.drop_index('ix_chat_messages_sender_id', table_name='chat_messages', if_exists=True)
    op.drop_index('ix_chat_messages_connection_id', table_name='chat_messages', if_exists=True)
    op.drop_index('ix_chat_connections_receiver_id', table_name='chat_connections', if_exists=True)
    op.drop_index('ix_chat_connections_sender_id', table_name='chat_connections', if_exists=True)
    op.drop_index('ix_ratings_learning_path_id', table_name='ratings', if_exists=True)
    op.drop_index('ix_sessions_speaker_id', table_name='sessions', if_exists=True)