import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    """إعدادات التطبيق العامة، تُقرأ من متغيرات البيئة عند توفرها."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me-in-production")

    DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "app.db"))

    # إعدادات البريد - كلها تُقرأ من البيئة، لا توجد بيانات حقيقية في الكود
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")  # App Password من Gmail
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_USERNAME")

    OTP_EXPIRY_SECONDS = 10 * 60  # صلاحية كود التحقق: 10 دقائق

    # حسابات افتراضية تُنشأ أول مرة فقط (غيّرها في البيئة قبل النشر الحقيقي)
    DEFAULT_ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@example.com")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "ChangeMe123!")

    # البريد الوحيد المسموح له بدخول لوحة المالك الخاصة — غيّره لبريدك
    OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "ziadmsm2007@gmail.com")

    # نظام الإسكرو — عمولة المنصة 20%، والباقي للفني
    COMMISSION_RATE = float(os.environ.get("COMMISSION_RATE", 0.20))
    # حساباتك اللي العميل هيدفع عليها (غيّرها لرقمك الحقيقي)
    OWNER_VODAFONE_CASH = os.environ.get("OWNER_VODAFONE_CASH", "01000000000")
    OWNER_INSTAPAY = os.environ.get("OWNER_INSTAPAY", "ziadmsm2007@instapay")
    OWNER_BANK_ACCOUNT = os.environ.get("OWNER_BANK_ACCOUNT", "")

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "photos")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
