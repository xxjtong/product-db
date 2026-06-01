"""AI conversation persistence models."""
from app.database import Base
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    messages = relationship("AIMessage", backref="conversation", cascade="all, delete-orphan",
                            order_by="AIMessage.created_at")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else "",
            "message_count": len(self.messages) if self.messages else 0,
        }


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system, tool
    content = Column(Text, nullable=True)
    tool_calls = Column(Text, nullable=True)  # JSON
    tool_call_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content or "",
            "tool_calls": self.tool_calls or "",
            "created_at": self.created_at.strftime("%H:%M") if self.created_at else "",
        }
