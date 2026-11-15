from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from backend.migrate import MIGRATIONS_DIRECTORY, migrate


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.database = self.directory / "test.sqlite3"
        self.assertEqual(migrate(self.database), 1)

    def test_rerun_keeps_existing_data(self):
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute("INSERT INTO quizzes (title) VALUES ('First quiz')")
            self.assertEqual(migrate(self.database), 1)
            self.assertEqual(
                connection.execute("SELECT title FROM quizzes").fetchall(),
                [("First quiz",)],
            )
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (1,))

    def test_failed_upgrade_rolls_back_schema_and_version(self):
        migrations = self.directory / "migrations"
        shutil.copytree(MIGRATIONS_DIRECTORY, migrations)
        second = migrations / "002_example.sql"
        second.write_text(
            "CREATE TABLE extras (id INTEGER PRIMARY KEY);\n"
            "INSERT INTO missing_table VALUES (1);\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "002_example.sql"):
            migrate(self.database, migrations)

        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (1,))
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_schema WHERE name = 'extras'"
            ).fetchone())

        second.write_text("CREATE TABLE extras (id INTEGER PRIMARY KEY);", encoding="utf-8")
        self.assertEqual(migrate(self.database, migrations), 2)
        self.assertEqual(migrate(self.database, migrations), 2)

    def test_answers_require_matching_quiz_session_participant_and_option(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                INSERT INTO quizzes (id, title) VALUES (1, 'First'), (2, 'Second');
                INSERT INTO questions (id, quiz_id, prompt, position)
                    VALUES (1, 1, 'Question 1', 1), (2, 1, 'Question 2', 2),
                           (3, 2, 'Question 3', 1);
                INSERT INTO question_options (id, question_id, label, position, is_correct)
                    VALUES (1, 1, 'One', 1, 1), (2, 1, 'Two', 2, 0),
                           (3, 2, 'Three', 1, 1), (4, 3, 'Four', 1, 1);
                INSERT INTO game_sessions (id, quiz_id, join_code)
                    VALUES (1, 1, 'ABCDE'), (2, 1, 'FGHIJ');
                INSERT INTO participants (id, session_id, display_name)
                    VALUES (1, 1, 'Alex'), (2, 2, 'Sam');
                """
            )
            insert_answer = (
                "INSERT INTO answers "
                "(quiz_id, session_id, participant_id, question_id, option_id, awarded_points) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            )

            for answer in [
                (2, 1, 1, 3, 4, 1),
                (1, 1, 2, 1, 1, 1),
                (1, 1, 1, 3, 4, 1),
                (1, 1, 1, 1, 3, 1),
            ]:
                with self.subTest(answer=answer):
                    with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY"):
                        connection.execute(insert_answer, answer)

            connection.execute(insert_answer, (1, 1, 1, 1, 1, 1))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                connection.execute(insert_answer, (1, 1, 1, 1, 2, 0))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                connection.execute(
                    "INSERT INTO question_options (question_id, label, position, is_correct) "
                    "VALUES (1, 'Another correct option', 3, 1)"
                )

            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
