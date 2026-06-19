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
]


class Database:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
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

    # ------------------------------------------------------------------
    # Pflanzen – Lesen
    # ------------------------------------------------------------------

    def _calendar_tgid(self, tgid: int) -> int:
        return self.get_calendar_id(tgid)

    def get_plant_names(self, tgid: int) -> list[str]:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "SELECT pflanze FROM pflanzen WHERE tgid = ? ORDER BY pflanze", (owner,)
        )
        return [row["pflanze"] for row in cur.fetchall()]

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

    def plant_exists(self, tgid: int, name: str) -> bool:
        owner = self._calendar_tgid(tgid)
        cur = self._conn.execute(
            "SELECT 1 FROM pflanzen WHERE tgid = ? AND pflanze = ?", (owner, name)
        )
        return cur.fetchone() is not None

    def get_due_plants(self, calendar_tgid: int, today_ordinal: int) -> list[str]:
        cur = self._conn.execute(
            "SELECT pflanze FROM pflanzen "
            "WHERE tgid = ? AND ? - lastt >= intervall "
            "ORDER BY pflanze",
            (calendar_tgid, today_ordinal),
        )
        return [row["pflanze"] for row in cur.fetchall()]

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

    def water_plant(self, tgid: int, name: str) -> None:
        owner = self._calendar_tgid(tgid)
        today = datetime.date.today().toordinal()
        self._conn.execute(
            "UPDATE pflanzen SET lastt = ? WHERE tgid = ? AND pflanze = ?",
            (today, owner, name),
        )
        self._conn.commit()

    def update_interval(self, tgid: int, name: str, intervall: int) -> None:
        owner = self._calendar_tgid(tgid)
        self._conn.execute(
            "UPDATE pflanzen SET intervall = ? WHERE tgid = ? AND pflanze = ?",
            (intervall, owner, name),
        )
        self._conn.commit()

    def update_last_watered(self, tgid: int, name: str, lastt: int) -> None:
        owner = self._calendar_tgid(tgid)
        self._conn.execute(
            "UPDATE pflanzen SET lastt = ? WHERE tgid = ? AND pflanze = ?",
            (lastt, owner, name),
        )
        self._conn.commit()

    def delete_plant(self, tgid: int, name: str) -> None:
        owner = self._calendar_tgid(tgid)
        self._conn.execute(
            "DELETE FROM pflanzen WHERE tgid = ? AND pflanze = ?", (owner, name)
        )
        self._conn.commit()
        logger.info("Pflanze gelöscht: %s (User %s)", name, owner)
