#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from db import Database

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------
(
    MAIN_MENU,
    WATERING_SELECT,
    ADD_NAME,
    ADD_INTERVAL,
    ADD_LAST_WATERED,
    EDIT_SELECT,
    EDIT_ACTION,
    EDIT_INTERVAL,
    EDIT_LAST_WATERED,
    CALENDAR_INPUT,
    REMINDER_MENU,
    REMINDER_TIME_INPUT,
) = range(12)

MAX_NAME_LEN = 15


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def main_menu_keyboard(reminders_on: bool = True) -> InlineKeyboardMarkup:
    bell = "🔔 Reminder" if reminders_on else "🔕 Reminder"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💧 Pflanze gegossen", callback_data="action_water")],
        [InlineKeyboardButton("📋 Übersicht",        callback_data="action_overview")],
        [
            InlineKeyboardButton("🌱 Neue Pflanze", callback_data="action_add"),
            InlineKeyboardButton("✏️ Bearbeiten",   callback_data="action_edit"),
        ],
        [InlineKeyboardButton("📅 Kalender ändern", callback_data="action_calendar")],
        [InlineKeyboardButton(bell,                  callback_data="action_reminder_menu")],
    ])


def reminder_settings_keyboard(reminders_on: bool, reminder_time: str) -> InlineKeyboardMarkup:
    toggle_label = "✅ Reminder an  →  ausschalten" if reminders_on else "❌ Reminder aus  →  einschalten"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label,              callback_data="rset_toggle")],
        [InlineKeyboardButton(f"⏰ Zeit setzen ({reminder_time})", callback_data="rset_time")],
        [InlineKeyboardButton("🔙 Zurück",               callback_data="rset_back")],
    ])


def plant_select_keyboard(plants: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(plants), 2):
        row = [InlineKeyboardButton(p, callback_data=f"plant_{p}") for p in plants[i:i+2]]
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Abbruch", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


def edit_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Intervall ändern",       callback_data="edit_interval")],
        [InlineKeyboardButton("💧 Letztes Gießen setzen", callback_data="edit_lastt")],
        [InlineKeyboardButton("🗑 Pflanze löschen",        callback_data="edit_delete")],
        [InlineKeyboardButton("❌ Abbruch",                callback_data="cancel")],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Abbruch", callback_data="cancel")]])


def reminder_msg_keyboard(due_plants: list[str], msg_id: int) -> InlineKeyboardMarkup:
    """
    Keyboard für die tägliche Reminder-Nachricht.
    Die msg_id wird in jede callback_data eingebettet, damit:
      1. Alte Nachrichten erkannt und deaktiviert werden können.
      2. Jeder Button eindeutig einer konkreten Nachricht zugeordnet ist.
    Format: "rmsg_{msg_id}_water_{plant}" / "rmsg_{msg_id}_menu"
    """
    rows = [
        [InlineKeyboardButton(f"✅ {p}", callback_data=f"rmsg_{msg_id}_water_{p}")]
        for p in due_plants
    ]
    rows.append([InlineKeyboardButton("📋 Zum Menü", callback_data=f"rmsg_{msg_id}_menu")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_overview(plants: list[tuple]) -> str:
    if not plants:
        return "Du hast noch keine Pflanzen hinzugefügt."

    header = f"{'Pflanze':<{MAX_NAME_LEN}} Int  Tage"
    sep    = "─" * len(header)
    rows   = [f"<code>{header}\n{sep}"]

    for name, interval, days_till in plants:
        display_name = name[:MAX_NAME_LEN]
        status = f"{days_till:>+4}" if days_till != 0 else "   0"
        rows.append(f"{display_name:<{MAX_NAME_LEN}} {interval:>3}  {status}")

    rows.append("</code>")
    table = "\n".join(rows)

    warn = []
    for name, _, days_till in plants:
        if days_till < 0:
            warn.append(f"🔴 {name} ({abs(days_till)}d überfällig)")
        elif days_till == 0:
            warn.append(f"🟠 {name} (heute fällig)")
        elif days_till <= 2:
            warn.append(f"🟡 {name} (in {days_till}d)")

    result = "📋 <b>Deine Pflanzen:</b>\n\n" + table
    if warn:
        result += "\n\n" + "\n".join(warn)
    return result


async def safe_edit(query, text: str, keyboard: InlineKeyboardMarkup,
                    parse_mode: str = "HTML") -> None:
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=parse_mode)
    except BadRequest as e:
        msg = str(e).lower()
        if "can't be edited" in msg or "is not modified" in msg:
            logger.warning("Nachricht konnte nicht bearbeitet werden: %s", e)
        else:
            raise


async def send_main_menu(update: Update, text: str, edit: bool = False,
                         db: Database = None) -> None:
    tgid = update.effective_user.id
    reminders_on = db.get_reminder_enabled(tgid) if db else True
    keyboard = main_menu_keyboard(reminders_on)
    if edit and update.callback_query:
        await safe_edit(update.callback_query, text, keyboard)
    else:
        msg = update.message or update.callback_query.message
        await msg.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def disable_old_reminders(context: ContextTypes.DEFAULT_TYPE, tgid: int) -> None:
    """
    Deaktiviert alle noch aktiven Reminder-Nachrichten des Users,
    indem das Keyboard entfernt wird. Die message_ids werden in
    bot_data["active_reminders"][tgid] gespeichert.
    """
    active = context.bot_data.setdefault("active_reminders", {})
    old_ids = active.pop(tgid, [])
    for chat_id, msg_id in old_ids:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=msg_id, reply_markup=None
            )
        except BadRequest:
            pass  # Nachricht zu alt oder bereits bearbeitet


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]

    is_new = db.ensure_user(tgid)
    if is_new:
        await update.message.reply_text(
            "🌿 Willkommen beim <b>WasserWächter</b>!\n"
            "Ich erinnere dich daran, deine Pflanzen zu gießen.\n\n"
            "<i>Tipp: Falls das Menü mal nicht reagiert, schreibe einfach /start.</i>",
            parse_mode="HTML",
        )
    await send_main_menu(update, "Was möchtest du tun?", db=db)
    return MAIN_MENU


