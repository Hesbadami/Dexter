import requests
import json
import logging
import re
from typing import Dict, Any, Optional, List
import time
from threading import Thread

from common.config import TELEGRAM_BOT_TOKEN
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
    
    def preprocess_text(self, text: str) -> str:
        """Clean text for TTS - keep only English letters, dots, and commas"""
        # Keep only English letters (a-z, A-Z), dots, commas, and spaces
        cleaned = re.sub(r'[^a-zA-Z.,\s]', '', text)
        # Clean up multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    def send_voice_message(self, chat_id: int, text: str) -> bool:
        """Send voice message via TTS"""
        try:
            # Preprocess text
            clean_text = self.preprocess_text(text)
            if not clean_text:
                return False
            
            # Generate MP3
            mp3_path = self.fish.text_to_mp3(clean_text)
            
            # Send voice message
            url = f"{self.base_url}/sendVoice"
            with open(mp3_path, 'rb') as audio:
                files = {'voice': audio}
                data = {'chat_id': chat_id}
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
    
    def handle_dump_command(self, chat_id: int, user_id: int) -> None:
        """Handle /dump command"""
        self.user_states[user_id] = "waiting_for_dump"
        self.send_voice_message(chat_id, "Send me your task dump")
    
    def handle_tasks_command(self, chat_id: int) -> None:
        """Handle /tasks command - list all pending micro-units"""
        try:
            from database.models import MicroUnit, Task
            
            # Get all pending micro-units ordered by priority
            pending_units = (
                self.task_manager.session.query(MicroUnit)
                .join(Task)
                .filter(MicroUnit.status == 'pending')
                .filter(Task.status.in_(['pending', 'active']))
                .order_by(Task.priority.desc(), MicroUnit.sequence_order.asc())
                .all()
            )
            
            if not pending_units:
                self.send_voice_message(chat_id, "No pending tasks")
                return
            
            # Build task list
            task_list = "Task list. "
            for i, unit in enumerate(pending_units[:20], 1):  # Limit to 20 for voice
                task_list += f"Number {i}. ID {unit.id}. {unit.description}. "
            
            if len(pending_units) > 20:
                task_list += f"And {len(pending_units) - 20} more tasks."
            
            self.send_voice_message(chat_id, task_list)
            
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            self.send_voice_message(chat_id, "Error getting tasks")
    
    def handle_delete_command(self, chat_id: int, task_id_str: str) -> None:
        """Handle /delete command"""
        try:
            task_id = int(task_id_str.strip())
            
            # Find and delete the micro-unit
            from database.models import MicroUnit
            micro_unit = self.task_manager.session.get(MicroUnit, task_id)
            
            if not micro_unit:
                self.send_voice_message(chat_id, f"Task ID {task_id} not found")
                return
            
            # Get description before deletion
            description = micro_unit.description[:50]
            
            # Delete the micro-unit
            self.task_manager.session.delete(micro_unit)
            self.task_manager.session.commit()
            
            self.send_voice_message(chat_id, f"Deleted task {task_id}")
            
        except ValueError:
            self.send_voice_message(chat_id, "Invalid task ID format")
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            self.send_voice_message(chat_id, "Error deleting task")
    
    def handle_transcribe_command(self, chat_id: int, text: str) -> None:
        """Handle /transcribe command"""
        if not text.strip():
            self.send_voice_message(chat_id, "Please provide text to transcribe")
            return
        
        self.send_voice_message(chat_id, text)
    
    def process_dump(self, chat_id: int, user_id: int, dump_text: str) -> None:
        """Process task dump"""
        try:
            self.send_voice_message(chat_id, "Processing tasks")
            
            results = self.task_manager.process_dump(dump_text)
            
            if results["new_tasks"] == 0:
                self.send_voice_message(chat_id, "No tasks could be extracted from your input")
                return
            
            # Simple completion message
            message = f"Created {results['new_tasks']} tasks with {results['total_micro_units']} units"
            self.send_voice_message(chat_id, message)
            
        except Exception as e:
            logger.error(f"Error processing dump: {e}")
            self.send_voice_message(chat_id, "Error processing tasks")
        finally:
            # Reset state
            self.user_states.pop(user_id, None)
    
    def handle_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming message"""
        try:
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "")
            
            # Get current user state
            current_state = self.user_states.get(user_id)
            
            # Handle states first
            if current_state == "waiting_for_dump":
                self.process_dump(chat_id, user_id, text)
                return
            
            # Handle commands
            if text.startswith("/"):
                parts = text.split(None, 1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                if command == "/start":
                    self.send_voice_message(chat_id, "Task manager ready. Use slash dump to add tasks, slash tasks to list them, slash delete with ID to remove")
                    
                elif command == "/dump":
                    self.handle_dump_command(chat_id, user_id)
                    
                elif command == "/tasks":
                    self.handle_tasks_command(chat_id)
                    
                elif command == "/delete":
                    if args:
                        self.handle_delete_command(chat_id, args)
                    else:
                        self.send_voice_message(chat_id, "Please provide task ID to delete")
                        
                elif command == "/transcribe":
                    if args:
                        self.handle_transcribe_command(chat_id, args)
                    else:
                        self.send_voice_message(chat_id, "Please provide text to transcribe")
                        
                else:
                    self.send_voice_message(chat_id, "Unknown command")
            else:
                # Non-command text
                self.send_voice_message(chat_id, "Use slash commands. slash dump, slash tasks, slash delete, slash transcribe")
                
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