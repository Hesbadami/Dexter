import logging
import sys
from common.telegram import create_telegram_bot

logger = logging.getLogger(__name__)

def main():
    """Main entry point"""
    try:
        logger.info("🔪 Starting Dexter's Task Hunter Bot...")
        
        # Create and start bot
        bot = create_telegram_bot()
        
        # Start polling
        bot.run_polling()
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
        if 'bot' in locals():
            bot.stop()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()