# ---------------------------------------------------------------------------
# Main menu dispatcher
# ---------------------------------------------------------------------------

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    action = query.data

    if action == "action_overview":
        plants = db.get_plants_with_status(tgid)
        await safe_edit(query, format_overview(plants),
                        main_menu_keyboard(db.get_reminder_enabled(tgid)))
        return MAIN_MENU

    elif action == "action_water":
        plants = db.get_plant_names(tgid)
        if not plants:
            await safe_edit(query, "Du hast noch keine Pflanzen. Füge zuerst eine hinzu.",
                            main_menu_keyboard(db.get_reminder_enabled(tgid)))
            return MAIN_MENU
        await safe_edit(query, "💧 Welche Pflanze wurde gegossen?", plant_select_keyboard(plants))
        return WATERING_SELECT

    elif action == "action_add":
        await safe_edit(
            query,
            f"🌱 Wie soll die Pflanze heißen? (max. {MAX_NAME_LEN} Zeichen)\n\nEinfach eintippen:",
            cancel_keyboard(),
        )
        return ADD_NAME

    elif action == "action_edit":
        plants = db.get_plant_names(tgid)
        if not plants:
            await safe_edit(query, "Du hast noch keine Pflanzen.",
                            main_menu_keyboard(db.get_reminder_enabled(tgid)))
            return MAIN_MENU
        await safe_edit(query, "✏️ Welche Pflanze möchtest du bearbeiten?",
                        plant_select_keyboard(plants))
        return EDIT_SELECT

    elif action == "action_calendar":
        calendar_id = db.get_calendar_id(tgid)
        await safe_edit(
            query,
            f"📅 <b>Kalender-Einstellungen</b>\n\n"
            f"Deine Telegram-ID: <code>{tgid}</code>\n"
            f"Aktuelle Kalender-ID: <code>{calendar_id}</code>\n\n"
            f"Möchtest du den Kalender einer anderen Person nutzen?\n"
            f"Tippe deren Telegram-ID ein, oder drücke Abbruch:",
            cancel_keyboard(),
        )
        return CALENDAR_INPUT

    elif action == "action_reminder_menu":
        enabled = db.get_reminder_enabled(tgid)
        rtime   = db.get_reminder_time(tgid)
        await safe_edit(
            query,
            "🔔 <b>Reminder-Einstellungen</b>",
            reminder_settings_keyboard(enabled, rtime),
        )
        return REMINDER_MENU

    return MAIN_MENU


