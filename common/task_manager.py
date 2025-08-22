from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from database.database import db
from database.models import Task, MicroUnit, Execution
from common.openai import ai

from sqlalchemy import text

logger = logging.getLogger()



class TaskManager:
    def __init__(self):
        self.session = db.get_session()
    
    def process_dump(self, dump_text: str) -> Dict[str, Any]:
        """Main entry point: process raw task dump"""
        logger.info("🧠 Processing task dump...")
        
        # Step 1: Parse dump into structured tasks
        parsed_tasks = ai.parse_task_dump(dump_text)
        
        results = {
            "new_tasks": 0,
            "merged_tasks": 0,
            "total_micro_units": 0,
            "tasks_created": []
        }
        
        for task_data in parsed_tasks:
            # Step 2: Check for similar existing tasks
            similar_tasks = self._find_similar_existing_tasks(task_data["content"])
            
            if similar_tasks:
                logger.info(f"🔄 Found similar tasks, considering merge...")
                # For now, create anyway - later we can implement smart merging
            
            # Step 3: Create task
            task = self._create_task(task_data)
            
            # Step 4: Decompose into micro-units
            micro_units = self._decompose_task(task)
            
            results["new_tasks"] += 1
            results["total_micro_units"] += len(micro_units)
            results["tasks_created"].append({
                "task_id": task.id,
                "content": task.content[:50] + "...",
                "micro_units": len(micro_units),
                "priority": task.priority
            })
        
        self.session.commit()
        return results
    
    def get_next_action(self) -> Optional[MicroUnit]:
        """Binary decision: Get next micro-unit to execute (READ-ONLY)"""
        # Get highest priority pending micro-unit WITHOUT changing status
        next_unit = (
            self.session.query(MicroUnit)
            .join(Task)
            .filter(MicroUnit.status == 'pending')
            .filter(Task.status.in_(['pending', 'active']))
            .order_by(Task.priority.desc(), MicroUnit.sequence_order.asc())
            .first()
        )
        
        if next_unit:
            logger.info(f"🎯 Next target: {next_unit.description}")
            return next_unit
        
        logger.info("✅ No pending tasks - you're clear!")
        return None
    
    def start_micro_unit(self, micro_unit_id: int) -> bool:
        """Mark micro-unit as active when you start working on it"""
        micro_unit = self.session.get(MicroUnit, micro_unit_id)
        
        if not micro_unit:
            logger.info(f"❌ Micro-unit {micro_unit_id} not found")
            return False
        
        if micro_unit.status != 'pending':
            logger.info(f"⚠️  Micro-unit {micro_unit_id} is not pending (status: {micro_unit.status})")
            return False
        
        # Mark as active
        micro_unit.status = 'active'
        micro_unit.task.status = 'active'
        self.session.commit()
        
        logger.info(f"▶️  Started: {micro_unit.description[:50]}...")
        return True
    
    def complete_micro_unit(self, micro_unit_id: int, success: bool = True, 
                          actual_minutes: int = None, notes: str = None):
        """Mark micro-unit as complete and log execution"""
        micro_unit = self.session.get(MicroUnit, micro_unit_id)
        
        if not micro_unit:
            logger.info(f"❌ Micro-unit {micro_unit_id} not found")
            return
        
        # Mark complete
        micro_unit.mark_complete(actual_minutes)
        
        # Log execution
        execution = Execution(
            micro_unit_id=micro_unit_id,
            completed_at=datetime.now(),
            success=success,
            notes=notes
        )
        self.session.add(execution)
        
        # Check if task is complete
        remaining_units = (
            self.session.query(MicroUnit)
            .filter(MicroUnit.task_id == micro_unit.task_id)
            .filter(MicroUnit.status == 'pending')
            .count()
        )
        
        if remaining_units == 0:
            micro_unit.task.status = 'complete'
            logger.info(f"🏆 Task complete: {micro_unit.task.content[:50]}...")
        
        self.session.commit()
        logger.info(f"✅ Micro-unit completed: {micro_unit.description[:50]}...")
    
    def process_dump_with_cost(self, dump_text: str) -> tuple[Dict[str, Any], float]:
        """Main entry point: process raw task dump and return total OpenAI cost"""
        logger.info("Processing task dump...")
        
        total_openai_cost = 0.0
        
        # Step 1: Parse dump into structured tasks
        parsed_tasks, parse_cost = ai.parse_task_dump_with_cost(dump_text)
        total_openai_cost += parse_cost
        
        results = {
            "new_tasks": 0,
            "merged_tasks": 0,
            "total_micro_units": 0,
            "tasks_created": []
        }
        
        for task_data in parsed_tasks:
            # Step 2: Check for similar existing tasks
            similar_tasks = self._find_similar_existing_tasks(task_data["content"])
            
            if similar_tasks:
                logger.info(f"Found similar tasks, considering merge...")
                # For now, create anyway - later we can implement smart merging
            
            # Step 3: Create task (includes priority calculation cost)
            task, priority_cost = self._create_task_with_cost(task_data)
            total_openai_cost += priority_cost
            
            # Step 4: Decompose into micro-units
            micro_units, decompose_cost = self._decompose_task_with_cost(task)
            total_openai_cost += decompose_cost
            
            results["new_tasks"] += 1
            results["total_micro_units"] += len(micro_units)
            results["tasks_created"].append({
                "task_id": task.id,
                "content": task.content[:50] + "...",
                "micro_units": len(micro_units),
                "priority": task.priority
            })
        
        self.session.commit()
        return results, total_openai_cost
        """Get current status summary"""
        summary = {}
        
        # Task counts by status
        task_counts = (
            self.session.query(Task.status, db.engine.func.count(Task.id))
            .group_by(Task.status)
            .all()
        )
        summary["tasks"] = dict(task_counts)
        
        # Micro-unit counts
        unit_counts = (
            self.session.query(MicroUnit.status, db.engine.func.count(MicroUnit.id))
            .group_by(MicroUnit.status)
            .all()
        )
        summary["micro_units"] = dict(unit_counts)
        
        # Today's completed units
        today_executions = (
            self.session.query(Execution)
            .filter(Execution.completed_at >= datetime.now().date())
            .filter(Execution.success == True)
            .count()
        )
        summary["today_completed"] = today_executions
        
        # API costs
        summary["total_api_cost"] = ai.get_total_cost()
        
        return summary
    
    def _find_similar_existing_tasks(self, task_content: str) -> List[Task]:
        """Find similar existing tasks using full-text search"""
        try:
            # Use PostgreSQL full-text search
            query = text("""
                SELECT id, content, ts_rank(search_vector, plainto_tsquery(:query)) as rank
                FROM tasks 
                WHERE search_vector @@ plainto_tsquery(:query)
                AND status IN ('pending', 'active')
                ORDER BY rank DESC
                LIMIT 5
            """)
            
            results = self.session.execute(query, {"query": task_content}).fetchall()
            
            if results:
                # Get Task objects
                task_ids = [r[0] for r in results if r[2] > 0.1]  # rank threshold
                return self.session.query(Task).filter(Task.id.in_(task_ids)).all()
            
        except Exception as e:
            logger.info(f"⚠️  Full-text search failed, using fallback: {e}")
        
        return []
    
    def _create_task(self, task_data: Dict[str, Any]) -> Task:
        """Create a new task from parsed data"""
        priority = ai.calculate_priority(
            task_data["content"], 
            {"category": task_data.get("category")}
        )
        
        task = Task(
            content=task_data["content"],
            priority=priority,
            metadata={
                "category": task_data.get("category"),
                "estimated_complexity": task_data.get("estimated_complexity"),
                "priority_hints": task_data.get("priority_hints")
            }
        )
        
        self.session.add(task)
        self.session.flush()  # Get the ID
        return task
    
    def _decompose_task(self, task: Task) -> List[MicroUnit]:
        """Decompose task into micro-units"""
        micro_data = ai.decompose_task(task.content)
        micro_units = []
        
        for i, unit_data in enumerate(micro_data):
            micro_unit = MicroUnit(
                task_id=task.id,
                description=unit_data["description"],
                sequence_order=unit_data.get("sequence_order", i + 1),
                estimated_minutes=unit_data.get("estimated_minutes"),
                metadata={
                    "binary_check": unit_data.get("binary_check"),
                    "dependencies": unit_data.get("dependencies", [])
                }
            )
            micro_units.append(micro_unit)
            self.session.add(micro_unit)
        
        return micro_units
    
    def close(self):
        """Close database session"""
        self.session.close()

# Usage helper
def create_task_manager():
    """Create a new TaskManager instance"""
    return TaskManager()