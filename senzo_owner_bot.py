"""
SENZO OWNER CONTROL BOT — the owner's premium dashboard

Run this bot on the OWNER's machine (once, keep it alive). It turns one
Telegram bot into a full control panel for every licensed Senzo user:

    /status          → live report of all connected users (sources, counts)
    /push <link>     → push a channel link to every user's "Tasks" panel
    /broadcast <msg> → send an in-app announcement to every user
    /update <url>    → announce a new version with download link
    /req <user> <link>  → privately ask one user to clone a channel

How it works (no server needed):
    • A private Telegram CHANNEL is used as the "control board". The bot
      pins command messages in it; user apps read the pinned messages.
    • Users send stats back to a private REPORT CHANNEL (the bot watches it).
    • The bot formats everything nicely for the owner.

Setup (one time):
    1. In Telegram: create channel "Senzo Control" → add the bot as ADMIN
       with posting rights. Copy its channel ID (e.g. -1001234567890)
       into senzo_owner.env  (CONTROL_ID=...)
    2. Create channel "Senzo Reports" → add bot as admin. Set REPORT_ID=...
    3. Fill BOT_TOKEN=... (from @BotFather) and OWNER_ID=your telegram id
    4. Run:  pip install python-telegram-bot
             python senzo_owner_bot.py
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("senzo-owner")

try:
    from telegram import Update
    from telegram.ext import (Application, CommandHandler, MessageHandler,
                              ContextTypes, filters)
except ImportError:
    sys.exit("Run: pip install python-telegram-bot")

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "senzo_owner.env"))

# Railway variables: BOT_TOKEN / TELEGRAM_BOT_TOKEN / TOKEN sab chalein ge
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
CONTROL_ID = os.getenv("CONTROL_ID")       # channel where commands are posted
REPORT_ID = os.getenv("REPORT_ID")         # channel where users report

_store = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "senzo_reports.json")


def load_reports():
    if os.path.exists(_store):
        with open(_store) as f:
            return json.load(f)
    return {}


def save_reports(data):
    with open(_store, "w") as f:
        json.dump(data, f, indent=2)


# ------------------------------------------------------------------
# report ingestion: users' desktop apps POST structured JSON updates
# ------------------------------------------------------------------
async def on_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text.startswith("{"):
        return
    try:
        payload = json.loads(text)
    except Exception:
        return
    rep = load_reports()
    uid = str(payload.get("user_id", update.message.from_user.id))
    payload["last_seen"] = datetime.utcnow().isoformat()
    rep[uid] = payload
    save_reports(rep)
    await update.message.reply_text(f"✅ Report recorded for user {uid}")


# ------------------------------------------------------------------
# /start — owner welcome
# ------------------------------------------------------------------
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    fid = update.effective_user.id
    if OWNER_ID and fid != OWNER_ID:
        await update.effective_message.reply_text(
            "🚫 This bot is owner-only.")
        return
    await update.effective_message.reply_text(
        "👑 SENZO OWNER BOT is online!\n\n"
        "Commands:\n"
        "/activate \u27e8machine_id\u27e9 \u27e8name\u27e9 [days] — issue a license key\n"
        "/status — live report of all users\n"
        "/push \u27e8link\u27e9 — push a link to every user's Tasks panel\n"
        "/broadcast \u27e8msg\u27e9 — in-app announcement for all users\n"
        "/update \u27e8url\u27e9 — announce a new version\n"
        "/req \u27e8user\u27e9 \u27e8link\u27e9 — private request for one user",
        parse_mode="HTML")


# ------------------------------------------------------------------
# owner commands
# ------------------------------------------------------------------
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rep = load_reports()
    if not rep:
        await update.effective_message.reply_text(
            "📡 No reports yet. Users' apps will start sending "
            "heartbeats once they connect to the control channel.")
        return
    lines = ["👑 SENZO OWNER DASHBOARD — live", "=" * 36]
    for uid, p in rep.items():
        name = p.get("user_name", uid)
        ch = p.get("channels", [])
        lines.append(f"• {name} ({uid})")
        for c in ch:
            lines.append(f"    📥 {c.get('source','?')} → "
                         f"{c.get('cloned','0')} msgs "
                         f"({c.get('status','idle')})")
        lines.append(f"    🕐 last seen: {p.get('last_seen','?')[:16]}")
    await update.effective_message.reply_text("\n".join(lines)[:4000])


async def cmd_push(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = " ".join(ctx.args or [])
    if not args:
        await update.effective_message.reply_text(
            "Usage: /push <channel_link or id>  — adds it to every user's Tasks panel")
        return
    task = {
        "type": "push",
        "source": args,
        "ts": datetime.utcnow().isoformat(),
    }
    if CONTROL_ID:
        await ctx.bot.send_message(CONTROL_ID, json.dumps(task))
    await update.effective_message.reply_text(f"📤 Pushed to all users: {args}")


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = " ".join(ctx.args or [])
    if not args:
        await update.effective_message.reply_text(
            "Usage: /broadcast <message> — in-app announcement for all users")
        return
    msg = {"type": "broadcast", "text": args,
           "ts": datetime.utcnow().isoformat()}
    if CONTROL_ID:
        await ctx.bot.send_message(CONTROL_ID, json.dumps(msg))
    await update.effective_message.reply_text("📢 Broadcast sent to all users")


async def cmd_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = " ".join(ctx.args or [])
    if not args:
        await update.effective_message.reply_text(
            "Usage: /update <download_url> — 'Update available' banner for all")
        return
    msg = {"type": "update", "url": args,
           "version": "1.2", "ts": datetime.utcnow().isoformat()}
    if CONTROL_ID:
        await ctx.bot.send_message(CONTROL_ID, json.dumps(msg))
    await update.effective_message.reply_text(f"🔄 Update announced: {args}")


async def cmd_req(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Private request for a specific user (by username or id)."""
    args = ctx.args or []
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Usage: /req <username> <channel_link>")
        return
    who, what = args[0], " ".join(args[1:])
    req = {"type": "request", "target": who, "source": what,
           "ts": datetime.utcnow().isoformat()}
    if CONTROL_ID:
        await ctx.bot.send_message(CONTROL_ID, json.dumps(req))
    await update.effective_message.reply_text(f"📋 Request sent for {who}: {what}")


