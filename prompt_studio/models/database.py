"""
Database models for Prompt Studio
"""
from datetime import datetime
from typing import Optional, List
import uuid
import json

from sqlmodel import SQLModel, Field, Relationship, Session, create_engine, select
from sqlalchemy import Text, JSON, Column


class PromptTagLink(SQLModel, table=True):
    """Many-to-many relationship between prompts and tags"""
    __tablename__ = "prompt_tag"
    
    prompt_id: str = Field(foreign_key="prompt.id", primary_key=True)
    tag_id: int = Field(foreign_key="tag.id", primary_key=True)


class Tag(SQLModel, table=True):
    """Tag model for categorizing prompts"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    
    # Relationships
    prompts: List["Prompt"] = Relationship(
        back_populates="tags", 
        link_model=PromptTagLink
    )


class Prompt(SQLModel, table=True):
    """Main prompt model"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(unique=True, index=True)
    content: str
    description: Optional[str] = Field(default=None)
    category: Optional[str] = Field(default=None, index=True)
    placeholders_schema: Optional[str] = Field(default=None)  # JSON string
    is_favorite: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    tags: List[Tag] = Relationship(
        back_populates="prompts", 
        link_model=PromptTagLink
    )
    history_entries: List["History"] = Relationship(back_populates="prompt")
    
    def get_placeholders_schema(self) -> List[dict]:
        """Get placeholders schema as Python list"""
        if self.placeholders_schema:
            try:
                return json.loads(self.placeholders_schema)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_placeholders_schema(self, schema: List[dict]):
        """Set placeholders schema from Python list"""
        self.placeholders_schema = json.dumps(schema) if schema else None


class History(SQLModel, table=True):
    """History of prompt executions"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    prompt_id: Optional[str] = Field(default=None, foreign_key="prompt.id", index=True)
    backend: str = Field(index=True)  # openai|ollama|lmstudio|custom
    request_payload: str  # JSON string
    response_text: str
    duration_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    
    # Relationships
    prompt: Optional[Prompt] = Relationship(back_populates="history_entries")
    
    def get_request_payload(self) -> dict:
        """Get request payload as Python dict"""
        try:
            return json.loads(self.request_payload)
        except json.JSONDecodeError:
            return {}
    
    def set_request_payload(self, payload: dict):
        """Set request payload from Python dict"""
        self.request_payload = json.dumps(payload)


class Workflow(SQLModel, table=True):
    """Workflow model for storing prompt workflows"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True)
    graph_json: str  # JSON string
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def get_graph(self) -> dict:
        """Get graph as Python dict"""
        try:
            return json.loads(self.graph_json)
        except json.JSONDecodeError:
            return {}
    
    def set_graph(self, graph: dict):
        """Set graph from Python dict"""
        self.graph_json = json.dumps(graph)


class Settings(SQLModel, table=True):
    """Application settings"""
    id: int = Field(default=1, primary_key=True)
    theme: str = Field(default="system")  # system/light/dark
    default_backend: Optional[str] = Field(default=None)
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_model: str = Field(default="gpt-4o-mini")
    ollama_base_url: str = Field(default="http://localhost:11434")
    lmstudio_base_url: str = Field(default="http://localhost:1234/v1")
    proxy_url: Optional[str] = Field(default=None)


class DatabaseManager:
    """Database management class"""
    
    def __init__(self, db_url: str = "sqlite:///prompt_studio.db"):
        self.engine = create_engine(db_url, echo=False)
        
    def create_tables(self):
        """Create all tables"""
        SQLModel.metadata.create_all(self.engine)
        
        # Create default settings if not exists
        with Session(self.engine) as session:
            settings = session.get(Settings, 1)
            if not settings:
                settings = Settings(id=1)
                session.add(settings)
                session.commit()
    
    def get_session(self) -> Session:
        """Get database session"""
        return Session(self.engine)
    
    def get_settings(self) -> Settings:
        """Get application settings"""
        with self.get_session() as session:
            settings = session.get(Settings, 1)
            if not settings:
                settings = Settings(id=1)
                session.add(settings)
                session.commit()
                session.refresh(settings)
            return settings
    
    def update_settings(self, **kwargs):
        """Update application settings"""
        with self.get_session() as session:
            settings = session.get(Settings, 1)
            if not settings:
                settings = Settings(id=1)
                session.add(settings)
            
            for key, value in kwargs.items():
                if hasattr(settings, key):
                    setattr(settings, key, value)
            
            session.commit()
