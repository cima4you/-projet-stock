import os
import sys
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Any
from werkzeug.security import generate_password_hash
from config import DB_PATH, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_EMAIL, IS_POSTGRES, DATABASE_URL

logger = logging.getLogger(__name__)

_db_local = threading.local()


class DatabaseError(Exception):
    pass


class ConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn
        self._orig_cursor = conn.cursor

    def cursor(self):
        return CursorWrapper(self._orig_cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class Row:
    def __init__(self, values, description):
        self._values = tuple(values)
        self._mapping = {}
        if description:
            for i, col in enumerate(description):
                self._mapping[col[0]] = i

    def __getitem__(self, key):
        if isinstance(key, str):
            return self._values[self._mapping[key]]
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._mapping.keys())


class CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None
        self.description = None
        self.rowcount = 0
        self._closed = False

    def _adapt_sql(self, sql):
        if not IS_POSTGRES:
            return sql
        sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        sql = sql.replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT NOW()")
        sql = sql.replace("CURRENT_TIMESTAMP", "NOW()")
        sql = sql.replace('?', '%s')
        return sql

    def execute(self, sql, params=None):
        sql = self._adapt_sql(sql)
        is_insert = sql.strip().upper().startswith('INSERT')
        has_returning = 'RETURNING' in sql.upper()

        if IS_POSTGRES and is_insert and not has_returning:
            sql = sql + ' RETURNING id'

        self._cursor.execute(sql, params or ())
        self.description = self._cursor.description
        self.rowcount = self._cursor.rowcount

        if IS_POSTGRES and is_insert:
            try:
                self.lastrowid = self._cursor.fetchone()[0]
            except Exception:
                self.lastrowid = None
        elif IS_SQLITE:
            self.lastrowid = self._cursor.lastrowid
        else:
            self.lastrowid = getattr(self._cursor, 'lastrowid', None)

        return self

    def executemany(self, sql, params_list):
        sql = self._adapt_sql(sql)
        self._cursor.executemany(sql, params_list)
        self.rowcount = self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if IS_SQLITE:
            return row
        return Row(row, self.description)

    def fetchall(self):
        rows = self._cursor.fetchall()
        if IS_SQLITE:
            return rows
        return [Row(row, self.description) for row in rows]

    def __getattr__(self, name):
        if self._closed:
            raise DatabaseError("Cursor is closed")
        return getattr(self._cursor, name)

    def close(self):
        self._closed = True
        self._cursor.close()


IS_SQLITE = not IS_POSTGRES


def _get_raw_connection():
    if IS_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    else:
        import sqlite3
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA busy_timeout = 30000')
            conn.execute('PRAGMA journal_mode = WAL')
        except Exception:
            pass
        return conn


@contextmanager
def get_db():
    conn = _get_raw_connection()
    wrapper = ConnectionWrapper(conn)
    _db_local.active_conn = wrapper
    try:
        yield wrapper
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise DatabaseError(str(e))
    finally:
        _db_local.active_conn = None
        conn.close()


def active_connection():
    return getattr(_db_local, 'active_conn', None)


