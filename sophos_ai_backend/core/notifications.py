# sophos_ai_backend/core/notifications.py

import requests
import json
import logging
from .config import config
from .database import get_and_increment_report_count

# Initialize a logger for this module.
logger = logging.getLogger(__name__)

def report_incorrect_answer_to_teams(username: str, question: str, answer: str) -> bool:
    """
    Sends a formatted message to a Microsoft Teams channel via a webhook
    when a user reports an incorrect answer.

    This function constructs a rich "card" message with the user's details,
    the question, the incorrect answer, and the current total report count.

    Args:
        username: The name of the user who reported the issue.
        question: The question that led to the incorrect answer.
        answer: The incorrect answer provided by the RAG bot.

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    # Fail early if the Teams webhook URL is not configured in the environment variables.
    if not config.TEAMS_WEBHOOK_URL:
        logger.error("TEAMS_WEBHOOK_URL not configured. Cannot send report notification.")
        return False

    # Construct the message payload for the Teams webhook.
    # This uses a simple JSON structure that Teams can render as a formatted card.
    message = {
        "title": "🚨 Incorrect Answer Reported",
        "text": (
            f"👤 **User:** {username}\n\n"
            f"❓ **Question:**\n```\n{question}\n```\n\n"
            f"💬 **Answer:**\n```\n{answer}\n```\n\n"
            # Fetches and increments the report count from the database for inclusion in the message.
            f"📊 **Report Count:** {get_and_increment_report_count()}"
        )
    }
    headers = {"Content-Type": "application/json"}

    try:
        # Send the POST request to the configured webhook URL.
        response = requests.post(config.TEAMS_WEBHOOK_URL, headers=headers, data=json.dumps(message))
        
        # Check the HTTP status code to confirm the message was received successfully.
        if response.status_code != 200:
            logger.error(f"Failed to send Teams message: {response.status_code} - {response.text}")
            return False
            
        logger.info("Report sent to Microsoft Teams successfully.")
        return True
    except requests.exceptions.RequestException as e:
        # Handle network-related errors (e.g., DNS failure, connection refused).
        logger.error(f"Network error sending Teams message: {e}")
        return False