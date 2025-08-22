import requests
import json
import logging
import re
import hashlib
import os
from typing import Dict, Any, Optional, List
import time
from threading import Thread

from common.config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from common.task_manager import create_task_manager
from common.fish import FishClient

logger = logging.getLogger()

class TelegramBot:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in config")
        
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        self.running = False
        self.task_manager = create_task_manager()
        self.fish = FishClient()
        
        # User states for conversation flow
        self.user_states = {}  # user_id -> current_state
        
        # Caching
        self.tts_cache = {}    # text_hash -> file_path
        self.dump_cache = {}   # dump_hash -> results
        
        # Ensure media directory exists
        os.makedirs('media', exist_ok=True)
    
    def preprocess_text(self, text: str) -> str:
        """Clean text for TTS - keep only English letters, dots, and commas"""
        # Keep only English letters (a-z, A-Z), dots, commas, and spaces
        cleaned = re.sub(r'[^a-zA-Z.,\s]', '', text)
        # Clean up multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    def get_text_hash(self, text: str) -> str:
        """Get hash for text caching"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def remove_keyboard(self, chat_id: int) -> bool:
        """Remove custom keyboard"""
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": "Keyboard removed. Use slash commands.",
            "reply_markup": json.dumps({"remove_keyboard": True})
        }
        
        try:
            response = requests.post(url, data=data)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to remove keyboard: {e}")
            return False
    
    def send_voice_message(self, chat_id: int, text: str, openai_cost: float = 0.0) -> bool:
        """Send voice message via TTS with caching and cost tracking"""
        try:
            # Preprocess text
            clean_text = self.preprocess_text(text)
            if not clean_text:
                return False
            
            fish_cost = 0.0
            
            # Check cache
            text_hash = self.get_text_hash(clean_text)
            
            if text_hash in self.tts_cache and os.path.exists(self.tts_cache[text_hash]):
                mp3_path = self.tts_cache[text_hash]
                logger.info(f"Using cached TTS for: {clean_text[:50]}...")
                # No fish cost for cached audio
            else:
                # Generate new MP3 and get cost
                mp3_path, fish_cost = self.fish.text_to_mp3_with_cost(clean_text)
                # Cache the result
                self.tts_cache[text_hash] = mp3_path
            
            # Build caption with costs
            caption = f"Fish: ${fish_cost:.4f} | OpenAI: ${openai_cost:.4f}"
            
            # Send voice message with caption
            url = f"{self.base_url}/sendVoice"
            with open(mp3_path, 'rb') as audio:
                files = {'voice': audio}
                data = {
                    'chat_id': chat_id,
                    'caption': caption
                }
                response = requests.post(url, data=data, files=files)
                return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Failed to send voice message: {e}")
            return False
    
    def get_updates(self) -> List[Dict]:
        """Get updates from Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {
            "offset": self.offset,
            "timeout": 30
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data["ok"]:
                    return data["result"]
        except Exception as e:
            logger.error(f"Failed to get updates: {e}")
        
        return []
    
    def get_pending_tasks(self) -> List:
        """Get all pending micro-units ordered by priority"""
        from database.models import MicroUnit, Task
        
        return (
            self.task_manager.session.query(MicroUnit)
            .join(Task)
            .filter(MicroUnit.status == 'pending')
            .filter(Task.status.in_(['pending', 'active']))
            .order_by(Task.priority.desc(), MicroUnit.sequence_order.asc())
            .all()
        )
    
    def handle_dump_command(self, chat_id: int, user_id: int) -> None:
        """Handle /dump command"""
        self.user_states[user_id] = "waiting_for_dump"
        self.send_voice_message(chat_id, "Send me your task dump")
    
    def handle_tasks_command(self, chat_id: int, limit: Optional[int] = None) -> None:
        """Handle /tasks command - list all pending micro-units"""
        try:
            pending_units = self.get_pending_tasks()
            
            if not pending_units:
                self.send_voice_message(chat_id, "No pending tasks")
                return
            
            # Apply limit if specified
            if limit:
                pending_units = pending_units[:limit]
            
            # Build task list - just descriptions
            descriptions = [unit.description for unit in pending_units]
            task_text = ". ".join(descriptions)
            
            self.send_voice_message(chat_id, task_text)
            
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            self.send_voice_message(chat_id, "Error getting tasks")
    
    def handle_task_command(self, chat_id: int, count: Optional[int] = 1) -> None:
        """Handle /task command - get next task(s)"""
        try:
            pending_units = self.get_pending_tasks()
            
            if not pending_units:
                self.send_voice_message(chat_id, "No pending tasks")
                return
            
            # Get the specified number of tasks
            tasks_to_show = pending_units[:count]
            descriptions = [unit.description for unit in tasks_to_show]
            task_text = ". ".join(descriptions)
            
            self.send_voice_message(chat_id, task_text)
            
        except Exception as e:
            logger.error(f"Error getting next task: {e}")
            self.send_voice_message(chat_id, "Error getting next task")
    
    def handle_done_command(self, chat_id: int) -> None:
        """Handle /done command - complete first task and read next"""
        try:
            pending_units = self.get_pending_tasks()
            
            if not pending_units:
                self.send_voice_message(chat_id, "No tasks to complete")
                return
            
            # Complete the first task
            first_task = pending_units[0]
            self.task_manager.complete_micro_unit(first_task.id, success=True)
            
            # Get next task after completion
            next_pending = self.get_pending_tasks()
            
            if next_pending:
                # Read the next task
                next_task_text = next_pending[0].description
                self.send_voice_message(chat_id, next_task_text)
            else:
                self.send_voice_message(chat_id, "No more tasks")
            
        except Exception as e:
            logger.error(f"Error completing task: {e}")
            self.send_voice_message(chat_id, "Error completing task")
    
    def handle_clear_command(self, chat_id: int) -> None:
        """Handle /clear command - delete all tasks"""
        try:
            from database.models import Task, MicroUnit, Execution
            
            # Delete in correct order to respect foreign key constraints
            # 1. Delete executions first
            self.task_manager.session.query(Execution).delete()
            
            # 2. Delete micro-units  
            self.task_manager.session.query(MicroUnit).delete()
            
            # 3. Delete tasks
            self.task_manager.session.query(Task).delete()
            
            self.task_manager.session.commit()
            
            self.send_voice_message(chat_id, "All tasks cleared")
            
        except Exception as e:
            logger.error(f"Error clearing tasks: {e}")
            # Rollback on error
            self.task_manager.session.rollback()
            self.send_voice_message(chat_id, "Error clearing tasks")
    
    def handle_tts_command(self, chat_id: int, user_id: int) -> None:
        """Handle /tts command - wait for next message to convert"""
        self.user_states[user_id] = "waiting_for_tts"
        # Don't send any response, just wait for next message
    
    def process_dump(self, chat_id: int, user_id: int, dump_text: str) -> None:
        """Process task dump with caching"""
        try:
            # Check cache first
            dump_hash = self.get_text_hash(dump_text)
            openai_cost = 0.0
            
            if dump_hash in self.dump_cache:
                logger.info(f"Using cached dump result for: {dump_text[:50]}...")
                results = self.dump_cache[dump_hash]
                # No OpenAI cost for cached results
            else:
                self.send_voice_message(chat_id, "Processing tasks")
                results, openai_cost = self.task_manager.process_dump_with_cost(dump_text)
                # Cache the result
                self.dump_cache[dump_hash] = results
            
            if results["new_tasks"] == 0:
                self.send_voice_message(chat_id, "No tasks could be extracted from your input", openai_cost)
                return
            
            # Simple completion message
            message = f"Created {results['new_tasks']} tasks with {results['total_micro_units']} units"
            self.send_voice_message(chat_id, message, openai_cost)
            
        except Exception as e:
            logger.error(f"Error processing dump: {e}")
            self.send_voice_message(chat_id, "Error processing tasks")
        finally:
            # Reset state
            self.user_states.pop(user_id, None)
    
    def process_tts_text(self, chat_id: int, user_id: int, text: str) -> None:
        """Process text for TTS conversion"""
        try:
            self.send_voice_message(chat_id, text)
        except Exception as e:
            logger.error(f"Error processing TTS: {e}")
        finally:
            # Reset state
            self.user_states.pop(user_id, None)
    
    def handle_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming message"""
        try:
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "")
            
            # Security check: Only allow admin user
            if int(user_id) != int(ADMIN_USER_ID):
                logger.warning(f"Unauthorized access attempt from user {user_id}")
                return  # Silently drop the message
            
            # Get current user state
            current_state = self.user_states.get(user_id)
            
            # Handle states first
            if current_state == "waiting_for_dump":
                self.process_dump(chat_id, user_id, text)
                return
            elif current_state == "waiting_for_tts":
                self.process_tts_text(chat_id, user_id, text)
                return
            
            # Handle commands
            if text.startswith("/"):
                parts = text.split(None, 1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                if command == "/start":
                    # Remove old keyboard if it exists
                    self.remove_keyboard(chat_id)
                    self.send_voice_message(chat_id, "Task manager ready. Use slash dump to add tasks, slash task for next task, slash done to complete")
                    
                elif command == "/dump":
                    self.handle_dump_command(chat_id, user_id)
                    
                elif command == "/tasks":
                    self.handle_tasks_command(chat_id)
                    
                elif command == "/task":
                    if args and args.isdigit():
                        count = int(args)
                        self.handle_task_command(chat_id, count)
                    else:
                        self.handle_task_command(chat_id, 1)
                        
                elif command == "/done":
                    self.handle_done_command(chat_id)
                    
                elif command == "/clear":
                    self.handle_clear_command(chat_id)
                    
                elif command == "/tts":
                    self.handle_tts_command(chat_id, user_id)
                        
                else:
                    self.send_voice_message(chat_id, "Unknown command")
            else:
                # Non-command text when not in a state
                self.send_voice_message(chat_id, "Use slash commands")
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def run_polling(self) -> None:
        """Run bot with polling"""
        self.running = True
        logger.info("Telegram bot started polling...")
        
        while self.running:
            try:
                updates = self.get_updates()
                
                for update in updates:
                    # Update offset
                    self.offset = update["update_id"] + 1
                    
                    # Handle message
                    if "message" in update:
                        self.handle_message(update["message"])
                
                # Small delay to prevent hammering
                if not updates:
                    time.sleep(1)
                    
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                time.sleep(5)  # Wait before retrying
        
        self.running = False
    
    def start(self) -> None:
        """Start bot in separate thread"""
        thread = Thread(target=self.run_polling, daemon=True)
        thread.start()
        return thread
    
    def stop(self) -> None:
        """Stop the bot"""
        self.running = False
        if hasattr(self, 'task_manager'):
            self.task_manager.close()

# Usage
def create_telegram_bot():
    """Create a new TelegramBot instance"""
    return TelegramBot()

if __name__ == "__main__":
    # Direct run
    logging.basicConfig(level=logging.INFO)
    bot = create_telegram_bot()
    
    try:
        bot.run_polling()
    except KeyboardInterrupt:
        bot.stop()
        print("Bot stopped.")