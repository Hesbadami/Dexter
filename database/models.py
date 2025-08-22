from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    status = Column(String(20), default='pending')  # pending, active, complete, archived
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    task_metadata = Column(JSON, default=dict)
    
    # Relationships
    micro_units = relationship("MicroUnit", back_populates="task", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Task(id={self.id}, content='{self.content[:50]}...', status='{self.status}')>"

class MicroUnit(Base):
    __tablename__ = 'micro_units'
    
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'), nullable=False)
    description = Column(Text, nullable=False)
    sequence_order = Column(Integer, nullable=False)
    status = Column(String(20), default='pending')  # pending, active, complete, skipped
    estimated_minutes = Column(Integer)
    actual_minutes = Column(Integer)
    completed_at = Column(DateTime)
    unit_metadata = Column(JSON, default=dict)
    
    # Relationships
    task = relationship("Task", back_populates="micro_units")
    executions = relationship("Execution", back_populates="micro_unit", cascade="all, delete-orphan")
    
    def mark_complete(self, actual_minutes=None):
        self.status = 'complete'
        self.completed_at = datetime.now()
        if actual_minutes:
            self.actual_minutes = actual_minutes
    
    def __repr__(self):
        return f"<MicroUnit(id={self.id}, description='{self.description[:30]}...', status='{self.status}')>"

class Execution(Base):
    __tablename__ = 'executions'
    
    id = Column(Integer, primary_key=True)
    micro_unit_id = Column(Integer, ForeignKey('micro_units.id'), nullable=False)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime)
    notes = Column(Text)
    success = Column(Boolean)
    
    # Relationships
    micro_unit = relationship("MicroUnit", back_populates="executions")
    
    def __repr__(self):
        return f"<Execution(id={self.id}, micro_unit_id={self.micro_unit_id}, success={self.success})>"