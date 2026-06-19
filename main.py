#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import datetime
import html
import logging
import os
from functools import wraps

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from db import Database
from translations import SUPPORTED_LANGUAGES, get_text

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

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
    EDIT_RENAME,
    CALENDAR_INPUT,
    REMINDER_MENU,
    REMINDER_TIME_INPUT,
) = range(13)

MAX_NAME_LEN = 15
MANAGED_DIALOG_KEYS = {
    "dialog_message_ids",
    "new_plant_name",
    "new_plant_interval",
    "edit_plant_id",
    "edit_plant_name",
}


# ---------------------------------------------------------------------------
# Keyboards and formatting
# ---------------------------------------------------------------------------

def main_menu_keyboard(reminders_on: bool = True, language: str = "de") -> InlineKeyboardMarkup:
    bell_key = "menu_reminder_on" if reminders_on else "menu_reminder_off"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(language, "menu_overview"), callback_data="action_overview")],
        [
            InlineKeyboardButton(get_text(language, "menu_watered"), callback_data="action_water"),
            InlineKeyboardButton(get_text(language, "menu_today"), callback_data="action_today"),
        ],
        [
            InlineKeyboardButton(get_text(language, "menu_add"), callback_data="action_add"),
            InlineKeyboardButton(get_text(language, "menu_edit"), callback_data="action_edit"),
        ],
        [
            InlineKeyboardButton(get_text(language, "menu_share"), callback_data="action_calendar"),
            InlineKeyboardButton(get_text(language, bell_key), callback_data="action_reminder_menu"),
        ],
    ])


def reminder_settings_keyboard(reminders_on: bool, reminder_time: str,
                               language: str = "de") -> InlineKeyboardMarkup:
    toggle_key = "reminder_toggle_on" if reminders_on else "reminder_toggle_off"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(language, toggle_key), callback_data="rset_toggle")],
        [InlineKeyboardButton(get_text(language, "reminder_time_button", time=reminder_time), callback_data="rset_time")],
        [InlineKeyboardButton(get_text(language, "back"), callback_data="rset_back")],
    ])


def plant_select_keyboard(plants: list[tuple[int, str]], language: str = "de") -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(plants), 2):
        rows.append([
            InlineKeyboardButton(name, callback_data=f"plant_{plant_id}")
            for plant_id, name in plants[i:i + 2]
        ])
    rows.append([InlineKeyboardButton(get_text(language, "cancel"), callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


def edit_action_keyboard(language: str = "de") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(language, "edit_interval"), callback_data="edit_interval")],
        [InlineKeyboardButton(get_text(language, "edit_last_watered"), callback_data="edit_lastt")],
        [InlineKeyboardButton(get_text(language, "edit_rename"), callback_data="edit_rename")],
        [InlineKeyboardButton(get_text(language, "edit_delete"), callback_data="edit_delete")],
        [InlineKeyboardButton(get_text(language, "cancel"), callback_data="cancel")],
    ])


def cancel_keyboard(language: str = "de") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(get_text(language, "cancel"), callback_data="cancel")
    ]])


def help_keyboard(language: str = "de") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(language, "help_start"), callback_data="action_help_start")]
    ])


def help_text(language: str = "de") -> str:
    return get_text(language, "help")


def today_keyboard(plants: list[tuple[int, str]], language: str = "de") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"✅ {name}", callback_data=f"today_water_{plant_id}")]
        for plant_id, name in plants
    ]
    rows.append([InlineKeyboardButton(get_text(language, "today_back"), callback_data="today_menu")])
    return InlineKeyboardMarkup(rows)


def format_overview(plants: list[tuple[str, int, int]], language: str = "de") -> str:
    if not plants:
        return get_text(language, "no_plants")

    header = get_text(language, "overview_columns")
    lines = [header, "─" * len(header)]
    warnings = []
    for name, interval, days_till in plants:
        display_name = html.escape(name[:MAX_NAME_LEN])
        status = f"{days_till:>+4}" if days_till else "   0"
        lines.append(f"{display_name:<{MAX_NAME_LEN}} {interval:>3}  {status}")
        safe_name = html.escape(name)
        if days_till < 0:
            warnings.append(get_text(language, "overdue", name=safe_name, days=abs(days_till)))
        elif days_till == 0:
            warnings.append(get_text(language, "due_today", name=safe_name))
        elif days_till <= 2:
            warnings.append(get_text(language, "due_in", name=safe_name, days=days_till))

    result = get_text(language, "overview_title") + "\n\n<code>" + "\n".join(lines) + "</code>"
    if warnings:
        result += "\n\n" + "\n".join(warnings)
    return result