# ---------------------------------------------------------------------------
# Reminder settings submenu
# ---------------------------------------------------------------------------

async def reminder_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]

    if query.data == "rset_back":
        await send_main_menu(update, "Was möchtest du tun?", edit=True, db=db)
        return MAIN_MENU

    elif query.data == "rset_toggle":
        current = db.get_reminder_enabled(tgid)
        db.set_reminder_enabled(tgid, not current)
        rtime = db.get_reminder_time(tgid)
        await safe_edit(
            query,
            "🔔 <b>Reminder-Einstellungen</b>",
            reminder_settings_keyboard(not current, rtime),
        )
        return REMINDER_MENU

    elif query.data == "rset_time":
        await safe_edit(
            query,
            "⏰ <b>Reminder-Zeit setzen</b>\n\n"
            "Gib die gewünschte Uhrzeit im Format <code>HHMM</code> ein.\n"
            "Beispiele: <code>0800</code> = 08:00, <code>2030</code> = 20:30",
            cancel_keyboard(),
        )
        return REMINDER_TIME_INPUT

    return REMINDER_MENU


async def reminder_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        tgid = update.effective_user.id
        db: Database = context.bot_data["db"]
        enabled = db.get_reminder_enabled(tgid)
        rtime   = db.get_reminder_time(tgid)
        await safe_edit(query, "🔔 <b>Reminder-Einstellungen</b>",
                        reminder_settings_keyboard(enabled, rtime))
        return REMINDER_MENU

    text = update.message.text.strip()

    # Validierung: genau 4 Ziffern, gültige Uhrzeit
    if not (len(text) == 4 and text.isnumeric()):
        await update.message.reply_text(
            "❌ Bitte genau 4 Ziffern eingeben, z.B. <code>0800</code>:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return REMINDER_TIME_INPUT

    hh, mm = int(text[:2]), int(text[2:])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        await update.message.reply_text(
            "❌ Ungültige Uhrzeit. Bitte erneut eingeben, z.B. <code>0800</code>:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML",
        )
        return REMINDER_TIME_INPUT

    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    time_str = f"{hh:02d}:{mm:02d}"
    db.set_reminder_time(tgid, time_str)

    # Job neu planen
    _schedule_reminder(context.application, tgid, hh, mm)

    enabled = db.get_reminder_enabled(tgid)
    await update.message.reply_text(
        f"✅ Reminder-Zeit gesetzt auf <b>{time_str}</b>.",
        reply_markup=reminder_settings_keyboard(enabled, time_str),
        parse_mode="HTML",
    )
    return REMINDER_MENU


# ---------------------------------------------------------------------------
# Watering (from main menu)
# ---------------------------------------------------------------------------

async def watering_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]

    if query.data == "cancel":
        await send_main_menu(update, "Abgebrochen.", edit=True, db=db)
        return MAIN_MENU

    plant = query.data.removeprefix("plant_")
    db.water_plant(tgid, plant)
    await safe_edit(
        query,
        f"✅ <b>{plant}</b> wurde heute gegossen!",
        main_menu_keyboard(db.get_reminder_enabled(tgid)),
    )
    return MAIN_MENU


# ---------------------------------------------------------------------------
# Reminder message callback – läuft AUSSERHALB des ConversationHandlers.
# Pattern: "rmsg_{msg_id}_water_{plant}" oder "rmsg_{msg_id}_menu"
# Die msg_id stellt sicher dass nur die aktuellste Reminder-Nachricht
# aktiv ist. Alte Nachrichten werden beim nächsten Reminder deaktiviert.
# ---------------------------------------------------------------------------