async def cmd_activate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Generate a license for a user's Machine ID and print the key text
    that the owner forwards to the user. Usage:
        /activate <machine_id> <name> [days]
    Example:  /activate SENZO-MC-a7f3c9d2e1b8 AliRaza 365
    The bot prints the key string — the owner DMs it to the user, who pastes
    it into Senzo → Activate."""
    args = ctx.args or []
    if len(args) < 2:
        await update.effective_message.reply_text(
            "Usage: /activate <machine_id> <name> [days]\n"
            "Example: /activate SENZO-MC-a7f3c9d2e1b8 AliRaza 365")
        return
    machine, name = args[0], args[1]
    days = int(args[2]) if len(args) > 2 and args[2].isdigit() else 365
    try:
        import os
        import subprocess
        out = subprocess.check_output(
            [sys.executable,
             os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "senzo_license.py"), "licprint",
             "-m", machine, "-u", name, "-d", str(days)],
            cwd=os.path.dirname(os.path.abspath(__file__))).decode().strip()
    except subprocess.CalledProcessError as e:
        await update.effective_message.reply_text(
            f"❌ License generation failed:\n{e.stderr or e.stdout}")
        return
    if not out or not out.startswith("eyJ"):
        await update.effective_message.reply_text(
            "❌ License key not generated — check senzo_license.py and the "
            "RSA keypair in licenses/")
        return
    exp = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")
    await update.effective_message.reply_text(
        f"🔑 LICENSE READY\n\n"
        f"User: {name}   Device: {machine}\n"
        f"Expires: {exp}\n\n"
        f"Key ({len(out)} chars):\n<pre>{out}</pre>\n\n"
        f"✅ Copy the key above and DM it to the user — they paste it in "
        f"Senzo → 'I HAVE A LICENSE KEY' → ACTIVATE.",
        parse_mode="HTML")
    log.info("License issued for %s / %s (%d days)", name, machine, days)


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------
def main():
    if not BOT_TOKEN:
        sys.exit("Set BOT_TOKEN in Railway Variables "
                 "(ya .env mein BOT_TOKEN=<BotFather token>)")
    if CONTROL_ID and (not CONTROL_ID.startswith("-") or not CONTROL_ID[1:].isdigit()):
        log.warning("CONTROL_ID looks wrong: %s (must be like -1001234567890)", CONTROL_ID)
    if REPORT_ID and (not REPORT_ID.startswith("-") or not REPORT_ID[1:].isdigit()):
        log.warning("REPORT_ID looks wrong: %s (must be like -1001234567890)", REPORT_ID)
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("push", cmd_push))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CommandHandler("req", cmd_req))
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, on_report))
    log.info("SENZO OWNER BOT running — dashboard commands active")
    app.run_polling()


if __name__ == "__main__":
    main()
