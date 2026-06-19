import datetime
import sqlite3
import tempfile
import unittest
from pathlib import Path

from db import Database


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "plants.db"
        self.db = Database(str(self.db_path))
        self.db.ensure_user(100)
        self.db.ensure_user(200)

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def add_plant(self, user_id=100, name="Monstera", interval=7, days_ago=7):
        last_watered = datetime.date.today().toordinal() - days_ago
        self.db.add_plant(user_id, name, interval, last_watered)
        return self.db.get_plants(user_id)[0][0]

    def test_current_message_id_is_persisted(self):
        self.assertIsNone(self.db.get_current_message_id(100))
        self.db.set_current_message_id(100, 42)
        self.assertEqual(self.db.get_current_message_id(100), 42)
        self.db.set_current_message_id(100, None)
        self.assertIsNone(self.db.get_current_message_id(100))

    def test_shared_calendar_allows_authorized_id_operations(self):
        plant_id = self.add_plant()
        self.db.set_calendar(200, 100)

        self.assertEqual(self.db.get_plants(200), [(plant_id, "Monstera")])
        self.assertTrue(self.db.water_plant(200, plant_id))

    def test_plant_id_from_unshared_calendar_is_rejected(self):
        plant_id = self.add_plant()

        self.assertIsNone(self.db.get_plant_name(200, plant_id))
        self.assertFalse(self.db.water_plant(200, plant_id))
        self.assertFalse(self.db.update_interval(200, plant_id, 2))
        self.assertFalse(self.db.delete_plant(200, plant_id))

    def test_due_plants_use_callers_shared_calendar(self):
        plant_id = self.add_plant()
        self.db.set_calendar(200, 100)

        due = self.db.get_due_plants(200, datetime.date.today().toordinal())
        self.assertEqual(due, [(plant_id, "Monstera")])

    def test_rename_checks_same_calendar_and_supports_exclusion(self):
        plant_id = self.add_plant()
        self.assertTrue(self.db.plant_exists(100, "Monstera"))
        self.assertFalse(self.db.plant_exists(100, "Monstera", exclude_id=plant_id))
        self.assertTrue(self.db.rename_plant(100, plant_id, "Fensterblatt"))
        self.assertEqual(self.db.get_plant_name(100, plant_id), "Fensterblatt")


class MigrationTest(unittest.TestCase):
    def test_existing_database_gets_current_message_column_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE personen (
                    tgid INTEGER PRIMARY KEY,
                    kalender INTEGER NOT NULL,
                    reminder_enabled INTEGER NOT NULL DEFAULT 1,
                    reminder_time TEXT NOT NULL DEFAULT '10:00'
                );
                CREATE TABLE pflanzen (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tgid INTEGER NOT NULL,
                    pflanze TEXT NOT NULL,
                    intervall INTEGER NOT NULL DEFAULT 7,
                    lastt INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(tgid, pflanze)
                );
                INSERT INTO personen VALUES (100, 100, 1, '10:00');
                INSERT INTO pflanzen (tgid, pflanze, intervall, lastt)
                VALUES (100, 'Altbestand', 5, 123);
                """
            )
            conn.close()

            db = Database(str(path))
            self.assertIsNone(db.get_current_message_id(100))
            self.assertEqual(db.get_plant_names(100), ["Altbestand"])
            db.close()


if __name__ == "__main__":
    unittest.main()