async def reminder_msg_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tgid  = update.effective_user.id
    db: Database = context.bot_data["db"]

    # callback_data parsen: "rmsg_{msg_id}_water_{plant}" oder "rmsg_{msg_id}_menu"
    parts    = query.data.split("_", 3)   # ["rmsg", msg_id, "water"/"menu", plant?]
    msg_id   = int(parts[1])
    action   = parts[2]

    # Prüfen ob diese Nachricht noch die aktive Reminder-Nachricht ist
    active = context.bot_data.get("active_reminders", {})
    active_entries = active.get(tgid, [])
    active_msg_ids = [mid for _, mid in active_entries]

    if msg_id not in active_msg_ids:
        # Alte Nachricht – Keyboard entfernen und ignorieren
        await query.answer("Diese Erinnerung ist nicht mehr aktiv.", show_alert=False)
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        return

    await query.answer()

    if action == "menu":
        # Keyboard der Reminder-Nachricht entfernen
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        active.get(tgid, []).clear()
        # Neues Menü als eigene Nachricht senden
        await query.message.reply_text(
            "Was möchtest du tun?",
            reply_markup=main_menu_keyboard(db.get_reminder_enabled(tgid)),
        )
        return

    # action == "water"
    plant = parts[3]
    db.water_plant(tgid, plant)

    # Pflanze aus dem Keyboard entfernen
    current_kb = query.message.reply_markup
    new_rows = []
    for row in current_kb.inline_keyboard:
        filtered = [btn for btn in row if btn.callback_data != query.data]
        if filtered:
            new_rows.append(filtered)

    remaining_plants = [
        btn for row in new_rows for btn in row
        if "_water_" in btn.callback_data
    ]

    if not remaining_plants:
        # Alle gegossen
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except BadRequest:
            pass
        active.get(tgid, []).clear()
        await query.message.reply_text(
            "✅ Alle Pflanzen gegossen!",
            reply_markup=main_menu_keyboard(db.get_reminder_enabled(tgid)),
        )
    else:
        try:
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(new_rows)
            )
        except BadRequest as e:
            logger.warning("Reminder-Keyboard konnte nicht bearbeitet werden: %s", e)


# ---------------------------------------------------------------------------
# Add plant
# ---------------------------------------------------------------------------

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await send_main_menu(update, "Abgebrochen.", edit=True, db=context.bot_data["db"])
        return MAIN_MENU

    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    name = update.message.text.strip()

    if len(name) > MAX_NAME_LEN:
        await update.message.reply_text(
            f"❌ Der Name hat {len(name)} Zeichen (max. {MAX_NAME_LEN}). Bitte kürzen:",
            reply_markup=cancel_keyboard(),
        )
        return ADD_NAME

    if db.plant_exists(tgid, name):
        await update.message.reply_text(
            "❌ Eine Pflanze mit diesem Namen existiert bereits.",
            reply_markup=cancel_keyboard(),
        )
        return ADD_NAME

    context.user_data["new_plant_name"] = name
    await update.message.reply_text(
        f"Alle wie vielen Tage soll ich dich erinnern, <b>{name}</b> zu gießen?",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    return ADD_INTERVAL


async def add_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data.pop("new_plant_name", None)
        await send_main_menu(update, "Abgebrochen.", edit=True, db=context.bot_data["db"])
        return MAIN_MENU

    text = update.message.text.strip()
    if not text.isnumeric() or int(text) <= 0:
        await update.message.reply_text(
            "❌ Bitte eine positive ganze Zahl eingeben:",
            reply_markup=cancel_keyboard(),
        )
        return ADD_INTERVAL

    context.user_data["new_plant_interval"] = int(text)
    await update.message.reply_text(
        "Vor wie vielen Tagen hast du diese Pflanze zuletzt gegossen? (0 = heute)",
        reply_markup=cancel_keyboard(),
    )
    return ADD_LAST_WATERED


async def add_last_watered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data.pop("new_plant_name", None)
        context.user_data.pop("new_plant_interval", None)
        await send_main_menu(update, "Abgebrochen.", edit=True, db=context.bot_data["db"])
        return MAIN_MENU

    text = update.message.text.strip()
    if not text.isnumeric():
        await update.message.reply_text(
            "❌ Bitte eine Zahl eingeben (0 = heute):",
            reply_markup=cancel_keyboard(),
        )
        return ADD_LAST_WATERED

    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    name     = context.user_data.pop("new_plant_name")
    interval = context.user_data.pop("new_plant_interval")
    lastt    = datetime.date.today().toordinal() - int(text)

    db.add_plant(tgid, name, interval, lastt)
    await update.message.reply_text(
        f"✅ <b>{name}</b> wurde hinzugefügt!",
        reply_markup=main_menu_keyboard(db.get_reminder_enabled(tgid)),
        parse_mode="HTML",
    )
    return MAIN_MENU


# ---------------------------------------------------------------------------
# Edit plant
# ---------------------------------------------------------------------------

async def edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await send_main_menu(update, "Abgebrochen.", edit=True, db=context.bot_data["db"])
        return MAIN_MENU

    plant = query.data.removeprefix("plant_")
    context.user_data["edit_plant"] = plant
    await safe_edit(query, f"✏️ Was möchtest du bei <b>{plant}</b> ändern?",
                    edit_action_keyboard())
    return EDIT_ACTION


async def edit_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]

    if query.data == "cancel":
        context.user_data.pop("edit_plant", None)
        await send_main_menu(update, "Abgebrochen.", edit=True, db=db)
        return MAIN_MENU

    plant = context.user_data.get("edit_plant")

    if query.data == "edit_delete":
        db.delete_plant(tgid, plant)
        context.user_data.pop("edit_plant", None)
        await safe_edit(query, f"🗑 <b>{plant}</b> wurde gelöscht.",
                        main_menu_keyboard(db.get_reminder_enabled(tgid)))
        return MAIN_MENU

    elif query.data == "edit_interval":
        await safe_edit(
            query,
            f"⏱ Alle wie vielen Tage soll ich dich erinnern, <b>{plant}</b> zu gießen?",
            cancel_keyboard(),
        )
        return EDIT_INTERVAL

    elif query.data == "edit_lastt":
        await safe_edit(
            query,
            f"💧 Vor wie vielen Tagen hast du <b>{plant}</b> zuletzt gegossen? (0 = heute)",
            cancel_keyboard(),
        )
        return EDIT_LAST_WATERED

    return EDIT_ACTION


