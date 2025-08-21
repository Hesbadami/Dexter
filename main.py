import logging

from common.discord import bot
from common.config import DISCORD_TOKEN

logger = logging.getLogger()

def main():
    logger.info(f"Running server")
    bot.run(DISCORD_TOKEN)


if __name__ == '__main__':
    main()
    logger.info(f"Terminated.")