def init_database():
    """Initialize the database with all required tables and default data."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                reset_token TEXT,
                reset_token_expires TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                unit TEXT,
                quantity INTEGER DEFAULT 0,
                brand TEXT,
                condition_status TEXT,
                chanter TEXT,
                storage_zone TEXT,
                notes TEXT,
                supplier_name TEXT,
                bc_number TEXT,
                bl_number TEXT,
                n_facture TEXT,
                type_achat TEXT,
                expiration_date DATE,
                min_quantity INTEGER DEFAULT 0,
                deleted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                workshop_id INTEGER,
                UNIQUE(code, workshop_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                movement_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                notes TEXT,
                user_id INTEGER NOT NULL,
                supplier_name TEXT,
                bc_number TEXT,
                bl_number TEXT,
                n_facture TEXT,
                type_achat TEXT,
                chantier_exp_recep TEXT,
                nom_donneur_ordre TEXT,
                nom_magasinier TEXT,
                nom_chauffeur TEXT,
                matricule TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                notify_achat_par_bc INTEGER DEFAULT 1,
                notify_achat_par_caisse INTEGER DEFAULT 1,
                notify_achat_a_regulariser INTEGER DEFAULT 1,
                notify_transfert INTEGER DEFAULT 1,
                notify_product_deletion INTEGER DEFAULT 1,
                notify_product_expiration INTEGER DEFAULT 1,
                notify_transfert_exit INTEGER DEFAULT 1,
                notify_consumption INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recipient_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL REFERENCES notification_recipients(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                notify_achat_par_bc INTEGER DEFAULT 1,
                notify_achat_par_caisse INTEGER DEFAULT 1,
                notify_achat_a_regulariser INTEGER DEFAULT 1,
                notify_transfert INTEGER DEFAULT 1,
                notify_product_deletion INTEGER DEFAULT 1,
                notify_product_expiration INTEGER DEFAULT 1,
                notify_transfert_exit INTEGER DEFAULT 1,
                notify_consumption INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration: migrate existing emails to recipient_emails
        existing = query('SELECT id, email, notify_achat_par_bc, notify_achat_par_caisse, notify_achat_a_regulariser, notify_transfert, notify_product_deletion, notify_product_expiration, notify_transfert_exit, notify_consumption FROM notification_recipients WHERE email != ""')
        for row in existing:
            cnt = query_one('SELECT COUNT(*) FROM recipient_emails WHERE recipient_id = ? AND email = ?', (row[0], row[1]))
            if not cnt or cnt[0] == 0:
                execute('''
                    INSERT INTO recipient_emails (recipient_id, email, active, notify_achat_par_bc, notify_achat_par_caisse,
                        notify_achat_a_regulariser, notify_transfert, notify_product_deletion,
                        notify_product_expiration, notify_transfert_exit, notify_consumption)
                    VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9]))

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_email TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                content TEXT,
                product_id INTEGER,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'sent',
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                details TEXT,
                user_id INTEGER,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT NOT NULL,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_counts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                theoretical_qty INTEGER NOT NULL,
                actual_qty INTEGER NOT NULL,
                difference INTEGER NOT NULL,
                notes TEXT,
                counted_by TEXT NOT NULL,
                counted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        ''')

        _workshops_table(cursor)
        _categories_table(cursor)
        _suppliers_table(cursor)
        _add_missing_columns(cursor)
        _create_default_admin(cursor)


def _workshops_table(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workshops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            location TEXT DEFAULT '',
            city TEXT DEFAULT '',
            description TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existing = cursor.execute('SELECT COUNT(*) FROM workshops').fetchone()[0]
    if existing == 0:
        cursor.execute(
            'INSERT INTO workshops (name, location, city, description) VALUES (?, ?, ?, ?)',
            ('Atelier Principal', 'Principal', '', 'Atelier principal par défaut')
        )
        default_ws_id = cursor.lastrowid
        add_workshop_id = IS_POSTGRES and 'ALTER TABLE users ADD COLUMN IF NOT EXISTS workshop_id INTEGER REFERENCES workshops(id)' or 'ALTER TABLE users ADD COLUMN workshop_id INTEGER'
        try:
            if IS_POSTGRES:
                cursor.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS workshop_id INTEGER')
            else:
                cursor.execute('ALTER TABLE users ADD COLUMN workshop_id INTEGER')
        except Exception:
            pass
        try:
            if IS_POSTGRES:
                cursor.execute('ALTER TABLE products ADD COLUMN IF NOT EXISTS workshop_id INTEGER')
            else:
                cursor.execute('ALTER TABLE products ADD COLUMN workshop_id INTEGER')
        except Exception:
            pass
        try:
            if IS_POSTGRES:
                cursor.execute('ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS workshop_id INTEGER')
            else:
                cursor.execute('ALTER TABLE stock_movements ADD COLUMN workshop_id INTEGER')
        except Exception:
            pass
        try:
            if IS_POSTGRES:
                cursor.execute('ALTER TABLE notification_recipients ADD COLUMN IF NOT EXISTS workshop_id INTEGER')
            else:
                cursor.execute('ALTER TABLE notification_recipients ADD COLUMN workshop_id INTEGER')
        except Exception:
            pass
        cursor.execute('UPDATE users SET workshop_id = ? WHERE workshop_id IS NULL', (default_ws_id,))
        cursor.execute('UPDATE products SET workshop_id = ? WHERE workshop_id IS NULL', (default_ws_id,))
        cursor.execute('UPDATE stock_movements SET workshop_id = ? WHERE workshop_id IS NULL', (default_ws_id,))
    else:
        _add_workshop_columns(cursor)


def _add_workshop_columns(cursor):
    for table, col in [('users', 'workshop_id'), ('products', 'workshop_id'),
                       ('stock_movements', 'workshop_id'), ('notification_recipients', 'workshop_id')]:
        try:
            if IS_POSTGRES:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} INTEGER')
            else:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {col} INTEGER')
        except Exception:
            pass


def _categories_table(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    existing = cursor.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
    if existing == 0:
        for cat in ['Électronique', 'Mécanique', 'Consommables', 'Outils', 'Sécurité', 'Informatique', 'Électricité', 'Plomberie']:
            if IS_POSTGRES:
                cursor.execute('INSERT INTO categories (name) VALUES (%s) ON CONFLICT DO NOTHING', (cat,))
            else:
                cursor.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))


def _suppliers_table(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            contact_name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def _add_missing_columns(cursor):
    migrations = [
        'ALTER TABLE notification_recipients ADD COLUMN notify_product_deletion INTEGER DEFAULT 1',
        'ALTER TABLE notification_recipients ADD COLUMN notify_product_expiration INTEGER DEFAULT 1',
        'ALTER TABLE notification_recipients ADD COLUMN notify_transfert_exit INTEGER DEFAULT 1',
        'ALTER TABLE notification_recipients ADD COLUMN notify_consumption INTEGER DEFAULT 1',
        'ALTER TABLE stock_movements ADD COLUMN chantier_exp_recep TEXT',
        'ALTER TABLE stock_movements ADD COLUMN nom_donneur_ordre TEXT',
        'ALTER TABLE stock_movements ADD COLUMN nom_magasinier TEXT',
        'ALTER TABLE stock_movements ADD COLUMN nom_chauffeur TEXT',
        'ALTER TABLE stock_movements ADD COLUMN matricule TEXT',
        'ALTER TABLE products ADD COLUMN min_quantity INTEGER DEFAULT 0',
        'ALTER TABLE products ADD COLUMN deleted_at TIMESTAMP',
        'ALTER TABLE products ADD COLUMN image_path TEXT',
        'ALTER TABLE products ADD COLUMN created_by INTEGER',
    ]
    for migration in migrations:
        try:
            if IS_POSTGRES:
                cursor.execute(migration.replace('ADD COLUMN', 'ADD COLUMN IF NOT EXISTS'))
            else:
                cursor.execute(migration)
        except Exception:
            if not IS_POSTGRES:
                import sqlite3
                if not isinstance(sys.exc_info()[1], sqlite3.OperationalError):
                    raise
    _rebuild_products_uniqueness(cursor)


def _rebuild_products_uniqueness(cursor):
    """Change UNIQUE(code) to UNIQUE(code, workshop_id) for multi-workshop support."""
    if IS_POSTGRES:
        try:
            cursor.execute('ALTER TABLE products DROP CONSTRAINT IF EXISTS products_code_key')
            cursor.execute('ALTER TABLE products ADD UNIQUE (code, workshop_id)')
        except Exception:
            pass
        return
    try:
        cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="products"')
        create_sql = cursor.fetchone()[0]
        if 'UNIQUE(code, workshop_id)' in create_sql:
            return
        cursor.execute('PRAGMA foreign_keys=OFF')
        cursor.execute('DROP TABLE IF EXISTS products_new')
        cursor.execute('''
            CREATE TABLE products_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                unit TEXT,
                quantity INTEGER DEFAULT 0,
                brand TEXT,
                condition_status TEXT,
                chanter TEXT,
                storage_zone TEXT,
                notes TEXT,
                supplier_name TEXT,
                bc_number TEXT,
                bl_number TEXT,
                n_facture TEXT,
                type_achat TEXT,
                expiration_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                image_path TEXT,
                min_quantity INTEGER DEFAULT 0,
                deleted_at TIMESTAMP,
                workshop_id INTEGER,
                created_by INTEGER,
                UNIQUE(code, workshop_id)
            )
        ''')
        # Get column names from old products table
        cursor.execute('PRAGMA table_info(products)')
        old_cols = [row[1] for row in cursor.fetchall()]
        # Map old columns to new columns (with defaults for missing ones)
        new_cols = ['id','code','name','category','unit','quantity','brand',
                    'condition_status','chanter','storage_zone','notes',
                    'supplier_name','bc_number','bl_number','n_facture',
                    'type_achat','expiration_date','created_at','updated_at',
                    'image_path','min_quantity','deleted_at','workshop_id']
        common_cols = [c for c in new_cols if c in old_cols]
        select_list = ', '.join(common_cols)
        insert_list = ', '.join(common_cols)
        cursor.execute(f'INSERT OR IGNORE INTO products_new ({insert_list}) SELECT {select_list} FROM products')
        cursor.execute('DROP TABLE products')
        cursor.execute('ALTER TABLE products_new RENAME TO products')
        cursor.execute('PRAGMA foreign_keys=ON')
        logger.info("Migrated products table to UNIQUE(code, workshop_id)")
    except Exception:
        cursor.execute('PRAGMA foreign_keys=ON')
        logger.error("Failed to migrate products table", exc_info=True)


def _create_default_admin(cursor):
    cursor.execute('SELECT COUNT(*) FROM users WHERE username = %s' if IS_POSTGRES else 'SELECT COUNT(*) FROM users WHERE username = ?', (DEFAULT_ADMIN_USERNAME,))
    if cursor.fetchone()[0] == 0:
        password_hash = generate_password_hash(DEFAULT_ADMIN_PASSWORD)
        cursor.execute(
            'INSERT INTO users (username, password_hash, email, role) VALUES (%s, %s, %s, %s)' if IS_POSTGRES else 'INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, ?)',
            (DEFAULT_ADMIN_USERNAME, password_hash, DEFAULT_ADMIN_EMAIL, 'principal_admin')
        )
        logger.info(f"Created default admin user: {DEFAULT_ADMIN_USERNAME}")

        cursor.execute('SELECT COUNT(*) FROM notification_recipients WHERE email = %s' if IS_POSTGRES else 'SELECT COUNT(*) FROM notification_recipients WHERE email = ?', (DEFAULT_ADMIN_EMAIL,))
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO notification_recipients
                (name, email, active, notify_achat_par_bc, notify_achat_par_caisse,
                 notify_achat_a_regulariser, notify_transfert, notify_consumption,
                 notify_product_deletion, notify_product_expiration)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''' if IS_POSTGRES else '''
                INSERT INTO notification_recipients
                (name, email, active, notify_achat_par_bc, notify_achat_par_caisse,
                 notify_achat_a_regulariser, notify_transfert, notify_consumption,
                 notify_product_deletion, notify_product_expiration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('Admin', DEFAULT_ADMIN_EMAIL, 1, 1, 1, 1, 1, 1, 1, 1))


def query(sql: str, params: tuple = ()) -> List:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()


def query_one(sql: str, params: tuple = ()) -> Optional:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.lastrowid


def execute_many(sql: str, params_list: List[tuple]):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.executemany(sql, params_list)