async def edit_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data.pop("edit_plant", None)
        await send_main_menu(update, "Abgebrochen.", edit=True, db=context.bot_data["db"])
        return MAIN_MENU

    text = update.message.text.strip()
    if not text.isnumeric() or int(text) <= 0:
        await update.message.reply_text(
            "❌ Bitte eine positive ganze Zahl eingeben:",
            reply_markup=cancel_keyboard(),
        )
        return EDIT_INTERVAL

    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    plant = context.user_data.pop("edit_plant")
    db.update_interval(tgid, plant, int(text))
    await update.message.reply_text(
        f"✅ Ich erinnere dich jetzt alle <b>{text} Tage</b> daran, {plant} zu gießen.",
        reply_markup=main_menu_keyboard(db.get_reminder_enabled(tgid)),
        parse_mode="HTML",
    )
    return MAIN_MENU


async def edit_last_watered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        context.user_data.pop("edit_plant", None)
        await send_main_menu(update, "Abgebrochen.", edit=True, db=context.bot_data["db"])
        return MAIN_MENU

    text = update.message.text.strip()
    if not text.isnumeric():
        await update.message.reply_text(
            "❌ Bitte eine Zahl eingeben (0 = heute):",
            reply_markup=cancel_keyboard(),
        )
        return EDIT_LAST_WATERED

    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    plant = context.user_data.pop("edit_plant")
    lastt = datetime.date.today().toordinal() - int(text)
    db.update_last_watered(tgid, plant, lastt)
    await update.message.reply_text(
        f"✅ Letztes Gießen für <b>{plant}</b> aktualisiert.",
        reply_markup=main_menu_keyboard(db.get_reminder_enabled(tgid)),
        parse_mode="HTML",
    )
    return MAIN_MENU


# ---------------------------------------------------------------------------
# Calendar sharing
# ---------------------------------------------------------------------------

async def calendar_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await send_main_menu(update, "Abgebrochen.", edit=True, db=context.bot_data["db"])
        return MAIN_MENU

    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    other_id = update.message.text.strip()

    if not other_id.lstrip("-").isnumeric():
        await update.message.reply_text(
            "❌ Ungültige ID. Bitte eine Telegram-ID eingeben:",
            reply_markup=cancel_keyboard(),
        )
        return CALENDAR_INPUT

    if not db.user_exists(int(other_id)):
        await update.message.reply_text(
            "❌ Kein Nutzer mit dieser ID gefunden.",
            reply_markup=cancel_keyboard(),
        )
        return CALENDAR_INPUT

    db.set_calendar(tgid, int(other_id))
    await update.message.reply_text(
        f"✅ Du siehst jetzt den Kalender von <code>{other_id}</code>.",
        reply_markup=main_menu_keyboard(db.get_reminder_enabled(tgid)),
        parse_mode="HTML",
    )
    return MAIN_MENU


