import sqlite3
from contextlib import contextmanager


class Database:
    def __init__(self, path="coupons.db"):
        self.path = path
        self.init_db()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    m INTEGER NOT NULL,
                    n INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                );

                CREATE TABLE IF NOT EXISTS coupons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    config_id INTEGER NOT NULL,
                    tier INTEGER NOT NULL,
                    p REAL NOT NULL,
                    q REAL NOT NULL,
                    FOREIGN KEY (config_id) REFERENCES configs(id) ON DELETE CASCADE,
                    UNIQUE(config_id, tier)
                );

                CREATE INDEX IF NOT EXISTS idx_coupons_config_id
                ON coupons(config_id);
                """
            )

    @staticmethod
    def _row_to_dict(row):
        return dict(row) if row else None

    def list_configs(self):
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT c.*,
                       COUNT(cp.id) AS coupon_count
                FROM configs c
                LEFT JOIN coupons cp ON cp.config_id = c.id
                GROUP BY c.id
                ORDER BY c.created_at DESC, c.id DESC
                """
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_config(self, config_id):
        with self.connection() as conn:
            config = conn.execute(
                "SELECT * FROM configs WHERE id = ?",
                (config_id,),
            ).fetchone()
            if not config:
                return None
            coupons = conn.execute(
                """
                SELECT id, config_id, tier, p, q
                FROM coupons
                WHERE config_id = ?
                ORDER BY tier ASC, id ASC
                """,
                (config_id,),
            ).fetchall()
            payload = self._row_to_dict(config)
            payload["coupons"] = [self._row_to_dict(row) for row in coupons]
            return payload

    def create_config(self, config_data, coupons):
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO configs (name, x, y, m, n)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    config_data["name"],
                    config_data["x"],
                    config_data["y"],
                    config_data["m"],
                    config_data["n"],
                ),
            )
            config_id = cursor.lastrowid
            self._replace_coupons(conn, config_id, coupons)
            return config_id

    def update_config(self, config_id, config_data, coupons):
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE configs
                SET name = ?, x = ?, y = ?, m = ?, n = ?
                WHERE id = ?
                """,
                (
                    config_data["name"],
                    config_data["x"],
                    config_data["y"],
                    config_data["m"],
                    config_data["n"],
                    config_id,
                ),
            )
            if cursor.rowcount == 0:
                return False
            self._replace_coupons(conn, config_id, coupons)
            return True

    def delete_config(self, config_id):
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM configs WHERE id = ?", (config_id,))
            return cursor.rowcount > 0

    def add_coupon(self, config_id, coupon):
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO coupons (config_id, tier, p, q)
                VALUES (?, ?, ?, ?)
                """,
                (config_id, coupon["tier"], coupon["p"], coupon["q"]),
            )
            return cursor.lastrowid

    def update_coupon(self, coupon_id, coupon):
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE coupons
                SET tier = ?, p = ?, q = ?
                WHERE id = ?
                """,
                (coupon["tier"], coupon["p"], coupon["q"], coupon_id),
            )
            return cursor.rowcount > 0

    def delete_coupon(self, coupon_id):
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM coupons WHERE id = ?", (coupon_id,))
            return cursor.rowcount > 0

    def get_coupon(self, coupon_id):
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT id, config_id, tier, p, q
                FROM coupons
                WHERE id = ?
                """,
                (coupon_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def _replace_coupons(self, conn, config_id, coupons):
        conn.execute("DELETE FROM coupons WHERE config_id = ?", (config_id,))
        if not coupons:
            return
        conn.executemany(
            """
            INSERT INTO coupons (config_id, tier, p, q)
            VALUES (?, ?, ?, ?)
            """,
            [
                (config_id, coupon["tier"], coupon["p"], coupon["q"])
                for coupon in coupons
            ],
        )
