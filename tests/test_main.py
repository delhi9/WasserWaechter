import unittest

from main import edit_action_keyboard, help_keyboard, help_text, main_menu_keyboard, today_keyboard


class KeyboardTest(unittest.TestCase):
    def test_main_menu_layout(self):
        rows = main_menu_keyboard(reminders_on=True).inline_keyboard
        self.assertEqual([[button.text for button in row] for row in rows], [
            ["📋 Übersicht"],
            ["💧 Gegossen", "✅ Heute"],
            ["🌱 Neue Pflanze", "✏️ Bearbeiten"],
            ["🔗 Teilen", "🔔 Reminder"],
        ])

    def test_today_callbacks_only_contain_numeric_plant_ids(self):
        rows = today_keyboard([(123, "Pflanze_mit_🔣")]).inline_keyboard
        self.assertEqual(rows[0][0].callback_data, "today_water_123")
        self.assertEqual(rows[-1][0].callback_data, "today_menu")

    def test_edit_menu_contains_rename(self):
        callbacks = [
            button.callback_data
            for row in edit_action_keyboard().inline_keyboard
            for button in row
        ]
        self.assertIn("edit_rename", callbacks)

    def test_help_has_single_start_button(self):
        rows = help_keyboard().inline_keyboard
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 1)
        self.assertEqual(rows[0][0].text, "Los geht's!")
        self.assertEqual(rows[0][0].callback_data, "action_help_start")
        self.assertIn("/help", help_text())


if __name__ == "__main__":
    unittest.main()