# ---------------------------------------------------------------------------
# Cancel fallback
# ---------------------------------------------------------------------------

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await send_main_menu(update, "Abgebrochen.", db=context.bot_data["db"])
    return MAIN_MENU


# ---------------------------------------------------------------------------
# Reminder job scheduling
# ---------------------------------------------------------------------------

def _schedule_reminder(app: Application, tgid: int, hour: int, minute: int) -> None:
    """Plant den täglichen Reminder-Job für einen User neu."""
    import pytz
    tz       = pytz.timezone("Europe/Berlin")
    job_name = f"reminder_{tgid}"

    # Alten Job entfernen falls vorhanden
    current_jobs = app.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    run_time = datetime.time(hour, minute, 0, tzinfo=tz)
    app.job_queue.run_daily(
        reminder_job,
        run_time,
        name=job_name,
        data={"tgid": tgid},
    )
    logger.info("Reminder für User %s geplant um %02d:%02d", tgid, hour, minute)


# States in denen ein laufender Vorgang unterbrochen werden soll
INTERRUPTIBLE_STATES = {
    WATERING_SELECT,
    ADD_NAME, ADD_INTERVAL, ADD_LAST_WATERED,
    EDIT_SELECT, EDIT_ACTION, EDIT_INTERVAL, EDIT_LAST_WATERED,
    CALENDAR_INPUT, REMINDER_MENU, REMINDER_TIME_INPUT,
}


async def interrupt_conversation(context: ContextTypes.DEFAULT_TYPE,
                                  conv_handler: ConversationHandler,
                                  tgid: int) -> bool:
    """
    Setzt den ConversationHandler-State des Users zurück falls er sich
    in einem unterbrechbaren Vorgang befindet.
    Gibt True zurück wenn ein Vorgang unterbrochen wurde.
    """
    # PTB speichert States in application.chat_data unter einem internen Key.
    # Der Key ist ein Tuple aus den Namen der Entry-Point-Handler des ConvHandlers.
    conv_key = conv_handler.name
    chat_data = context.application.chat_data.get(tgid, {})

    current_state = None
    for key, val in chat_data.items():
        if isinstance(key, str) and key == conv_key:
            current_state = val
            break

    # Alternativer Zugriff über _conversation_key
    if current_state is None:
        state_map = conv_handler._conversations
        current_state = state_map.get((tgid, tgid))

    if current_state in INTERRUPTIBLE_STATES:
        # State löschen → ConvHandler nimmt beim nächsten Update den Entry-Point
        conv_handler._conversations.pop((tgid, tgid), None)
        # user_data bereinigen
        if tgid in context.application.user_data:
            context.application.user_data[tgid].clear()
        logger.info("Laufender Vorgang von User %s unterbrochen (State %s)", tgid, current_state)
        return True
    return False


