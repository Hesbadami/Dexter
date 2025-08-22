import logging
import os

from common.config import DB_CFG
from database.models import Base

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger()

class Database:
    def __init__(self):
        
        self.connection_string = "postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}".format(**DB_CFG)
        self.engine = create_engine(self.connection_string, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def create_tables(self):
        """Create all tables defined in models"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created successfully")
    
    def get_session(self):
        """Get a database session"""
        return self.SessionLocal()
    
    def test_connection(self):
        """Test database connection"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                logger.info("Database connection successful")
                return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    def enable_full_text_search(self):
        """Enable PostgreSQL full-text search capabilities"""
        try:
            with self.engine.connect() as conn:
                # Add tsvector column for full-text search
                conn.execute(text("""
                    ALTER TABLE tasks 
                    ADD COLUMN IF NOT EXISTS search_vector tsvector;
                """))
                
                # Create index for full-text search
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS tasks_search_idx 
                    ON tasks USING GIN(search_vector);
                """))
                
                # Create trigger to automatically update search_vector
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION update_task_search_vector()
                    RETURNS trigger AS $$
                    BEGIN
                        NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """))
                
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS update_task_search_trigger ON tasks;
                    CREATE TRIGGER update_task_search_trigger
                    BEFORE INSERT OR UPDATE ON tasks
                    FOR EACH ROW EXECUTE FUNCTION update_task_search_vector();
                """))
                
                conn.commit()
                logger.info("Full-text search enabled")
        except Exception as e:
            logger.error(f"Failed to enable full-text search: {e}")

# Global database instance
db = Database()