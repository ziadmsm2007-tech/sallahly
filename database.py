import sqlite3
import uuid
from contextlib import contextmanager

from werkzeug.security import generate_password_hash

from config import Config


@contextmanager
def get_db():
    """Context manager يفتح اتصال بقاعدة البيانات ويقفله تلقائياً."""
    conn = sqlite3.connect(Config.DATABASE)
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


def init_db():
    """إنشاء الجداول وحسابات تجريبية افتراضية (مرة واحدة فقط)."""
    with get_db() as conn:
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        phone TEXT,
                        governorate TEXT,
                        city TEXT,
                        address TEXT,
                        lat REAL,
                        lng REAL,
                        created_at REAL DEFAULT (strftime('%s','now')))''')

        # ترقية جدول المستخدمين — موقع المحافظة
        for col, ddl in [
            ("governorate", "ALTER TABLE users ADD COLUMN governorate TEXT"),
            ("city", "ALTER TABLE users ADD COLUMN city TEXT"),
            ("address", "ALTER TABLE users ADD COLUMN address TEXT"),
            ("lat", "ALTER TABLE users ADD COLUMN lat REAL"),
            ("lng", "ALTER TABLE users ADD COLUMN lng REAL"),
        ]:
            try:
                cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
                if col not in cols:
                    c.execute(ddl)
            except Exception:
                pass

        c.execute('''CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_id INTEGER NOT NULL,
                        customer_id INTEGER NOT NULL,
                        technician_id INTEGER,
                        name TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        location TEXT NOT NULL,
                        lat REAL,
                        lng REAL,
                        car_make TEXT,
                        car_model TEXT,
                        car_year TEXT,
                        fault_photo TEXT,
                        gateway_txn TEXT,
                        payment_method TEXT NOT NULL DEFAULT 'Pending',
                        service_name TEXT,
                        service_price REAL,
                        status TEXT DEFAULT 'Pending',
                        payment_status TEXT DEFAULT 'Unpaid',
                        created_at REAL DEFAULT (strftime('%s','now')),
                        FOREIGN KEY (customer_id) REFERENCES users (id),
                        FOREIGN KEY (technician_id) REFERENCES users (id))''')

        # ترقية لجداول قديمة — الدفع بعد الخدمة + إسكرو + موقع + عربية
        for col, ddl in [
            ("lat", "ALTER TABLE orders ADD COLUMN lat REAL"),
            ("lng", "ALTER TABLE orders ADD COLUMN lng REAL"),
            ("payment_status", "ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'Unpaid'"),
            ("payout_status", "ALTER TABLE orders ADD COLUMN payout_status TEXT DEFAULT 'Pending'"),
            ("car_make", "ALTER TABLE orders ADD COLUMN car_make TEXT"),
            ("car_model", "ALTER TABLE orders ADD COLUMN car_model TEXT"),
            ("car_year", "ALTER TABLE orders ADD COLUMN car_year TEXT"),
        ]:
            try:
                cols = [r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()]
                if col not in cols:
                    c.execute(ddl)
            except Exception:
                pass

        # محفظة الفني — زي أوبر: خصم مباشر 20%
        c.execute('''CREATE TABLE IF NOT EXISTS wallets (
                        user_id INTEGER PRIMARY KEY,
                        balance REAL NOT NULL DEFAULT 0,
                        FOREIGN KEY (user_id) REFERENCES users (id))''')

        # موافقة الفني + صورة + تقييم + حجز بميعاد + شات + إشعارات + OTP + كوبون
        for col, ddl in [
            ("photo", "ALTER TABLE users ADD COLUMN photo TEXT"),
            ("rating_avg", "ALTER TABLE users ADD COLUMN rating_avg REAL DEFAULT 0"),
            ("rating_count", "ALTER TABLE users ADD COLUMN rating_count INTEGER DEFAULT 0"),
            ("is_approved", "ALTER TABLE users ADD COLUMN is_approved INTEGER DEFAULT 1"),
            ("points", "ALTER TABLE users ADD COLUMN points INTEGER DEFAULT 0"),
            ("fcm_token", "ALTER TABLE users ADD COLUMN fcm_token TEXT"),
            ("referral_code", "ALTER TABLE users ADD COLUMN referral_code TEXT"),
            ("referred_by", "ALTER TABLE users ADD COLUMN referred_by INTEGER"),
        ]:
            try:
                cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
                if col not in cols:
                    c.execute(ddl)
            except Exception:
                pass
        for col, ddl in [
            ("otp_code", "ALTER TABLE orders ADD COLUMN otp_code TEXT"),
            ("gateway_txn", "ALTER TABLE orders ADD COLUMN gateway_txn TEXT"),
        ]:
            try:
                cols = [r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()]
                if col not in cols:
                    c.execute(ddl)
            except Exception:
                pass
        # كود إحالة لكل مستخدم قديم
        try:
            for r in c.execute("SELECT id FROM users WHERE referral_code IS NULL").fetchall():
                code = f"DR{str(r[0]).zfill(4)}{uuid.uuid4().hex[:3].upper()}"
                c.execute("UPDATE users SET referral_code=? WHERE id=?", (code, r[0]))
        except:
            pass
        for col, ddl in [
            ("fault_photo", "ALTER TABLE orders ADD COLUMN fault_photo TEXT"),
            ("gateway_txn", "ALTER TABLE orders ADD COLUMN gateway_txn TEXT"),
        ]:
            try:
                cols = [r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()]
                if col not in cols:
                    c.execute(ddl)
            except Exception:
                pass
        # الفنيين الجدد غير موافق عليهم افتراضياً
        try:
            c.execute("UPDATE users SET is_approved=0 WHERE role='technician' AND is_approved IS NULL")
        except:
            pass

        for col, ddl in [
            ("scheduled_at", "ALTER TABLE orders ADD COLUMN scheduled_at TEXT"),
            ("rating", "ALTER TABLE orders ADD COLUMN rating INTEGER"),
            ("review", "ALTER TABLE orders ADD COLUMN review TEXT"),
            ("coupon_code", "ALTER TABLE orders ADD COLUMN coupon_code TEXT"),
            ("discount", "ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0"),
            ("otp_code", "ALTER TABLE orders ADD COLUMN otp_code TEXT"),
            ("tech_lat", "ALTER TABLE orders ADD COLUMN tech_lat REAL"),
            ("tech_lng", "ALTER TABLE orders ADD COLUMN tech_lng REAL"),
        ]:
            try:
                cols = [r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()]
                if col not in cols:
                    c.execute(ddl)
            except Exception:
                pass

        c.execute('''CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        sender_id INTEGER NOT NULL,
                        message TEXT NOT NULL,
                        photo TEXT,
                        created_at REAL DEFAULT (strftime('%s','now')),
                        FOREIGN KEY (order_id) REFERENCES orders (id),
                        FOREIGN KEY (sender_id) REFERENCES users (id))''')
        for col, ddl in [("photo", "ALTER TABLE messages ADD COLUMN photo TEXT")]:
            try:
                cols = [r[1] for r in c.execute("PRAGMA table_info(messages)").fetchall()]
                if col not in cols:
                    c.execute(ddl)
            except:
                pass

        c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        amount REAL NOT NULL,
                        commission REAL NOT NULL,
                        method TEXT NOT NULL,
                        txn_id TEXT UNIQUE,
                        status TEXT DEFAULT 'escrow',
                        created_at REAL DEFAULT (strftime('%s','now')),
                        FOREIGN KEY (order_id) REFERENCES orders (id))''')

        c.execute('''CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        body TEXT,
                        is_read INTEGER DEFAULT 0,
                        created_at REAL DEFAULT (strftime('%s','now')),
                        FOREIGN KEY (user_id) REFERENCES users (id))''')

        c.execute('''CREATE TABLE IF NOT EXISTS coupons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT UNIQUE NOT NULL,
                        discount_percent INTEGER NOT NULL,
                        max_uses INTEGER DEFAULT 100,
                        used_count INTEGER DEFAULT 0,
                        valid_until TEXT,
                        governorate TEXT,
                        created_at REAL DEFAULT (strftime('%s','now')))''')
        # كوبونات افتراضية
        for code, pct in [("ZAYED20", 20), ("TAGAMOA15", 15), ("WELCOME10", 10)]:
            try:
                c.execute("INSERT OR IGNORE INTO coupons (code, discount_percent, governorate) VALUES (?, ?, ?)",
                          (code, pct, "التجمع" if "TAGAMOA" in code else "الشيخ زايد" if "ZAYED" in code else None))
            except:
                pass

        seed_users = [
            (Config.DEFAULT_ADMIN_EMAIL, "Admin", Config.DEFAULT_ADMIN_PASSWORD, "admin"),
            ("client@example.com", "Client User", "ChangeMe123!", "client"),
            ("tech@example.com", "Technician User", "ChangeMe123!", "technician"),
        ]
        for email, name, password, role in seed_users:
            existing = c.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if not existing:
                c.execute(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                    (name, email, generate_password_hash(password), role),
                )
