#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import datetime
import logging
import os

logger = logging.getLogger(__name__)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS personen (
    tgid              INTEGER PRIMARY KEY,
    kalender          INTEGER NOT NULL,
    reminder_enabled  INTEGER NOT NULL DEFAULT 1,
    reminder_time     TEXT    NOT NULL DEFAULT '10:00',
    current_message_id INTEGER,
    FOREIGN KEY (kalender) REFERENCES personen(tgid)
);

CREATE TABLE IF NOT EXISTS pflanzen (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tgid       INTEGER NOT NULL,
    pflanze    TEXT    NOT NULL,
    intervall  INTEGER NOT NULL DEFAULT 7,
    lastt      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(tgid, pflanze),
    FOREIGN KEY (tgid) REFERENCES personen(tgid) ON DELETE CASCADE
);
"""

MIGRATIONS = [
    "ALTER TABLE personen ADD COLUMN reminder_enabled INTEGER NOT NULL DEFAULT 1;",
    "ALTER TABLE personen ADD COLUMN reminder_time TEXT NOT NULL DEFAULT '10:00';",
    "ALTER TABLE personen ADD COLUMN current_message_id INTEGER;",
]


class Database:
    def __init__(self, db_path: str) -> None:
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.info("Datenbank geöffnet: %s", db_path)

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        for migration in MIGRATIONS:
            try:
                self._conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # Spalte existiert bereits
        self._conn.commit()

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    def ensure_user(self, tgid: int) -> bool:
        cur = self._conn.execute("SELECT tgid FROM personen WHERE tgid = ?", (tgid,))
        if cur.fetchone():
            return False
        self._conn.execute(
            "INSERT INTO personen (tgid, kalender, reminder_enabled, reminder_time) "
            "VALUES (?, ?, 1, '10:00')",
            (tgid, tgid),
        )
        self._conn.commit()
        logger.info("Neuer User angelegt: %s", tgid)
        return True

    def user_exists(self, tgid: int) -> bool:
        cur = self._conn.execute("SELECT 1 FROM personen WHERE tgid = ?", (tgid,))
        return cur.fetchone() is not None

    def get_all_users(self) -> list[tuple[int, int, bool]]:
        cur = self._conn.execute(
            "SELECT tgid, kalender, reminder_enabled FROM personen"
        )
        return [(row["tgid"], row["kalender"], bool(row["reminder_enabled"]))
                for row in cur.fetchall()]

    def get_calendar_id(self, tgid: int) -> int:
        cur = self._conn.execute("SELECT kalender FROM personen WHERE tgid = ?", (tgid,))
        row = cur.fetchone()
        return row["kalender"] if row else tgid

    def set_calendar(self, tgid: int, calendar_id: int) -> None:
        self._conn.execute(
            "UPDATE personen SET kalender = ? WHERE tgid = ?", (calendar_id, tgid)
        )
        self._conn.commit()

    def get_reminder_enabled(self, tgid: int) -> bool:
        cur = self._conn.execute(
            "SELECT reminder_enabled FROM personen WHERE tgid = ?", (tgid,)
        )
        row = cur.fetchone()
        return bool(row["reminder_enabled"]) if row else True

    def set_reminder_enabled(self, tgid: int, enabled: bool) -> None:
        self._conn.execute(
            "UPDATE personen SET reminder_enabled = ? WHERE tgid = ?",
            (1 if enabled else 0, tgid),
        )
        self._conn.commit()
        logger.info("Reminder für User %s: %s", tgid, "an" if enabled else "aus")

    def get_reminder_time(self, tgid: int) -> str:
        """Gibt die Reminder-Zeit als 'HH:MM' zurück."""
        cur = self._conn.execute(
            "SELECT reminder_time FROM personen WHERE tgid = ?", (tgid,)
        )
        row = cur.fetchone()
        return row["reminder_time"] if row else "10:00"

    def set_reminder_time(self, tgid: int, time_str: str) -> None:
        """time_str im Format 'HH:MM'."""
        self._conn.execute(
            "UPDATE personen SET reminder_time = ? WHERE tgid = ?", (time_str, tgid)
        )
        self._conn.commit()
        logger.info("Reminder-Zeit für User %s gesetzt auf %s", tgid, time_str)

    def get_current_message_id(self, tgid: int) -> int | None:
        cur = self._conn.execute(
            "SELECT current_message_id FROM personen WHERE tgid = ?", (tgid,)
        )
        row = cur.fetchone()
        return row["current_message_id"] if row else None

    def set_current_message_id(self, tgid: int, message_id: int | None) -> None:
        self._conn.execute(
            "UPDATE personen SET current_message_id = ? WHERE tgid = ?",
            (message_id, tgid),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Pflanzen – Lesen
    # ------------------------------------------------------------------

    def _calendar_tgid(self, tgid: int) -> int:
        return self.get_calendar_id(tgid)

    def get_plants(self, tgid: int) -> list[tuple[int, str]]:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "SELECT id, pflanze FROM pflanzen WHERE tgid = ? ORDER BY pflanze", (owner,)
        )
        return [(row["id"], row["pflanze"]) for row in cur.fetchall()]

    def get_plant_names(self, tgid: int) -> list[str]:
        return [name for _, name in self.get_plants(tgid)]

    def get_plants_with_status(self, tgid: int) -> list[tuple[str, int, int]]:
        owner = self._calendar_tgid(tgid)
        today = datetime.date.today().toordinal()
        cur = self._conn.execute(
            "SELECT pflanze, intervall, lastt FROM pflanzen WHERE tgid = ? ORDER BY pflanze",
            (owner,),
        )
        result = []
        for row in cur.fetchall():
            days_till = row["intervall"] - (today - row["lastt"])
            result.append((row["pflanze"], row["intervall"], days_till))
        return result

    def plant_exists(self, tgid: int, name: str, exclude_id: int | None = None) -> bool:
        owner = self._calendar_tgid(tgid)
        sql = "SELECT 1 FROM pflanzen WHERE tgid = ? AND pflanze = ?"
        params: tuple = (owner, name)
        if exclude_id is not None:
            sql += " AND id != ?"
            params += (exclude_id,)
        cur = self._conn.execute(sql, params)
        return cur.fetchone() is not None

    def get_due_plants(self, tgid: int, today_ordinal: int) -> list[tuple[int, str]]:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "SELECT id, pflanze FROM pflanzen "
            "WHERE tgid = ? AND ? - lastt >= intervall "
            "ORDER BY pflanze",
            (owner, today_ordinal),
        )
        return [(row["id"], row["pflanze"]) for row in cur.fetchall()]

    def get_plant_name(self, tgid: int, plant_id: int) -> str | None:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "SELECT pflanze FROM pflanzen WHERE id = ? AND tgid = ?",
            (plant_id, owner),
        )
        row = cur.fetchone()
        return row["pflanze"] if row else None

    # ------------------------------------------------------------------
    # Pflanzen – Schreiben
    # ------------------------------------------------------------------

    def add_plant(self, tgid: int, name: str, intervall: int, lastt: int) -> None:
        owner = self._calendar_tgid(tgid)
        try:
            self._conn.execute(
                "INSERT INTO pflanzen (tgid, pflanze, intervall, lastt) VALUES (?, ?, ?, ?)",
                (owner, name, intervall, lastt),
            )
            self._conn.commit()
            logger.info("Pflanze hinzugefügt: %s (User %s)", name, owner)
        except sqlite3.IntegrityError as e:
            logger.error("Fehler beim Hinzufügen von Pflanze %s: %s", name, e)
            raise

    def water_plant(self, tgid: int, plant_id: int) -> bool:
        owner = self._calendar_tgid(tgid)
        today = datetime.date.today().toordinal()
        cur = self._conn.execute(
            "UPDATE pflanzen SET lastt = ? WHERE id = ? AND tgid = ?",
            (today, plant_id, owner),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def update_interval(self, tgid: int, plant_id: int, intervall: int) -> bool:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "UPDATE pflanzen SET intervall = ? WHERE id = ? AND tgid = ?",
            (intervall, plant_id, owner),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def update_last_watered(self, tgid: int, plant_id: int, lastt: int) -> bool:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "UPDATE pflanzen SET lastt = ? WHERE id = ? AND tgid = ?",
            (lastt, plant_id, owner),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def rename_plant(self, tgid: int, plant_id: int, name: str) -> bool:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "UPDATE pflanzen SET pflanze = ? WHERE id = ? AND tgid = ?",
            (name, plant_id, owner),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def delete_plant(self, tgid: int, plant_id: int) -> bool:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "DELETE FROM pflanzen WHERE id = ? AND tgid = ?", (plant_id, owner)
        )
        self._conn.commit()
        if cur.rowcount:
            logger.info("Pflanze %s gelöscht (User %s)", plant_id, owner)
        return cur.rowcount == 1

    def close(self) -> None:
        self._conn.close()
