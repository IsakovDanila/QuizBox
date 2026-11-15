"""Apply QuizBox SQLite migrations with the Python standard library."""

import argparse
from contextlib import closing
from pathlib import Path
import re
import sqlite3

DEFAULT_DATABASE = Path(__file__).resolve().parent / "quizbox.sqlite3"
MIGRATIONS_DIRECTORY = Path(__file__).resolve().with_name("migrations")
MIGRATION_NAME = re.compile(r"([0-9]{3,})_[a-z0-9_]+\.sql")


def migrate(database: Path, directory: Path = MIGRATIONS_DIRECTORY) -> int:
    paths = sorted(directory.glob("*.sql"))
    migrations = []
    for path in paths:
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise ValueError(f"Invalid migration filename: {path.name}")
        migrations.append((int(match[1]), path))
    migrations.sort()
    if not migrations or [version for version, _ in migrations] != list(
        range(1, len(migrations) + 1)
    ):
        raise ValueError("Migration versions must start at 1 and be consecutive")

    with closing(sqlite3.connect(database, timeout=10, isolation_level=None)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        # Read the version after acquiring the write lock so concurrent runs cannot
        # both apply the same migration.
        connection.execute("BEGIN IMMEDIATE")
        try:
            current_version = connection.execute("PRAGMA user_version").fetchone()[0]
            if not 0 <= current_version <= len(migrations):
                raise ValueError(
                    f"Database version {current_version} is unsupported by this checkout"
                )
            if current_version == 0 and connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' LIMIT 1"
            ).fetchone():
                raise ValueError("Database is not empty and has no QuizBox schema version")

            for version, path in migrations[current_version:]:
                try:
                    # executescript() implicitly commits an open transaction.
                    # Execute complete statements individually to retain the lock.
                    script = path.read_text(encoding="utf-8")
                    start = 0
                    for terminator in re.finditer(";", script):
                        end = terminator.end()
                        statement = script[start:end]
                        if sqlite3.complete_statement(statement):
                            connection.execute(statement)
                            start = end
                    if script[start:].strip():
                        connection.execute(script[start:])
                    connection.execute(f"PRAGMA user_version = {version}")
                except sqlite3.Error as error:
                    raise ValueError(f"{path.name}: {error}") from error

            if current_version < len(migrations):
                violation = connection.execute("PRAGMA foreign_key_check").fetchone()
                if violation:
                    raise ValueError(f"Foreign key check failed: {violation}")
            connection.execute("COMMIT")
        except (OSError, ValueError, sqlite3.Error):
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    return len(migrations)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    try:
        version = migrate(args.database)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Migration failed: {error}\n")
    print(f"SQLite schema version: {version} ({args.database.resolve()})")


if __name__ == "__main__":
    main()
