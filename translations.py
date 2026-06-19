SUPPORTED_LANGUAGES = ("de", "en")


TEXTS = {
    "de": {
        "menu_overview": "📋 Übersicht",
        "menu_watered": "💧 Gegossen",
        "menu_today": "✅ Heute",
        "menu_add": "🌱 Neue Pflanze",
        "menu_edit": "✏️ Bearbeiten",
        "menu_share": "🔗 Teilen",
        "menu_reminder_on": "🔔 Reminder",
        "menu_reminder_off": "🔕 Reminder",
        "reminder_toggle_on": "✅ Reminder an  →  ausschalten",
        "reminder_toggle_off": "❌ Reminder aus  →  einschalten",
        "reminder_time_button": "⏰ Zeit setzen ({time})",
        "back": "🔙 Zurück",
        "cancel": "❌ Abbruch",
        "edit_interval": "⏱ Intervall ändern",
        "edit_last_watered": "💧 Letztes Gießen setzen",
        "edit_rename": "🏷 Umbenennen",
        "edit_delete": "🗑 Pflanze löschen",
        "help_start": "Los geht's!",
        "help": (
            "🌿 <b>So funktioniert der WasserWächter</b>\n\n"
            "📋 <b>Übersicht</b> zeigt den Zustand deiner Pflanzen.\n"
            "💧 <b>Gegossen</b> trägt ein, was du heute gegossen hast.\n"
            "✅ <b>Heute</b> zeigt alle aktuell fälligen Pflanzen.\n"
            "🌱 <b>Neue Pflanze</b> legt Name und Gießintervall fest.\n"
            "✏️ <b>Bearbeiten</b> ändert oder löscht vorhandene Pflanzen.\n"
            "🔗 <b>Teilen</b> verbindet dich über die Telegram-ID mit einem anderen Kalender.\n"
            "🔔 <b>Reminder</b> stellt tägliche Erinnerungen und deren Uhrzeit ein.\n\n"
            "Mit <code>/help</code> kannst du diese Hilfe jederzeit erneut öffnen."
        ),
        "today_back": "📋 Zum Menü",
        "no_plants": "Du hast noch keine Pflanzen hinzugefügt.",
        "overview_columns": "Pflanze         Int  Tage",
        "overdue": "🔴 {name} ({days}d überfällig)",
        "due_today": "🟠 {name} (heute fällig)",
        "due_in": "🟡 {name} (in {days}d)",
        "overview_title": "📋 <b>Deine Pflanzen:</b>",
        "main_prompt": "Was möchtest du tun?",
        "nothing_due": "Heute gibt es nichts zu gießen. 🌿",
        "today_title": "💧 <b>Heute gießen:</b>",
        "interrupted": "⚠️ <i>Dein laufender Vorgang wurde unterbrochen.</i>",
        "welcome": (
            "🌿 Willkommen beim <b>WasserWächter</b>!\n"
            "Ich erinnere dich daran, deine Pflanzen zu gießen."
        ),
        "water_select": "💧 Welche Pflanze wurde gegossen?",
        "add_name_prompt": "🌱 Wie soll die Pflanze heißen? (max. {max_len} Zeichen)\n\nEinfach eintippen:",
        "edit_select": "✏️ Welche Pflanze möchtest du bearbeiten?",
        "share_prompt": (
            "🔗 <b>Kalender teilen</b>\n\n"
            "Deine Telegram-ID: <code>{tgid}</code>\n"
            "Aktuelle Kalender-ID: <code>{calendar_id}</code>\n\n"
            "Gib die Telegram-ID der Person ein, deren Kalender du nutzen möchtest:"
        ),
        "reminder_settings": "🔔 <b>Reminder-Einstellungen</b>",
        "aborted": "Abgebrochen.",
        "unavailable": "Diese Pflanze ist nicht verfügbar.",
        "watered": "✅ <b>{name}</b> wurde heute gegossen!",
        "stale_message": "Diese Nachricht ist nicht mehr aktiv.",
        "all_watered": "✅ Alle Pflanzen für heute gegossen!",
        "invalid_name": "❌ Bitte einen Namen mit 1 bis {max_len} Zeichen eingeben:",
        "duplicate_name": "❌ Dieser Name existiert bereits.",
        "add_interval_prompt": "Alle wie vielen Tage soll ich dich erinnern, <b>{name}</b> zu gießen?",
        "invalid_positive": "❌ Bitte eine positive ganze Zahl eingeben:",
        "last_watered_prompt": "Vor wie vielen Tagen hast du diese Pflanze zuletzt gegossen? (0 = heute)",
        "invalid_days": "❌ Bitte eine Zahl eingeben (0 = heute):",
        "plant_added": "✅ <b>{name}</b> wurde hinzugefügt!",
        "edit_action_prompt": "✏️ Was möchtest du bei <b>{name}</b> ändern?",
        "plant_deleted": "🗑 <b>{name}</b> wurde gelöscht.",
        "new_interval_prompt": "⏱ Neues Gießintervall für <b>{name}</b>:",
        "edit_last_prompt": "💧 Vor wie vielen Tagen hast du <b>{name}</b> zuletzt gegossen?",
        "rename_prompt": "🏷 Wie soll <b>{name}</b> künftig heißen?",
        "interval_updated": "✅ <b>{name}</b> wird jetzt alle <b>{days} Tage</b> gegossen.",
        "last_updated": "✅ Letztes Gießen für <b>{name}</b> aktualisiert.",
        "renamed": "✅ Die Pflanze heißt jetzt <b>{name}</b>.",
        "invalid_tgid": "❌ Keine gültige Telegram-ID eines bekannten Nutzers.",
        "share_success": "✅ Du nutzt jetzt den Kalender von <code>{tgid}</code>.",
        "time_prompt": "⏰ <b>Reminder-Zeit setzen</b>\n\nBitte als <code>HHMM</code> eingeben, z.B. <code>0800</code>.",
        "invalid_time_format": "❌ Bitte genau vier Ziffern eingeben, z.B. 0800.",
        "invalid_time": "❌ Ungültige Uhrzeit.",
        "time_updated": "✅ Reminder-Zeit auf <b>{time}</b> gesetzt.",
    },
    "en": {
        "menu_overview": "📋 Overview",
        "menu_watered": "💧 Watered",
        "menu_today": "✅ Today",
        "menu_add": "🌱 New plant",
        "menu_edit": "✏️ Edit",
        "menu_share": "🔗 Share",
        "menu_reminder_on": "🔔 Reminder",
        "menu_reminder_off": "🔕 Reminder",
        "reminder_toggle_on": "✅ Reminders on  →  turn off",
        "reminder_toggle_off": "❌ Reminders off  →  turn on",
        "reminder_time_button": "⏰ Set time ({time})",
        "back": "🔙 Back",
        "cancel": "❌ Cancel",
        "edit_interval": "⏱ Change interval",
        "edit_last_watered": "💧 Set last watering",
        "edit_rename": "🏷 Rename",
        "edit_delete": "🗑 Delete plant",
        "help_start": "Let's go!",
        "help": (
            "🌿 <b>How WateringWatcher works</b>\n\n"
            "📋 <b>Overview</b> shows the status of your plants.\n"
            "💧 <b>Watered</b> records what you watered today.\n"
            "✅ <b>Today</b> shows all plants currently due.\n"
            "🌱 <b>New plant</b> sets its name and watering interval.\n"
            "✏️ <b>Edit</b> changes or deletes existing plants.\n"
            "🔗 <b>Share</b> connects you to another calendar using a Telegram ID.\n"
            "🔔 <b>Reminder</b> configures daily reminders and their time.\n\n"
            "Use <code>/help</code> to open this guide again at any time."
        ),
        "today_back": "📋 Back to menu",
        "no_plants": "You have not added any plants yet.",
        "overview_columns": "Plant            Int  Days",
        "overdue": "🔴 {name} ({days}d overdue)",
        "due_today": "🟠 {name} (due today)",
        "due_in": "🟡 {name} (in {days}d)",
        "overview_title": "📋 <b>Your plants:</b>",
        "main_prompt": "What would you like to do?",
        "nothing_due": "There is nothing to water today. 🌿",
        "today_title": "💧 <b>Water today:</b>",
        "interrupted": "⚠️ <i>Your current action was interrupted.</i>",
        "welcome": (
            "🌿 Welcome to <b>WateringWatcher</b>!\n"
            "I will remind you when your plants need watering."
        ),
        "water_select": "💧 Which plant did you water?",
        "add_name_prompt": "🌱 What is the plant's name? (max. {max_len} characters)\n\nType it below:",
        "edit_select": "✏️ Which plant would you like to edit?",
        "share_prompt": (
            "🔗 <b>Share calendar</b>\n\n"
            "Your Telegram ID: <code>{tgid}</code>\n"
            "Current calendar ID: <code>{calendar_id}</code>\n\n"
            "Enter the Telegram ID of the person whose calendar you want to use:"
        ),
        "reminder_settings": "🔔 <b>Reminder settings</b>",
        "aborted": "Cancelled.",
        "unavailable": "This plant is not available.",
        "watered": "✅ <b>{name}</b> was watered today!",
        "stale_message": "This message is no longer active.",
        "all_watered": "✅ All plants have been watered for today!",
        "invalid_name": "❌ Enter a name between 1 and {max_len} characters:",
        "duplicate_name": "❌ This name already exists.",
        "add_interval_prompt": "How often should I remind you to water <b>{name}</b>? Enter the number of days:",
        "invalid_positive": "❌ Enter a positive whole number:",
        "last_watered_prompt": "How many days ago did you last water this plant? (0 = today)",
        "invalid_days": "❌ Enter a number (0 = today):",
        "plant_added": "✅ <b>{name}</b> was added!",
        "edit_action_prompt": "✏️ What would you like to change for <b>{name}</b>?",
        "plant_deleted": "🗑 <b>{name}</b> was deleted.",
        "new_interval_prompt": "⏱ Enter the new watering interval for <b>{name}</b>:",
        "edit_last_prompt": "💧 How many days ago did you last water <b>{name}</b>?",
        "rename_prompt": "🏷 What should <b>{name}</b> be called?",
        "interval_updated": "✅ <b>{name}</b> will now be watered every <b>{days} days</b>.",
        "last_updated": "✅ Last watering date for <b>{name}</b> was updated.",
        "renamed": "✅ The plant is now called <b>{name}</b>.",
        "invalid_tgid": "❌ Enter a valid Telegram ID of a known user.",
        "share_success": "✅ You are now using the calendar of <code>{tgid}</code>.",
        "time_prompt": "⏰ <b>Set reminder time</b>\n\nEnter four digits as <code>HHMM</code>, e.g. <code>0800</code>.",
        "invalid_time_format": "❌ Enter exactly four digits, e.g. 0800.",
        "invalid_time": "❌ Invalid time.",
        "time_updated": "✅ Reminder time set to <b>{time}</b>.",
    },
}


def get_text(language: str, key: str, **values) -> str:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return TEXTS[language][key].format(**values)
