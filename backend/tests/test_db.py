import sqlite3

from app.db import init_db


def test_init_db_migrates_settings_with_render_preset(tmp_path) -> None:
    db_path = tmp_path / "old.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE settings (
            id INTEGER NOT NULL PRIMARY KEY,
            logo_path VARCHAR NOT NULL
        )
        """
    )
    connection.execute("INSERT INTO settings (id, logo_path) VALUES (1, '')")
    connection.commit()
    connection.close()

    init_db(db_path)

    connection = sqlite3.connect(db_path)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(settings)").fetchall()
    }
    preset = connection.execute(
        "SELECT render_preset FROM settings WHERE id = 1"
    ).fetchone()
    connection.close()
    assert "render_preset" in columns
    assert preset == ("full",)