async def reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Wird entweder mit context.job.data["tgid"] (user-spezifisch)
    oder ohne data (globaler Fallback-Job) aufgerufen.
    """
    db: Database = context.bot_data["db"]
    today        = datetime.date.today().toordinal()
    active       = context.bot_data.setdefault("active_reminders", {})

    # ConversationHandler-Referenz für State-Reset
    conv_handler = context.bot_data.get("conv_handler")

    # Bestimmen welche User dieser Job-Aufruf betrifft
    job_data = context.job.data if context.job.data else {}
    specific_tgid = job_data.get("tgid")

    if specific_tgid:
        users_to_remind = [
            (r[0], r[1], r[2])
            for r in db.get_all_users()
            if r[0] == specific_tgid
        ]
    else:
        users_to_remind = db.get_all_users()

    for tgid, calendar_id, reminder_enabled in users_to_remind:
        if not reminder_enabled:
            continue
        due = db.get_due_plants(calendar_id, today)
        if not due:
            continue

        # Alte Reminder-Nachrichten dieses Users deaktivieren
        old_ids = active.pop(tgid, [])
        for chat_id, msg_id in old_ids:
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=msg_id, reply_markup=None
                )
            except BadRequest:
                pass

        # Laufenden Vorgang unterbrechen falls nötig
        interrupted = False
        if conv_handler:
            interrupted = await interrupt_conversation(context, conv_handler, tgid)

        try:
            # Unterbrechungshinweis + Reminder in einer Nachricht
            text = "💧 <b>Heute gießen:</b>"
            if interrupted:
                text = "⚠️ <i>Dein laufender Vorgang wurde unterbrochen.</i>\n\n" + text

            sent = await context.bot.send_message(
                tgid,
                text,
                parse_mode="HTML",
                reply_markup=reminder_msg_keyboard(due, 0),
            )
            await sent.edit_reply_markup(
                reply_markup=reminder_msg_keyboard(due, sent.message_id)
            )
            active.setdefault(tgid, []).append((tgid, sent.message_id))
            logger.info("Reminder gesendet an %s (msg_id=%s)", tgid, sent.message_id)
        except Exception as e:
            logger.warning("Reminder für %s fehlgeschlagen: %s", tgid, e)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram.error import Conflict, NetworkError
    err = context.error

    if isinstance(err, Conflict):
        logger.error("Konflikt: Nur eine Bot-Instanz gleichzeitig starten!")
        return
    if isinstance(err, NetworkError):
        logger.warning("Netzwerkfehler (wird automatisch wiederholt): %s", err)
        return

    logger.exception("Unbehandelter Fehler bei Update %s:", update, exc_info=err)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Es ist ein Fehler aufgetreten. Bitte starte mit /start neu."
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import pytz

    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Umgebungsvariable BOT_TOKEN ist nicht gesetzt!")

    db_path = os.environ.get("DB_PATH", "/data/Pflanzendaten.db")
    db      = Database(db_path)

    app = Application.builder().token(token).build()
    app.bot_data["db"]              = db
    app.bot_data["active_reminders"] = {}

    # Individuelle Reminder-Jobs für alle User anlegen
    import pytz
    tz = pytz.timezone("Europe/Berlin")
    for tgid, _, reminder_enabled in db.get_all_users():
        if not reminder_enabled:
            continue
        rtime = db.get_reminder_time(tgid)   # "HH:MM"
        hh, mm = map(int, rtime.split(":"))
        run_time = datetime.time(hh, mm, 0, tzinfo=tz)
        app.job_queue.run_daily(
            reminder_job,
            run_time,
            name=f"reminder_{tgid}",
            data={"tgid": tgid},
        )

    # Negatives Lookahead: rmsg_-Callbacks werden NICHT vom ConversationHandler
    # abgefangen, sondern vom externen reminder_msg_callback behandelt.
    NOT_RMSG = r"^(?!rmsg_)"

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler, pattern=NOT_RMSG),
            ],
            REMINDER_MENU: [
                CallbackQueryHandler(reminder_menu_handler, pattern=NOT_RMSG),
            ],
            REMINDER_TIME_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time_input),
                CallbackQueryHandler(reminder_time_input, pattern=NOT_RMSG),
            ],
            WATERING_SELECT: [
                CallbackQueryHandler(watering_select, pattern=NOT_RMSG),
            ],
            ADD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_name),
                CallbackQueryHandler(add_name, pattern=NOT_RMSG),
            ],
            ADD_INTERVAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_interval),
                CallbackQueryHandler(add_interval, pattern=NOT_RMSG),
            ],
            ADD_LAST_WATERED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_last_watered),
                CallbackQueryHandler(add_last_watered, pattern=NOT_RMSG),
            ],
            EDIT_SELECT: [
                CallbackQueryHandler(edit_select, pattern=NOT_RMSG),
            ],
            EDIT_ACTION: [
                CallbackQueryHandler(edit_action, pattern=NOT_RMSG),
            ],
            EDIT_INTERVAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_interval),
                CallbackQueryHandler(edit_interval, pattern=NOT_RMSG),
            ],
            EDIT_LAST_WATERED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_last_watered),
                CallbackQueryHandler(edit_last_watered, pattern=NOT_RMSG),
            ],
            CALENDAR_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calendar_input),
                CallbackQueryHandler(calendar_input, pattern=NOT_RMSG),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )

    # ConvHandler in bot_data speichern damit reminder_job darauf zugreifen kann
    app.bot_data["conv_handler"] = conv
    app.add_handler(conv)
    # Reminder-Callbacks laufen komplett außerhalb des ConversationHandlers –
    # kein State-Konflikt möglich, funktioniert unabhängig vom Dialog-State.
    app.add_handler(CallbackQueryHandler(reminder_msg_callback, pattern=r"^rmsg_"))
    app.add_error_handler(error_handler)

    logger.info("WasserWächter gestartet.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
