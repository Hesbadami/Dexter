import os
import logging
import json
from typing import List, Dict, Any

from common.config import OPENAI_API_KEY

from openai import OpenAI

logger = logging.getLogger()


class AIEngine:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-5-nano"  # Using gpt-4o-mini (nano equivalent)
        self.total_cost = 0.0
        
        # Pricing per 1M tokens (as of 2024)
        self.pricing = {
            "gpt-4o-mini": {"input": 0.15, "output": 0.60}  # $0.15/$0.60 per 1M tokens
        }
    
    def parse_task_dump(self, dump_text: str) -> List[Dict[str, Any]]:
        """Parse raw task dump into structured tasks"""
        system_prompt = """
        You are a surgical task decomposition engine. Parse the user's brain dump into clean, actionable tasks.
        
        Extract distinct tasks and return them as JSON array with this structure:
        [
            {
                "content": "Clear description of the task",
                "category": "Work/Home/Health/Social/Finance/Learning/Misc",
                "priority_hints": "Any urgency or importance clues",
                "estimated_complexity": "low/medium/high"
            }
        ]
        
        Rules:
        - Each task should be one clear objective
        - Don't over-segment - keep related sub-tasks together
        - Extract the essence, not the exact wording
        - If something is vague, make it concrete
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse this task dump:\n\n{dump_text}"}
                ],
            )
            
            self._track_cost(response)
            
            content = response.choices[0].message.content
            # Extract JSON from response
            start_idx = content.find('[')
            end_idx = content.rfind(']') + 1
            json_str = content[start_idx:end_idx]
            
            return json.loads(json_str)
        
        except Exception as e:
            logger.info(f"❌ Failed to parse task dump: {e}")
            return []
        
    def _track_cost(self, response):
        """Track API costs from response"""
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            
            # Calculate cost
            input_cost = (input_tokens / 1_000_000) * self.pricing[self.model]["input"]
            output_cost = (output_tokens / 1_000_000) * self.pricing[self.model]["output"]
            total_cost = input_cost + output_cost
            
            self.total_cost += total_cost
            
            logger.info(f"💰 API Call: ${total_cost:.4f} (${self.total_cost:.4f} total)")
    
    def get_total_cost(self) -> float:
        """Get total accumulated API costs"""
        return self.total_cost
    
    def reset_cost_tracking(self):
        """Reset cost tracking"""
        self.total_cost = 0.0
    
    def decompose_task(self, task_content: str) -> List[Dict[str, Any]]:
        """Decompose a task into atomic micro-units"""
        system_prompt = """
        You are a micro-unit decomposition specialist. Break down the given task into atomic, executable micro-units.
        
        Return JSON array with this structure:
        [
            {
                "description": "Specific, actionable micro-unit",
                "estimated_minutes": 15,
                "sequence_order": 1,
                "dependencies": ["previous micro-unit if any"],
                "binary_check": "Clear yes/no criteria for completion"
            }
        ]
        
        Rules:
        - Each micro-unit should be 5-45 minutes max
        - Must be atomic - cannot be broken down further
        - Should have clear start/stop criteria
        - Include setup/cleanup if needed
        - Order them logically
        - Be specific about deliverables
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Decompose this task:\n\n{task_content}"}
                ],
            )
            
            self._track_cost(response)
            
            content = response.choices[0].message.content
            start_idx = content.find('[')
            end_idx = content.rfind(']') + 1
            json_str = content[start_idx:end_idx]
            
            return json.loads(json_str)
        
        except Exception as e:
            logger.info(f"❌ Failed to decompose task: {e}")
            return []
    
    def calculate_priority(self, task_content: str, metadata: Dict = None) -> int:
        """Calculate priority score based on leverage, control, urgency"""
        system_prompt = """
        Calculate a priority score (1-100) for this task based on:
        - Leverage: Impact on life/career/control (0-40 points)
        - Control: Can act independently without dependencies (0-30 points)  
        - Urgency: Deadline pressure or decay risk (0-30 points)
        
        Return only the integer score, no explanation.
        """
        
        try:
            context = f"Task: {task_content}"
            if metadata:
                context += f"\nMetadata: {json.dumps(metadata, indent=2)}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
            )
            
            self._track_cost(response)
            
            score = int(response.choices[0].message.content.strip())
            return max(1, min(100, score))  # Clamp between 1-100
        
        except Exception as e:
            logger.info(f"❌ Failed to calculate priority: {e}")
            return 50  # Default priority
    
    def find_similar_tasks(self, new_task: str, existing_tasks: List[str]) -> List[Dict[str, Any]]:
        """Find similar existing tasks for potential merging"""
        if not existing_tasks:
            return []
        
        system_prompt = """
        Compare the new task against existing tasks and find similar ones that could be merged.
        
        Return JSON array with this structure:
        [
            {
                "existing_task": "The similar existing task",
                "similarity_score": 0.85,
                "merge_suggestion": "How they could be combined"
            }
        ]
        
        Only return matches with similarity_score > 0.7
        """
        
        try:
            context = f"New task: {new_task}\n\nExisting tasks:\n"
            context += "\n".join([f"- {task}" for task in existing_tasks])
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ],
            )
            
            self._track_cost(response)
            
            content = response.choices[0].message.content
            if '[' in content and ']' in content:
                start_idx = content.find('[')
                end_idx = content.rfind(']') + 1
                json_str = content[start_idx:end_idx]
                return json.loads(json_str)
            
            return []
        
        except Exception as e:
            logger.info(f"❌ Failed to find similar tasks: {e}")
            return []

# Global AI engine instance
ai = AIEngine()