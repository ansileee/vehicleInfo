import logging
import re
import uuid
import json
import os
import requests  # type: ignore
from dotenv import load_dotenv  # type: ignore
from telegram import Update  # type: ignore
from telegram.ext import (  # type: ignore
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -- Config -------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in .env file")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -- RC number helpers --------------------------------------------------------

# Pattern: 2 letters (state) + 2 digits (RTO) + 1-3 letters (series) + 1-4 digits (number)
RC_PATTERN = re.compile(
    r"^([A-Z]{2})(\d{2})([A-Z]{1,3})(\d{1,4})$",
    re.IGNORECASE,
)


def normalize_rc(raw: str) -> str | None:
    """
    Validate and normalize an RC number.
    - Strips spaces/hyphens
    - Pads the trailing numeric part to 4 digits
    - Returns None if the format is unrecognizable
    """
    cleaned = raw.strip().upper().replace(" ", "").replace("-", "")
    m = RC_PATTERN.match(cleaned)
    if not m:
        return None
    state, rto, series, number = m.groups()
    padded_number = number.zfill(4)
    return f"{state}{rto}{series}{padded_number}"


# -- Core lookup (original logic, untouched) ----------------------------------

def rc_lookup(rc_number: str) -> dict:
    if not rc_number.strip():
        return {"status": "error", "message": "No RC number"}

    session_id = f"{uuid.uuid4()}-{uuid.uuid4()}"

    payload = {
        "regNo": rc_number.strip().upper(),
        "sessionid": session_id,
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.91wheels.com",
        "Referer": "https://www.91wheels.com/",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile Safari/537.36)",
    }

    try:
        response = requests.post(
            "https://api1.91wheels.com/api/v1/third/rc-detail",
            headers=headers,
            data=json.dumps(payload),
            timeout=15,
        )
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": str(e)}


# -- Bot handlers -------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "RC Vehicle Info Bot\n\n"
        "Enter a vehicle registration number to look up.\n\n"
        "Examples: KL41V3504, MH12AB1234, DL4C0001\n\n"
        "Short numbers are auto-padded, e.g. KL41V1 becomes KL41V0001."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw_input = update.message.text.strip()

    normalized = normalize_rc(raw_input)

    if normalized is None:
        await update.message.reply_text(
            f"Invalid format: {raw_input.upper()}\n\n"
            "Expected: STATE + RTO + SERIES + NUMBER\n"
            "Examples: KL41V3504, MH12AB1, DL4CAB123\n\n"
            "Please try again."
        )
        return

    raw_cleaned = raw_input.upper().replace(" ", "").replace("-", "")
    if normalized != raw_cleaned:
        await update.message.reply_text(
            f"Auto-corrected: {raw_input.upper()} -> {normalized}"
        )

    await update.message.reply_text(f"Looking up {normalized}...")

    result = rc_lookup(normalized)
    result["credit"] = "@drazeforce"
    output = json.dumps(result, indent=2, ensure_ascii=False)

    max_len = 4000
    chunks = [output[i : i + max_len] for i in range(0, len(output), max_len)]

    for i, chunk in enumerate(chunks):
        part_label = f" (part {i+1}/{len(chunks)})" if len(chunks) > 1 else ""
        await update.message.reply_text(
            f"```json\n{chunk}\n```{part_label}",
            parse_mode="Markdown",
        )


# -- Main ---------------------------------------------------------------------

def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