# ---------------------------------------------------------------------------
# Central message lifecycle
# ---------------------------------------------------------------------------

def bot_language(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.bot_data.get("language", "de")


def tr(context: ContextTypes.DEFAULT_TYPE, key: str, **values) -> str:
    return get_text(bot_language(context), key, **values)


def user_lock(context: ContextTypes.DEFAULT_TYPE, tgid: int) -> asyncio.Lock:
    locks = context.bot_data.setdefault("user_locks", {})
    return locks.setdefault(tgid, asyncio.Lock())


def locked_handler(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with user_lock(context, update.effective_user.id):
            return await handler(update, context)
    return wrapper


async def best_effort_remove_message(context: ContextTypes.DEFAULT_TYPE,
                                     chat_id: int, message_id: int) -> None:
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        return
    except TelegramError as exc:
        logger.info("Nachricht %s konnte nicht gelöscht werden: %s", message_id, exc)
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None
        )
    except TelegramError:
        pass


async def edit_or_replace_view(context: ContextTypes.DEFAULT_TYPE, tgid: int,
                               text: str, keyboard: InlineKeyboardMarkup,
                               query=None, force_new: bool = False) -> int:
    db: Database = context.bot_data["db"]
    current_id = db.get_current_message_id(tgid)

    if query and not force_new and (current_id is None or query.message.message_id == current_id):
        try:
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
            db.set_current_message_id(tgid, query.message.message_id)
            return query.message.message_id
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                db.set_current_message_id(tgid, query.message.message_id)
                return query.message.message_id
            logger.info("Ansicht wird nach fehlgeschlagenem Edit ersetzt: %s", exc)

    if current_id is not None:
        await best_effort_remove_message(context, tgid, current_id)
        db.set_current_message_id(tgid, None)
    sent = await context.bot.send_message(
        chat_id=tgid, text=text, reply_markup=keyboard, parse_mode="HTML"
    )
    db.set_current_message_id(tgid, sent.message_id)
    return sent.message_id


async def show_main_menu(context: ContextTypes.DEFAULT_TYPE, tgid: int,
                         text: str | None = None, query=None,
                         force_new: bool = False) -> int:
    db: Database = context.bot_data["db"]
    if text is None:
        text = tr(context, "main_prompt")
    return await edit_or_replace_view(
        context,
        tgid,
        text,
        main_menu_keyboard(db.get_reminder_enabled(tgid), bot_language(context)),
        query=query,
        force_new=force_new,
    )


async def show_today(context: ContextTypes.DEFAULT_TYPE, tgid: int, query=None,
                     force_new: bool = False, interrupted: bool = False) -> int:
    db: Database = context.bot_data["db"]
    due = db.get_due_plants(tgid, datetime.date.today().toordinal())
    if not due:
        return await show_main_menu(
            context, tgid, tr(context, "nothing_due"), query=query
        )
    text = tr(context, "today_title")
    if interrupted:
        text = tr(context, "interrupted") + "\n\n" + text
    return await edit_or_replace_view(
        context, tgid, text, today_keyboard(due, bot_language(context)),
        query=query, force_new=force_new
    )


# ---------------------------------------------------------------------------
# Managed add/edit dialog cleanup
# ---------------------------------------------------------------------------

def begin_managed_dialog(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    context.user_data["dialog_message_ids"] = {message_id}


def track_message(context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    context.user_data.setdefault("dialog_message_ids", set()).add(message_id)


async def tracked_reply(update: Update, context: ContextTypes.DEFAULT_TYPE,
                        text: str, keyboard: InlineKeyboardMarkup = None,
                        parse_mode: str | None = "HTML"):
    sent = await update.effective_message.reply_text(
        text, reply_markup=keyboard, parse_mode=parse_mode
    )
    track_message(context, sent.message_id)
    return sent


async def cleanup_managed_dialog(context: ContextTypes.DEFAULT_TYPE, tgid: int) -> None:
    user_data = context.application.user_data.get(tgid)
    if user_data is None:
        return
    ids = set(user_data.get("dialog_message_ids", set()))
    for message_id in ids:
        await best_effort_remove_message(context, tgid, message_id)
    for key in MANAGED_DIALOG_KEYS:
        user_data.pop(key, None)


async def finish_managed_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                text: str) -> int:
    tgid = update.effective_user.id
    await cleanup_managed_dialog(context, tgid)
    await show_main_menu(context, tgid, text, force_new=True)
    return MAIN_MENU


def valid_name(name: str) -> bool:
    return bool(name) and len(name) <= MAX_NAME_LEN


# ---------------------------------------------------------------------------
# Start, recovery and main menu
# ---------------------------------------------------------------------------

async def recovery_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    tgid = user.id
    db: Database = context.bot_data["db"]
    recovered = context.bot_data.setdefault("recovered_users", set())
    if tgid in recovered or not db.user_exists(tgid):
        return

    if update.callback_query:
        await update.callback_query.answer()
        await best_effort_remove_message(
            context, tgid, update.callback_query.message.message_id
        )
    elif update.effective_message:
        await best_effort_remove_message(context, tgid, update.effective_message.message_id)

    async with user_lock(context, tgid):
        await show_main_menu(context, tgid, force_new=True)
        recovered.add(tgid)
    raise ApplicationHandlerStop


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    is_new = db.ensure_user(tgid)
    context.bot_data.setdefault("recovered_users", set()).add(tgid)
    if is_new:
        _schedule_from_database(context.application, db, tgid)
        await update.message.reply_text(
            tr(context, "welcome"),
            parse_mode="HTML",
        )
        await edit_or_replace_view(
            context, tgid, help_text(bot_language(context)),
            help_keyboard(bot_language(context)), force_new=True
        )
    else:
        await show_main_menu(context, tgid, force_new=True)
    return MAIN_MENU


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    if not db.user_exists(tgid):
        db.ensure_user(tgid)
        _schedule_from_database(context.application, db, tgid)
    context.bot_data.setdefault("recovered_users", set()).add(tgid)
    async with user_lock(context, tgid):
        await cleanup_managed_dialog(context, tgid)
        await edit_or_replace_view(
            context, tgid, help_text(bot_language(context)),
            help_keyboard(bot_language(context)), force_new=True
        )
    return MAIN_MENU


@locked_handler
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    action = query.data

    if action == "action_help_start":
        await show_main_menu(context, tgid, query=query)
    elif action == "action_overview":
        await show_main_menu(
            context, tgid,
            format_overview(db.get_plants_with_status(tgid), bot_language(context)), query
        )
    elif action == "action_today":
        await show_today(context, tgid, query=query)
    elif action == "action_water":
        plants = db.get_plants(tgid)
        if not plants:
            await show_main_menu(context, tgid, tr(context, "no_plants"), query)
        else:
            await edit_or_replace_view(
                context, tgid, tr(context, "water_select"),
                plant_select_keyboard(plants, bot_language(context)), query
            )
            return WATERING_SELECT
    elif action == "action_add":
        begin_managed_dialog(context, query.message.message_id)
        await edit_or_replace_view(
            context, tgid,
            tr(context, "add_name_prompt", max_len=MAX_NAME_LEN),
            cancel_keyboard(bot_language(context)), query
        )
        return ADD_NAME
    elif action == "action_edit":
        plants = db.get_plants(tgid)
        if not plants:
            await show_main_menu(context, tgid, tr(context, "no_plants"), query)
        else:
            begin_managed_dialog(context, query.message.message_id)
            await edit_or_replace_view(
                context, tgid, tr(context, "edit_select"),
                plant_select_keyboard(plants, bot_language(context)), query
            )
            return EDIT_SELECT
    elif action == "action_calendar":
        calendar_id = db.get_calendar_id(tgid)
        await edit_or_replace_view(
            context, tgid, tr(
                context, "share_prompt", tgid=tgid, calendar_id=calendar_id
            ), cancel_keyboard(bot_language(context)), query
        )
        return CALENDAR_INPUT
    elif action == "action_reminder_menu":
        await edit_or_replace_view(
            context, tgid, tr(context, "reminder_settings"),
            reminder_settings_keyboard(
                db.get_reminder_enabled(tgid), db.get_reminder_time(tgid),
                bot_language(context)
            ), query
        )
        return REMINDER_MENU
    return MAIN_MENU


@locked_handler
async def watering_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    if query.data == "cancel":
        await show_main_menu(context, tgid, tr(context, "aborted"), query)
        return MAIN_MENU
    plant_id = int(query.data.removeprefix("plant_"))
    name = db.get_plant_name(tgid, plant_id)
    if not name or not db.water_plant(tgid, plant_id):
        await show_main_menu(context, tgid, tr(context, "unavailable"), query)
    else:
        await show_main_menu(
            context, tgid, tr(context, "watered", name=html.escape(name)), query
        )
    return MAIN_MENU


async def today_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    async with user_lock(context, tgid):
        current_id = db.get_current_message_id(tgid)
        if current_id != query.message.message_id:
            await query.answer(tr(context, "stale_message"))
            await best_effort_remove_message(context, tgid, query.message.message_id)
            return
        await query.answer()
        if query.data == "today_menu":
            await show_main_menu(context, tgid, query=query)
            return
        plant_id = int(query.data.removeprefix("today_water_"))
        if not db.water_plant(tgid, plant_id):
            await show_main_menu(context, tgid, tr(context, "unavailable"), query)
            return
        due = db.get_due_plants(tgid, datetime.date.today().toordinal())
        if due:
            await show_today(context, tgid, query=query)
        else:
            await show_main_menu(
                context, tgid, tr(context, "all_watered"), query
            )


# ---------------------------------------------------------------------------
# Add and edit plant dialogs
# ---------------------------------------------------------------------------

@locked_handler
async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    track_message(context, update.message.message_id)
    name = update.message.text.strip()
    db: Database = context.bot_data["db"]
    if not valid_name(name):
        await tracked_reply(
            update, context, tr(context, "invalid_name", max_len=MAX_NAME_LEN),
            cancel_keyboard(bot_language(context))
        )
        return ADD_NAME
    if db.plant_exists(update.effective_user.id, name):
        await tracked_reply(
            update, context, tr(context, "duplicate_name"),
            cancel_keyboard(bot_language(context))
        )
        return ADD_NAME
    context.user_data["new_plant_name"] = name
    await tracked_reply(
        update, context, tr(context, "add_interval_prompt", name=html.escape(name)),
        cancel_keyboard(bot_language(context))
    )
    return ADD_INTERVAL


@locked_handler
async def add_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    track_message(context, update.message.message_id)
    text = update.message.text.strip()
    if not text.isnumeric() or int(text) <= 0:
        await tracked_reply(
            update, context, tr(context, "invalid_positive"),
            cancel_keyboard(bot_language(context))
        )
        return ADD_INTERVAL
    context.user_data["new_plant_interval"] = int(text)
    await tracked_reply(
        update, context, tr(context, "last_watered_prompt"),
        cancel_keyboard(bot_language(context)), parse_mode=None
    )
    return ADD_LAST_WATERED


@locked_handler
async def add_last_watered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    track_message(context, update.message.message_id)
    text = update.message.text.strip()
    if not text.isnumeric():
        await tracked_reply(
            update, context, tr(context, "invalid_days"),
            cancel_keyboard(bot_language(context))
        )
        return ADD_LAST_WATERED
    tgid = update.effective_user.id
    name = context.user_data["new_plant_name"]
    interval = context.user_data["new_plant_interval"]
    lastt = datetime.date.today().toordinal() - int(text)
    context.bot_data["db"].add_plant(tgid, name, interval, lastt)
    return await finish_managed_dialog(
        update, context, tr(context, "plant_added", name=html.escape(name))
    )


@locked_handler
async def edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    tgid = update.effective_user.id
    plant_id = int(query.data.removeprefix("plant_"))
    name = context.bot_data["db"].get_plant_name(tgid, plant_id)
    if not name:
        return await finish_managed_dialog(update, context, tr(context, "unavailable"))
    context.user_data["edit_plant_id"] = plant_id
    context.user_data["edit_plant_name"] = name
    await edit_or_replace_view(
        context, tgid, tr(context, "edit_action_prompt", name=html.escape(name)),
        edit_action_keyboard(bot_language(context)), query
    )
    return EDIT_ACTION


@locked_handler
async def edit_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    plant_id = context.user_data.get("edit_plant_id")
    name = db.get_plant_name(tgid, plant_id) if plant_id is not None else None
    if not name:
        return await finish_managed_dialog(update, context, tr(context, "unavailable"))
    safe_name = html.escape(name)
    if query.data == "edit_delete":
        db.delete_plant(tgid, plant_id)
        return await finish_managed_dialog(
            update, context, tr(context, "plant_deleted", name=safe_name)
        )
    if query.data == "edit_interval":
        await edit_or_replace_view(
            context, tgid, tr(context, "new_interval_prompt", name=safe_name),
            cancel_keyboard(bot_language(context)), query
        )
        return EDIT_INTERVAL
    if query.data == "edit_lastt":
        await edit_or_replace_view(
            context, tgid, tr(context, "edit_last_prompt", name=safe_name),
            cancel_keyboard(bot_language(context)), query
        )
        return EDIT_LAST_WATERED
    if query.data == "edit_rename":
        await edit_or_replace_view(
            context, tgid, tr(context, "rename_prompt", name=safe_name),
            cancel_keyboard(bot_language(context)), query
        )
        return EDIT_RENAME
    return EDIT_ACTION


@locked_handler
async def edit_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    track_message(context, update.message.message_id)
    text = update.message.text.strip()
    if not text.isnumeric() or int(text) <= 0:
        await tracked_reply(
            update, context, tr(context, "invalid_positive"),
            cancel_keyboard(bot_language(context))
        )
        return EDIT_INTERVAL
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    plant_id = context.user_data["edit_plant_id"]
    name = db.get_plant_name(tgid, plant_id)
    if not name or not db.update_interval(tgid, plant_id, int(text)):
        return await finish_managed_dialog(update, context, tr(context, "unavailable"))
    return await finish_managed_dialog(
        update, context, tr(
            context, "interval_updated", name=html.escape(name), days=text
        )
    )


@locked_handler
async def edit_last_watered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    track_message(context, update.message.message_id)
    text = update.message.text.strip()
    if not text.isnumeric():
        await tracked_reply(
            update, context, tr(context, "invalid_days"),
            cancel_keyboard(bot_language(context))
        )
        return EDIT_LAST_WATERED
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    plant_id = context.user_data["edit_plant_id"]
    name = db.get_plant_name(tgid, plant_id)
    lastt = datetime.date.today().toordinal() - int(text)
    if not name or not db.update_last_watered(tgid, plant_id, lastt):
        return await finish_managed_dialog(update, context, tr(context, "unavailable"))
    return await finish_managed_dialog(
        update, context, tr(context, "last_updated", name=html.escape(name))
    )


@locked_handler
async def edit_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        return await finish_managed_dialog(update, context, tr(context, "aborted"))
    track_message(context, update.message.message_id)
    name = update.message.text.strip()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    plant_id = context.user_data["edit_plant_id"]
    if not valid_name(name):
        await tracked_reply(
            update, context, tr(context, "invalid_name", max_len=MAX_NAME_LEN),
            cancel_keyboard(bot_language(context))
        )
        return EDIT_RENAME
    if db.plant_exists(tgid, name, exclude_id=plant_id):
        await tracked_reply(
            update, context, tr(context, "duplicate_name"),
            cancel_keyboard(bot_language(context))
        )
        return EDIT_RENAME
    if not db.rename_plant(tgid, plant_id, name):
        return await finish_managed_dialog(update, context, tr(context, "unavailable"))
    return await finish_managed_dialog(
        update, context, tr(context, "renamed", name=html.escape(name))
    )


# ---------------------------------------------------------------------------
# Sharing and reminder settings
# ---------------------------------------------------------------------------

@locked_handler
async def calendar_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    if update.callback_query:
        await update.callback_query.answer()
        await show_main_menu(context, tgid, tr(context, "aborted"), update.callback_query)
        return MAIN_MENU
    other_id = update.message.text.strip()
    if not other_id.lstrip("-").isnumeric() or not db.user_exists(int(other_id)):
        await update.message.reply_text(
            tr(context, "invalid_tgid"),
            reply_markup=cancel_keyboard(bot_language(context))
        )
        return CALENDAR_INPUT
    db.set_calendar(tgid, int(other_id))
    await show_main_menu(
        context, tgid, tr(context, "share_success", tgid=other_id),
        force_new=True
    )
    return MAIN_MENU


@locked_handler
async def reminder_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    if query.data == "rset_back":
        await show_main_menu(context, tgid, query=query)
        return MAIN_MENU
    if query.data == "rset_toggle":
        db.set_reminder_enabled(tgid, not db.get_reminder_enabled(tgid))
        _schedule_from_database(context.application, db, tgid)
        await edit_or_replace_view(
            context, tgid, tr(context, "reminder_settings"),
            reminder_settings_keyboard(
                db.get_reminder_enabled(tgid), db.get_reminder_time(tgid),
                bot_language(context)
            ), query
        )
    elif query.data == "rset_time":
        await edit_or_replace_view(
            context, tgid, tr(context, "time_prompt"),
            cancel_keyboard(bot_language(context)), query
        )
        return REMINDER_TIME_INPUT
    return REMINDER_MENU


@locked_handler
async def reminder_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tgid = update.effective_user.id
    db: Database = context.bot_data["db"]
    if update.callback_query:
        await update.callback_query.answer()
        await edit_or_replace_view(
            context, tgid, tr(context, "reminder_settings"),
            reminder_settings_keyboard(
                db.get_reminder_enabled(tgid), db.get_reminder_time(tgid),
                bot_language(context)
            ),
            update.callback_query
        )
        return REMINDER_MENU
    text = update.message.text.strip()
    if len(text) != 4 or not text.isnumeric():
        await update.message.reply_text(tr(context, "invalid_time_format"))
        return REMINDER_TIME_INPUT
    hh, mm = int(text[:2]), int(text[2:])
    if not 0 <= hh <= 23 or not 0 <= mm <= 59:
        await update.message.reply_text(tr(context, "invalid_time"))
        return REMINDER_TIME_INPUT
    time_str = f"{hh:02d}:{mm:02d}"
    db.set_reminder_time(tgid, time_str)
    _schedule_reminder(context.application, tgid, hh, mm)
    await edit_or_replace_view(
        context, tgid, tr(context, "time_updated", time=time_str),
        reminder_settings_keyboard(
            db.get_reminder_enabled(tgid), time_str, bot_language(context)
        ),
        force_new=True
    )
    return REMINDER_MENU


# ---------------------------------------------------------------------------
# Reminder jobs
# ---------------------------------------------------------------------------

def _schedule_reminder(app: Application, tgid: int, hour: int, minute: int) -> None:
    import pytz

    job_name = f"reminder_{tgid}"
    for job in app.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    app.job_queue.run_daily(
        reminder_job,
        datetime.time(hour, minute, tzinfo=pytz.timezone("Europe/Berlin")),
        name=job_name,
        data={"tgid": tgid},
    )
    logger.info("Reminder für User %s geplant um %02d:%02d", tgid, hour, minute)


def _schedule_from_database(app: Application, db: Database, tgid: int) -> None:
    hh, mm = map(int, db.get_reminder_time(tgid).split(":"))
    _schedule_reminder(app, tgid, hh, mm)


INTERRUPTIBLE_STATES = {
    WATERING_SELECT, ADD_NAME, ADD_INTERVAL, ADD_LAST_WATERED,
    EDIT_SELECT, EDIT_ACTION, EDIT_INTERVAL, EDIT_LAST_WATERED, EDIT_RENAME,
    CALENDAR_INPUT, REMINDER_MENU, REMINDER_TIME_INPUT,
}


async def interrupt_conversation(context: ContextTypes.DEFAULT_TYPE,
                                 conv_handler: ConversationHandler, tgid: int) -> bool:
    current_state = conv_handler._conversations.get((tgid, tgid))
    if current_state not in INTERRUPTIBLE_STATES:
        return False
    conv_handler._conversations.pop((tgid, tgid), None)
    await cleanup_managed_dialog(context, tgid)
    logger.info("Laufender Vorgang von User %s unterbrochen", tgid)
    return True


async def reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.bot_data["db"]
    tgid = context.job.data["tgid"]
    if not db.get_reminder_enabled(tgid):
        return
    due = db.get_due_plants(tgid, datetime.date.today().toordinal())
    if not due:
        return
    async with user_lock(context, tgid):
        conv = context.bot_data.get("conv_handler")
        interrupted = await interrupt_conversation(context, conv, tgid) if conv else False
        try:
            await show_today(context, tgid, force_new=True, interrupted=interrupted)
        except Exception as exc:
            logger.warning("Reminder für %s fehlgeschlagen: %s", tgid, exc)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unbehandelter Fehler bei Update %s", update, exc_info=context.error)


def create_application(token: str, language: str, db_path: str) -> Application:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"BOT_LANGUAGE must be one of {', '.join(SUPPORTED_LANGUAGES)}"
        )
    db = Database(db_path)
    app = Application.builder().token(token).build()
    app.bot_data.update({
        "db": db,
        "language": language,
        "user_locks": {},
        "recovered_users": set(),
    })

    for tgid, _, _ in db.get_all_users():
        _schedule_from_database(app, db, tgid)

    not_today = r"^(?!today_)"
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            CallbackQueryHandler(main_menu_handler, pattern=r"^action_"),
        ],
        states={
            MAIN_MENU: [CallbackQueryHandler(main_menu_handler, pattern=not_today)],
            WATERING_SELECT: [CallbackQueryHandler(watering_select, pattern=not_today)],
            ADD_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_name),
                CallbackQueryHandler(add_name, pattern=not_today),
            ],
            ADD_INTERVAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_interval),
                CallbackQueryHandler(add_interval, pattern=not_today),
            ],
            ADD_LAST_WATERED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_last_watered),
                CallbackQueryHandler(add_last_watered, pattern=not_today),
            ],
            EDIT_SELECT: [CallbackQueryHandler(edit_select, pattern=not_today)],
            EDIT_ACTION: [CallbackQueryHandler(edit_action, pattern=not_today)],
            EDIT_INTERVAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_interval),
                CallbackQueryHandler(edit_interval, pattern=not_today),
            ],
            EDIT_LAST_WATERED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_last_watered),
                CallbackQueryHandler(edit_last_watered, pattern=not_today),
            ],
            EDIT_RENAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_rename),
                CallbackQueryHandler(edit_rename, pattern=not_today),
            ],
            CALENDAR_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, calendar_input),
                CallbackQueryHandler(calendar_input, pattern=not_today),
            ],
            REMINDER_MENU: [CallbackQueryHandler(reminder_menu_handler, pattern=not_today)],
            REMINDER_TIME_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time_input),
                CallbackQueryHandler(reminder_time_input, pattern=not_today),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("help", help_command),
        ],
        per_message=False,
    )
    app.bot_data["conv_handler"] = conv

    app.add_handler(CallbackQueryHandler(recovery_handler), group=-1)
    app.add_handler(MessageHandler(filters.ALL, recovery_handler), group=-1)
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(today_callback, pattern=r"^today_"))
    app.add_error_handler(error_handler)
    return app


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")
    language = os.environ.get("BOT_LANGUAGE", "de").lower()
    app = create_application(
        token=token,
        language=language,
        db_path=os.environ.get("DB_PATH", "/data/Pflanzendaten.db"),
    )
    logger.info("WasserWächter gestartet (%s).", language)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
