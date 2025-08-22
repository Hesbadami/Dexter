import os
import logging
import json
from typing import List, Dict, Any

from common.config import OPENAI_API_KEY

from openai import OpenAI

logger = logging.getLogger()

class AIEngine:
    def __init__(self):
        api_key = OPENAI_API_KEY
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-5-nano"  # Using your model
        
        # Pricing per 1M tokens
        self.pricing = {
            "input": 0.15,   # $0.15 per 1M input tokens
            "output": 0.60   # $0.60 per 1M output tokens
        }
    
    def calculate_cost(self, usage) -> float:
        """Calculate cost from OpenAI usage object"""
        if not usage:
            return 0.0
        
        input_cost = (usage.prompt_tokens / 1_000_000) * self.pricing["input"]
        output_cost = (usage.completion_tokens / 1_000_000) * self.pricing["output"]
        
        return input_cost + output_cost
    
    def parse_task_dump_with_cost(self, dump_text: str) -> tuple[List[Dict[str, Any]], float]:
        """Parse raw task dump into structured tasks and return cost"""
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
                ]
            )
            
            cost = self.calculate_cost(response.usage)
            logger.info(f"Parse dump cost: ${cost:.4f}")
            
            content = response.choices[0].message.content
            # Extract JSON from response
            start_idx = content.find('[')
            end_idx = content.rfind(']') + 1
            json_str = content[start_idx:end_idx]
            
            return json.loads(json_str), cost
        
        except Exception as e:
            logger.error(f"Failed to parse task dump: {e}")
            return [], 0.0
    
    def decompose_task_with_cost(self, task_content: str) -> tuple[List[Dict[str, Any]], float]:
        """Decompose a task into atomic micro-units and return cost"""
        system_prompt = """
        You are a micro-unit decomposition specialist. Break down ONLY complex tasks that genuinely need multiple steps.

        Return JSON array with this structure:
        [
            {
                "description": "Specific, actionable micro-unit",
                "sequence_order": 1
            }
        ]
        
        CRITICAL RULES:
        - Simple tasks (like "collect keys", "call mom", "buy milk") should have 1-2 units MAX
        - Only decompose if the task genuinely has multiple distinct phases
        - Don't break down obvious single actions into ridiculous micro-steps
        - Each unit should be a meaningful chunk of work (15+ minutes typically)
        - Don't include setup, travel, or trivial preparation steps
        - If it's a simple errand or call, keep it as ONE unit
        
        Examples:
        - "Collect keys from landlord" → 1 unit: "Collect keys from landlord"
        - "Call mom" → 1 unit: "Call mom"  
        - "Build user authentication system" → Multiple units for different components
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Decompose this task:\n\n{task_content}"}
                ]
            )
            
            cost = self.calculate_cost(response.usage)
            logger.info(f"Decompose task cost: ${cost:.4f}")
            
            content = response.choices[0].message.content
            start_idx = content.find('[')
            end_idx = content.rfind(']') + 1
            json_str = content[start_idx:end_idx]
            
            return json.loads(json_str), cost
        
        except Exception as e:
            logger.error(f"Failed to decompose task: {e}")
            return [], 0.0
    
    def calculate_priority_with_cost(self, task_content: str, task_metadata: Dict = None) -> tuple[int, float]:
        """Calculate priority score based on leverage, control, urgency and return cost"""
        system_prompt = """
        Calculate a priority score (1-100) for this task based on:
        - Leverage: Impact on life/career/control (0-40 points)
        - Control: Can act independently without dependencies (0-30 points)  
        - Urgency: Deadline pressure or decay risk (0-30 points)
        
        Return only the integer score, no explanation.
        """
        
        try:
            context = f"Task: {task_content}"
            if task_metadata:
                context += f"\nMetadata: {json.dumps(task_metadata, indent=2)}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context}
                ]
            )
            
            cost = self.calculate_cost(response.usage)
            logger.info(f"Priority calculation cost: ${cost:.4f}")
            
            score = int(response.choices[0].message.content.strip())
            return max(1, min(100, score)), cost  # Clamp between 1-100
        
        except Exception as e:
            logger.error(f"Failed to calculate priority: {e}")
            return 50, 0.0  # Default priority
    
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
                ]
            )
            
            cost = self.calculate_cost(response.usage)
            logger.info(f"Similar tasks search cost: ${cost:.4f}")
            
            content = response.choices[0].message.content
            if '[' in content and ']' in content:
                start_idx = content.find('[')
                end_idx = content.rfind(']') + 1
                json_str = content[start_idx:end_idx]
                return json.loads(json_str)
            
            return []
        
        except Exception as e:
            logger.error(f"Failed to find similar tasks: {e}")
            return []

# Global AI engine instance
ai = AIEngine()