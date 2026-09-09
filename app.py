import hashlib
import os
import random
import time
from datetime import datetime

from werkzeug.utils import secure_filename
import uuid

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_from_directory,
)

from config import Config
from database import init_db
import models
import math

EGYPT_GOVERNORATES = [
    "القاهرة", "الجيزة", "الإسكندرية", "الدقهلية", "البحر الأحمر", "البحيرة", "الفيوم", "الغربية",
    "الإسماعيلية", "المنوفية", "المنيا", "القليوبية", "الوادي الجديد", "السويس", "أسوان", "أسيوط",
    "بني سويف", "بورسعيد", "دمياط", "الشرقية", "جنوب سيناء", "كفر الشيخ", "مطروح", "الأقصر", "قنا", "شمال سيناء", "سوهاج"
]

def haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))
from mailer import init_mail, send_otp_email
from auth import login_required, role_required, owner_required, get_current_user
from services_data import (
    categories,
    get_service_by_id,
    get_all_services,
    localize_service,
    localize_category,
    localize_categories,
    get_localized_service_by_id,
    get_localized_services,
    get_services_by_category,
    get_category_key,
    get_category_for_service,
    get_visual_for_service,
    get_image_for_service,
    get_adjusted_price,
    get_car_tier,
    TIER_MULT,
    CAR_TIERS,
    CAR_MAKES,
    get_car_makes,
    MOTORCYCLE_MAKES,
    get_motorcycle_makes,
)
from i18n import LANGUAGES, LANG_DIR, get_lang, make_t


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    init_mail(app)
    register_routes(app)
    init_db()
    return app


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def save_photo(file):
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(Config.UPLOAD_FOLDER, fname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file.save(path)
    return f"uploads/photos/{fname}"


def save_fault_photo(file):
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    fname = f"{uuid.uuid4().hex}.{ext}"
    folder = os.path.join(os.path.dirname(__file__), "static", "uploads", "faults")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, fname)
    file.save(path)
    return f"uploads/faults/{fname}"


def _hash_otp(otp):
    return hashlib.sha256(otp.encode()).hexdigest()


PAYMENT_METHODS = [
    {"value": "Secure", "label_key": "pay_secure", "icon": "🔒"},
    {"value": "Cash", "label_key": "pay_cash", "icon": "💵"},
]


def register_routes(app):

    @app.context_processor
    def inject_globals():
        lang = get_lang()
        cur = get_current_user()
        unread = 0
        try:
            if cur:
                unread = models.get_unread_count(cur["id"])
        except:
            unread = 0
        return {
            "current_user": cur,
            "lang": lang,
            "lang_dir": LANG_DIR.get(lang, "ltr"),
            "t": make_t(lang),
            "LANGUAGES": LANGUAGES,
            "localize_service": localize_service,
            "localize_category": localize_category,
            "payment_methods": PAYMENT_METHODS,
            "owner_email": (Config.OWNER_EMAIL or "").lower(),
            "commission_rate": Config.COMMISSION_RATE,
            "owner_vodafone": Config.OWNER_VODAFONE_CASH,
            "owner_instapay": Config.OWNER_INSTAPAY,
            "unread_notifications": unread,
            "cart_count": len(session.get("cart", [])),
        }

    # -----------------------------------------------------------------
    # Language switcher
    # -----------------------------------------------------------------
    @app.route("/lang/<code>")
    def set_lang(code):
        if code in LANGUAGES:
            session["lang"] = code
            resp = redirect(request.referrer or url_for("landing"))
            resp.set_cookie("lang", code, max_age=365 * 24 * 3600)
            return resp
        return redirect(url_for("landing"))

    # -----------------------------------------------------------------
    # Public pages
    # -----------------------------------------------------------------
    @app.route("/")
    def index():
        return redirect(url_for("landing"))

    @app.route("/landing")
    def landing():
        lang = get_lang()
        cats = localize_categories(categories, lang)
        # آراء حقيقية من التقييمات
        testimonials = []
        try:
            with models.get_db() as conn:
                rows = conn.execute("""
                    SELECT o.rating, o.review, o.service_name, u.name, u.photo
                    FROM orders o JOIN users u ON u.id=o.customer_id
                    WHERE o.rating IS NOT NULL ORDER BY o.created_at DESC LIMIT 6
                """).fetchall()
                testimonials = [dict(r) for r in rows]
        except:
            testimonials = []
        return render_template("landing.html", landing_categories=cats, testimonials=testimonials)

    @app.route("/overview")
    def overview():
        return render_template("overview.html")

    @app.route("/contact_us", methods=["GET", "POST"])
    def contact_us():
        if request.method == "POST":
            flash("flash_contact_thanks")
            return redirect(url_for("contact_us"))
        return render_template("contact_us.html")

    # -----------------------------------------------------------------
    # Auth
    # -----------------------------------------------------------------
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "client").strip().lower()
            governorate = request.form.get("governorate", "").strip()
            city = request.form.get("city", "").strip()
            address = request.form.get("address", "").strip()
            lat = request.form.get("lat", "").strip()
            lng = request.form.get("lng", "").strip()
            try:
                lat = float(lat) if lat else None
                lng = float(lng) if lng else None
            except:
                lat, lng = None, None

            referral_input = request.form.get("referral_code", "").strip().upper()
            photo = None
            if role == "technician" and "photo" in request.files:
                photo = save_photo(request.files["photo"])

            if role not in ("client", "technician"):
                role = "client"  # الأدمن لا يُنشأ من صفحة التسجيل العامة

            if not name or not email or not password or not governorate:
                flash("flash_fill_fields")
                return redirect(url_for("register"))
            if len(password) < 6:
                flash("flash_pass_short")
                return redirect(url_for("register"))

            if models.get_user_by_email(email):
                flash("flash_email_exists")
                return redirect(url_for("login"))

            models.create_user(name, email, password, role, governorate, city, address, lat, lng, photo, referral_input or None)
            flash("flash_reg_ok")
            return redirect(url_for("login"))

        return render_template("register.html", governorates=EGYPT_GOVERNORATES)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            user = models.verify_user(email, password)
            if user:
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                session["name"] = user["name"]

                if user["role"] == "client":
                    return redirect(url_for("customer_dashboard"))
                elif user["role"] == "technician":
                    return redirect(url_for("technical_dashboard"))
                elif user["role"] == "admin":
                    return redirect(url_for("admin_dashboard"))
                flash("flash_role_unknown")
                return redirect(url_for("login"))

            flash("flash_invalid_creds")
            return redirect(url_for("login"))

        return render_template("login.html")

    @app.route("/sw.js")
    def sw():
        return send_from_directory(os.path.join(app.static_folder), "sw.js", mimetype="application/javascript")

    @app.route("/save_fcm_token", methods=["POST"])
    @login_required
    def save_fcm_token():
        data = request.get_json(silent=True) or {}
        token = data.get("token", "").strip()
        if token:
            with models.get_db() as conn:
                conn.execute("UPDATE users SET fcm_token=? WHERE id=?", (token, session["user_id"]))
        return {"ok": True}

    @app.route("/notifications")
    @login_required
    def notifications_page():
        notes = models.get_notifications(session["user_id"], limit=20)
        # mark as read when viewed
        try:
            models.mark_notifications_read(session["user_id"])
        except:
            pass
        return render_template("notifications.html", notifications=notes)

    @app.route("/logout")
    def logout():
        session.clear()
        flash("flash_logout")
        return redirect(url_for("landing"))

    @app.route("/forgot_password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = models.get_user_by_email(email)

            # نفس الرسالة سواء الإيميل موجود أو لا، لمنع كشف وجود الحساب من عدمه
            if user:
                otp = f"{random.randint(100000, 999999)}"
                session["otp_hash"] = _hash_otp(otp)
                session["otp_expires"] = time.time() + Config.OTP_EXPIRY_SECONDS
                session["reset_email"] = email
                send_otp_email(app, email, otp)

            flash("flash_otp_sent")
            return redirect(url_for("verify_otp"))
        return render_template("forgot_password.html")

    @app.route("/verify_otp", methods=["GET", "POST"])
    def verify_otp():
        if request.method == "POST":
            entered = request.form.get("otp", "").strip()
            stored_hash = session.get("otp_hash")
            expires = session.get("otp_expires", 0)

            if not stored_hash or time.time() > expires:
                flash("flash_otp_expired")
                return redirect(url_for("forgot_password"))

            if _hash_otp(entered) != stored_hash:
                flash("flash_otp_invalid")
                return redirect(url_for("verify_otp"))

            session.pop("otp_hash", None)
            session.pop("otp_expires", None)
            session["otp_verified"] = True
            return redirect(url_for("reset_password"))

        return render_template("verify_otp.html")

    @app.route("/reset_password", methods=["GET", "POST"])
    def reset_password():
        if not session.get("otp_verified") or not session.get("reset_email"):
            flash("flash_verify_first")
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            new_password = request.form.get("new_password", "")
            if len(new_password) < 6:
                flash("flash_pass_short")
                return redirect(url_for("reset_password"))

            models.update_user_password(session["reset_email"], new_password)
            flash("flash_pass_reset")

            session.pop("otp_verified", None)
            session.pop("reset_email", None)
            return redirect(url_for("login"))

        return render_template("reset_password.html")

    # -----------------------------------------------------------------
    # Client area
    # -----------------------------------------------------------------
    @app.route("/customer_dashboard")
    @login_required
    def customer_dashboard():
        lang = get_lang()
        my_recent_orders = models.get_orders_by_customer(session["user_id"], limit=5)
        # الخانات الرئيسية: عربيات / مكن / ونش / كهرباء — إنجليزي في EN وعربي في AR
        from services_data import MAIN_GROUPS, MAIN_GROUPS_AR, MAIN_GROUP_ICONS
        main_groups = {}
        for gname, subcats in MAIN_GROUPS.items():
            total = sum(len(categories.get(c, [])) for c in subcats)
            display = MAIN_GROUPS_AR.get(gname, gname) if lang == "ar" else gname
            main_groups[display] = {"key": gname, "icon": MAIN_GROUP_ICONS.get(gname, "🔧"), "count": total, "subcats": subcats}
        cats = localize_categories(categories, lang)
        cats_meta = {localize_category(k, lang): k for k in categories}
        return render_template(
            "customer_dashboard.html",
            categories=cats,
            orders=my_recent_orders,
            cats_meta=cats_meta,
            main_groups=main_groups,
        )

    @app.route("/customer_services")
    @login_required
    def customer_services():
        lang = get_lang()
        cat_key = get_category_key(request.args.get("cat", "").strip())
        group = request.args.get("group", "").strip()
        from services_data import MAIN_GROUPS
        if group and group in MAIN_GROUPS:
            services = []
            for sub in MAIN_GROUPS[group]:
                services.extend(get_services_by_category(sub, lang))
            active_cat = group
        elif cat_key:
            services = get_services_by_category(cat_key, lang)
            active_cat = localize_category(cat_key, lang)
        else:
            services = get_localized_services(lang)
            active_cat = None
        # الكتالوج يعرض السعر الأساسي (فئة عادية) — السعر النهائي حسب عربية العميل في صفحة الطلب
        # للكهربائي السعر يحدده الفني بعد المعاينة
        services = [{**s, "base_price": get_adjusted_price(s["base_price"]) if not s.get("variable_price") else 0} for s in services]
        return render_template(
            "services_catalog.html",
            services=services,
            active_cat=active_cat,
            all_categories=categories,
        )

    # Amazon-like Cart — تحفظ في الجلسة
    def get_cart():
        return session.get("cart", [])

    def set_cart(cart):
        session["cart"] = cart
        session.modified = True

    @app.route("/cart/add/<int:service_id>", methods=["POST"])
    @login_required
    def add_to_cart(service_id):
        cart = get_cart()
        if service_id not in cart:
            cart.append(service_id)
            set_cart(cart)
            flash("تمت الإضافة للسلة ✅")
        return redirect(request.referrer or url_for("cart_page"))

    @app.route("/cart/remove/<int:service_id>", methods=["POST"])
    @login_required
    def remove_from_cart(service_id):
        cart = get_cart()
        if service_id in cart:
            cart.remove(service_id)
            set_cart(cart)
        return redirect(url_for("cart_page"))

    @app.route("/cart")
    @login_required
    def cart_page():
        lang = get_lang()
        cart = get_cart()
        services = [get_localized_service_by_id(sid, lang) for sid in cart]
        services = [s for s in services if s]
        # السعر الأساسي للعرض — النهائي حسب العربية في الـ checkout
        cur = get_current_user()
        gov = cur.get("governorate") if cur else None
        city = cur.get("city") if cur else None
        total_base = sum(s["base_price"] for s in services)
        return render_template("cart.html", services=services, total_base=total_base)

    @app.route("/checkout", methods=["GET", "POST"])
    @login_required
    def checkout():
        lang = get_lang()
        cart = get_cart()
        if not cart:
            flash("السلة فارغة")
            return redirect(url_for("customer_services"))
        services = [get_localized_service_by_id(sid, lang) for sid in cart]
        services = [s for s in services if s]
        cur = get_current_user()
        if request.method == "GET":
            # لو السلة فيها مكن، اعرض مكن كمان
            has_motor = any(get_category_for_service(s["id"]) == "Motorcycles" for s in services)
            makes_dict = {**CAR_MAKES, **MOTORCYCLE_MAKES} if has_motor else CAR_MAKES
            makes_list = sorted(makes_dict.keys())
            car_tier_map = {make: get_car_tier(make) for make in makes_dict}
            return render_template("checkout.html", services=services, car_makes=makes_dict, car_makes_list=makes_list, tier_mult=TIER_MULT, car_tier_map=car_tier_map)
        # POST — تأكيد الطلب زي أمازون
        name = request.form.get("name", "").strip() or cur["name"]
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        lat = request.form.get("lat", "").strip()
        lng = request.form.get("lng", "").strip()
        scheduled_at = request.form.get("scheduled_at", "").strip()
        car_make = request.form.get("car_make", "").strip()
        car_model = request.form.get("car_model", "").strip()
        other_model = request.form.get("other_model", "").strip()
        if car_make == "Other" and other_model:
            car_model = other_model
        elif car_model == "Other model" and other_model:
            car_model = other_model
        car_year = request.form.get("car_year", "").strip()
        fault_file = request.files.get("fault_photo")
        fault_photo = save_fault_photo(fault_file) if fault_file and fault_file.filename else None
        try:
            lat = float(lat) if lat else None
            lng = float(lng) if lng else None
        except:
            lat, lng = None, None
        if not all([name, phone, location, car_make, car_model]):
            flash("flash_fill_fields")
            return redirect(url_for("checkout"))
        if not scheduled_at:
            scheduled_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
        # زي طلبات: الدفع عند الطلب
        payment_method = request.form.get("payment_method", "Cash").strip()
        coupon_code = request.form.get("coupon_code", "").strip().upper()
        if payment_method not in ("Cash", "Secure", "Card", "InstaPay"):
            payment_method = "Cash"
        if payment_method == "Card":
            payment_method = "Secure"
        discount_pct = 0
        if coupon_code:
            cp, err = models.validate_coupon(coupon_code, location)
            if not err:
                discount_pct = cp["discount_percent"]
        order_ids = []
        for svc in services:
            base = get_service_by_id(svc["id"])["base_price"]
            price = get_adjusted_price(base, car_make)
            if discount_pct:
                price = int(price * (100 - discount_pct) / 100)
            fp = fault_photo if svc == services[0] else None
            pay_status = "Paid" if payment_method in ("Secure", "InstaPay", "Card") else "Unpaid"
            payout = "Pending" if pay_status == "Paid" else "Pending"
            models.create_order(
                service_id=svc["id"], customer_id=session["user_id"], name=name, phone=phone,
                location=location, payment_method=payment_method, service_name=svc["name"],
                service_price=price, lat=lat, lng=lng, scheduled_at=scheduled_at,
                car_make=car_make, car_model=car_model, car_year=car_year or None, fault_photo=fp
            )
            oid = max(o["id"] for o in models.get_orders_by_customer(session["user_id"]))
            with models.get_db() as conn:
                conn.execute("UPDATE orders SET payment_status=?, payout_status=? WHERE id=?", (pay_status, payout, oid))
                if discount_pct:
                    conn.execute("UPDATE orders SET coupon_code=?, discount=? WHERE id=?", (coupon_code, int(get_service_by_id(svc["id"])["base_price"]*2.2* (1.6 if get_car_tier(car_make)=="luxury" else 1.25 if get_car_tier(car_make)=="mid" else 1.0) * discount_pct/100), oid))
                if pay_status == "Paid":
                    conn.execute("UPDATE orders SET gateway_txn=? WHERE id=?", (f"TAL-{oid}-{int(time.time())%10000}", oid))
            order_ids.append(oid)
        if discount_pct:
            models.use_coupon(coupon_code)
        # نقاط
        set_cart([])
        models.add_points(session["user_id"], len(services)*10)
        gov = cur.get("governorate") if cur else ""
        for oid in order_ids:
            o = models.get_order_by_id(oid)
            for tech in [u for u in models.get_all_users() if u["role"]=="technician" and (not gov or u.get("governorate")==gov)]:
                models.add_notification(tech["id"], f"طلب جديد: {o['service_name']}", f"من {name} — 🚗 {car_make} {car_model} — {payment_method}")
        flash("تم تأكيد الطلب ✅ — زي طلبات")
        return redirect(url_for("my_orders"))

    @app.route("/service/<int:service_id>")
    @login_required
    def service_details(service_id):
        lang = get_lang()
        service = get_localized_service_by_id(service_id, lang)
        if not service:
            return render_template("404.html"), 404
        cat_key = get_category_for_service(service_id)
        visual = get_visual_for_service(service_id)
        image_url = get_image_for_service(service_id)
        cat_name = localize_category(cat_key, lang) if cat_key else ""
        # صفحة التفاصيل تعرض السعر الأساسي — السعر النهائي حسب العربية في صفحة الطلب
        related = [s for s in get_services_by_category(cat_key, lang) if s["id"] != service_id][:4] if cat_key else []
        service = {**service, "base_price": get_adjusted_price(service["base_price"])}
        return render_template("service_details.html", service=service, cat_key=cat_key, cat_name=cat_name, visual=visual, image_url=image_url, related=related)

    @app.route("/order_service/<int:service_id>", methods=["GET", "POST"])
    @role_required("client")
    def order_service(service_id):
        lang = get_lang()
        service = get_localized_service_by_id(service_id, lang)
        if not service:
            return render_template("404.html"), 404
        # لو مكن اختار مكن، لو عربيات اختار عربيات
        cat_for_makes = get_category_for_service(service_id)
        is_motorcycle = cat_for_makes == "Motorcycles"
        makes_dict = MOTORCYCLE_MAKES if is_motorcycle else CAR_MAKES
        makes_list = get_motorcycle_makes() if is_motorcycle else get_car_makes()
        # صفحة الطلب: السعر الأساسي + مضاعفات الفئات للجافاسكربت (السعر يتحدث مع اختيار العربية)
        service_display = {**service, "base_price": get_adjusted_price(service["base_price"])}
        image_url = get_image_for_service(service_id)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            location = request.form.get("location", "").strip()
            lat = request.form.get("lat", "").strip()
            lng = request.form.get("lng", "").strip()
            scheduled_at = request.form.get("scheduled_at", "").strip()
            car_make = request.form.get("car_make", "").strip()
            car_model = request.form.get("car_model", "").strip()
            car_year = request.form.get("car_year", "").strip()
            fault_photo = None
            if "fault_photo" in request.files:
                fault_photo = save_fault_photo(request.files["fault_photo"])
            try:
                lat = float(lat) if lat else None
                lng = float(lng) if lng else None
            except:
                lat, lng = None, None

            # الكهرباء والسباكة لا يحتاجان عربية
            cat_for_check = get_category_for_service(service_id)
            needs_car = cat_for_check not in ("Electrician", "Plumbing")
            if needs_car:
                if not all([name, phone, location, car_make, car_model]):
                    flash("flash_fill_fields")
                    return redirect(url_for("order_service", service_id=service_id))
            else:
                if not all([name, phone, location]):
                    flash("flash_fill_fields")
                    return redirect(url_for("order_service", service_id=service_id))
                car_make = car_make or "Other"
                car_model = car_model or "Other model"
            # لو مختار "اطلب الآن" → الميعاد = دلوقتي
            if not scheduled_at:
                scheduled_at = datetime.now().strftime("%Y-%m-%dT%H:%M")

            # السعر النهائي حسب فئة العربية — الكهربائي سعره يحدده الفني بعد المعاينة
            raw = get_service_by_id(service_id)
            if raw.get("variable_price"):
                final_price = 0
            else:
                final_price = get_adjusted_price(raw["base_price"], car_make)
            car_label = f"{car_make} {car_model}" + (f" {car_year}" if car_year else "")
            models.create_order(
                service_id=service_id,
                customer_id=session["user_id"],
                name=name,
                phone=phone,
                location=location,
                payment_method="Pending",
                service_name=raw["name"],
                service_price=final_price,
                lat=lat,
                lng=lng,
                scheduled_at=scheduled_at,
                car_make=car_make,
                car_model=car_model,
                car_year=car_year or None,
                fault_photo=fault_photo,
            )
            # إشعار للفنيين القريبين فقط — نفس المحافظة
            cust = models.get_user_by_id(session["user_id"])
            gov = cust.get("governorate") if cust else ""
            for tech in [u for u in models.get_all_users() if u["role"]=="technician" and (not gov or u.get("governorate")==gov)]:
                models.add_notification(tech["id"], f"طلب جديد: {raw['name']}", f"من {name} في {gov or location} — 🚗 {car_label} — ميعاد: {scheduled_at} — السعر: {final_price} ج.م")

            flash("flash_order_placed")
            return redirect(url_for("my_orders"))

        car_tier_map = {make: tier for tier, makes in CAR_TIERS.items() for make in makes}
        is_variable = service.get("variable_price", False)
        cat_for_hide = get_category_for_service(service_id)
        hide_car = cat_for_hide in ("Electrician", "Plumbing")
        return render_template("order_form.html", service=service_display, raw_price=service["base_price"], image_url=image_url, car_makes=makes_dict, car_makes_list=makes_list, tier_mult=TIER_MULT, car_tier_map=car_tier_map, is_variable=is_variable, hide_car=hide_car)

    @app.route("/my_orders")
    @role_required("client")
    def my_orders():
        orders = models.get_orders_by_customer(session["user_id"])
        return render_template("my_orders.html", orders=orders)

    @app.route("/track_order/<int:order_id>")
    @role_required("client")
    def track_order(order_id):
        lang = get_lang()
        order = models.get_order_by_id(order_id)
        if not order:
            return render_template("404.html"), 404
        if order["customer_id"] != session["user_id"]:
            flash("flash_no_access")
            return redirect(url_for("my_orders"))

        step_order = ["Pending", "In Progress", "Awaiting Payment", "Completed"]
        # Completed يظهر فقط بعد الدفع
        display_completed = order["status"] == "Completed" and order.get("payment_status") == "Paid"
        current_index = step_order.index(order["status"]) if order["status"] in step_order else -1
        if display_completed:
            current_index = 3
        steps = [
            {"key": "step_1", "done": True},
            {"key": "step_2", "done": current_index >= 1},
            {"key": "step_3", "done": current_index >= 2},
            {"key": "step_4", "done": display_completed},
        ]
        # خط سير الفني ووقت الوصول — لما الفني يقبل
        technician = models.get_user_by_id(order["technician_id"]) if order.get("technician_id") else None
        tech_lat = technician.get("lat") if technician else None
        tech_lng = technician.get("lng") if technician else None
        client_lat = order.get("lat")
        client_lng = order.get("lng")
        # fallback لموقع العميل المسجل لو الطلب بدون إحداثيات
        if client_lat is None or client_lng is None:
            cust = models.get_user_by_id(order["customer_id"])
            client_lat = cust.get("lat") if cust else None
            client_lng = cust.get("lng") if cust else None
        distance = haversine(tech_lat, tech_lng, client_lat, client_lng)
        eta_min = int(distance / 0.67) + 5 if distance is not None else None
        route = None
        if technician and client_lat and client_lng and tech_lat and tech_lng:
            route = {"tech": {"lat": tech_lat, "lng": tech_lng, "name": technician["name"], "gov": technician.get("governorate")}, "client": {"lat": client_lat, "lng": client_lng}, "distance": distance, "eta": eta_min}
        return render_template("track_order.html", order=order, steps=steps, payment_methods=PAYMENT_METHODS, route=route, technician=technician)

    @app.route("/api/track/<int:order_id>")
    @login_required
    def api_track(order_id):
        order = models.get_order_by_id(order_id)
        if not order or order["customer_id"] != session["user_id"]:
            return {"error": "no access"}, 403
        technician = models.get_user_by_id(order["technician_id"]) if order.get("technician_id") else None
        tech_lat = None; tech_lng = None
        if order.get("tech_lat") is not None and order.get("tech_lng") is not None:
            tech_lat = order.get("tech_lat"); tech_lng = order.get("tech_lng")
        elif technician:
            tech_lat = technician.get("lat"); tech_lng = technician.get("lng")
        client_lat = order.get("lat"); client_lng = order.get("lng")
        if client_lat is None or client_lng is None:
            cust = models.get_user_by_id(order["customer_id"])
            client_lat = cust.get("lat") if cust else None
            client_lng = cust.get("lng") if cust else None
        dist = haversine(tech_lat, tech_lng, client_lat, client_lng)
        eta = int(dist / 0.67) + 5 if dist is not None else None
        return {"tech": {"lat": tech_lat, "lng": tech_lng}, "client": {"lat": client_lat, "lng": client_lng}, "distance": dist, "eta": eta, "status": order["status"]}

    @app.route("/cancel_order/<int:order_id>")
    @role_required("client")
    def cancel_order(order_id):
        order = models.get_order_by_id(order_id)
        if not order or order["customer_id"] != session["user_id"]:
            flash("flash_no_access")
            return redirect(url_for("my_orders"))
        # منع الإلغاء بعد ما الفني يستلم الطلب — ده بيمنع احتيال "لغى بعد ما الفني وصل"
        if order["technician_id"] is not None or order["status"] != "Pending":
            flash("flash_cancel_fail_assigned")
            return redirect(url_for("my_orders"))
        # بدل الحذف — نحفظه كـ Rejected عشان يظهر في سجل المالك المالي
        models.update_order_status(order_id, "Rejected")
        flash("flash_order_cancelled")
        return redirect(url_for("my_orders"))

    @app.route("/client_complete_order/<int:order_id>")
    @role_required("client")
    def client_complete_order(order_id):
        # لم يعد يُستخدم — الدفع هو الذي يُكمل الطلب
        flash("flash_pay_first")
        return redirect(url_for("track_order", order_id=order_id))

    @app.route("/pay_order/<int:order_id>", methods=["POST"])
    @role_required("client")
    def pay_order(order_id):
        order = models.get_order_by_id(order_id)
        if not order or order["customer_id"] != session["user_id"]:
            flash("flash_no_access")
            return redirect(url_for("my_orders"))
        if order["status"] not in ("Awaiting Payment", "Completed"):
            flash("flash_not_ready_to_pay")
            return redirect(url_for("track_order", order_id=order_id))
        if order.get("payment_status") == "Paid":
            flash("flash_already_paid")
            return redirect(url_for("track_order", order_id=order_id))
        payment_method = request.form.get("payment_method", "").strip()
        coupon_code = request.form.get("coupon_code", "").strip().upper()
        allowed = {p["value"] for p in PAYMENT_METHODS}
        if payment_method not in allowed:
            flash("flash_fill_fields")
            return redirect(url_for("track_order", order_id=order_id))
        # كوبون — يطبق قبل الإسكرو
        discount = 0
        if coupon_code:
            coupon, err = models.validate_coupon(coupon_code, order.get("location"))
            if err:
                flash("flash_coupon_bad")
                return redirect(url_for("track_order", order_id=order_id))
            discount = int(order["service_price"] * coupon["discount_percent"] / 100)
            with models.get_db() as conn:
                conn.execute("UPDATE orders SET coupon_code=?, discount=?, service_price = service_price - ? WHERE id=?", (coupon_code, discount, discount, order_id))
            models.use_coupon(coupon_code)
            models.add_points(order["customer_id"], 10)
            flash("flash_coupon_ok")
            order = models.get_order_by_id(order_id)
        # إسكرو آمن: الفلوس تتحجز ولا تصل للفني إلا بـ OTP
        if payment_method == "Cash":
            # كاش: العميل سيدفع كاش للفني عند التسليم مع OTP
            with models.get_db() as conn:
                conn.execute("UPDATE orders SET payment_method=?, payment_status='Escrow' WHERE id=?", (payment_method, order_id))
            # إنشاء معاملة إسكرو
            txn = f"CASH-{order_id}-{int(time.time())%100000}"
            models.create_transaction(order_id, order["service_price"], order["service_price"]*0.20, payment_method, txn)
            flash("تم حجز الطلب — أعطِ الفني الكود والكاش عند التسليم")
            return redirect(url_for("track_order", order_id=order_id))
        else:
            with models.get_db() as conn:
                conn.execute("UPDATE orders SET payment_method=? WHERE id=?", (payment_method, order_id))
            return redirect(url_for("pay_gateway", order_id=order_id))

    @app.route("/confirm_escrow/<int:order_id>", methods=["POST"])
    @role_required("technician")
    def confirm_escrow(order_id):
        order = models.get_order_by_id(order_id)
        if not order or order["technician_id"] != session["user_id"]:
            flash("flash_no_access")
            return redirect(url_for("technician_tasks"))
        otp = request.form.get("otp", "").strip()
        if not otp or otp != order.get("otp_code"):
            flash("flash_otp_wrong")
            return redirect(url_for("technician_tasks"))
        # تحرير الإسكرو — تأكيد آمن
        if models.confirm_transaction(order.get("gateway_txn") or f"PAY-{order_id}", otp):
            models.add_notification(order["customer_id"], "تم تأكيد الخدمة ✅", f"الفني أكد استلام المبلغ لطلب #{order_id} — شكراً لثقتك")
            flash("تم تحرير المبلغ للفني ✅")
        else:
            # fallback: مباشر
            models.mark_order_paid(order_id, order.get("payment_method") or "Secure")
            flash("flash_paid_completed")
        return redirect(url_for("technician_tasks"))

    @app.route("/pay_gateway/<int:order_id>", methods=["GET", "POST"])
    @role_required("client")
    def pay_gateway(order_id):
        order = models.get_order_by_id(order_id)
        if not order or order["customer_id"] != session["user_id"]:
            flash("flash_no_access")
            return redirect(url_for("my_orders"))
        if order["status"] not in ("Awaiting Payment", "Completed") or order.get("payment_status") == "Paid":
            return redirect(url_for("track_order", order_id=order_id))
        if request.method == "POST":
            pm = order.get("payment_method") or "Secure"
            # تحقق مبسط — البوابة محاكاة 3D Secure
            if pm == "Secure":
                card = request.form.get("card_number", "").replace(" ", "")
                expiry = request.form.get("expiry", "").strip()
                cvv = request.form.get("cvv", "").strip()
                if pm == "Secure" and card:
                    if not (card.isdigit() and 13 <= len(card) <= 19):
                        flash("flash_fill_fields")
                        return redirect(url_for("pay_gateway", order_id=order_id))
            # إنشاء إسكرو — الفلوس محجوزة
            txn = f"PAY-SEC-{random.randint(100000,999999)}{int(time.time())%1000}"
            with models.get_db() as conn:
                conn.execute("UPDATE orders SET gateway_txn=?, payment_status='Escrow' WHERE id=?", (txn, order_id))
            models.create_transaction(order_id, order["service_price"], order["service_price"]*0.20, pm, txn)
            if order.get("technician_id"):
                models.add_notification(order["technician_id"], "تم الدفع في الإسكرو 🔒", f"العميل دفع {order['service_price']} ج.م لطلب #{order_id} — بانتظار كود التأكيد")
            flash("تم حجز المبلغ في الإسكرو 🔒 — أعطِ الكود للفني بعد التأكد من الخدمة")
            return redirect(url_for("track_order", order_id=order_id))
        return render_template("pay_gateway.html", order=order)

    @app.route("/rate_order/<int:order_id>", methods=["POST"])
    @role_required("client")
    def rate_order(order_id):
        order = models.get_order_by_id(order_id)
        if not order or order["customer_id"] != session["user_id"]:
            flash("flash_no_access")
            return redirect(url_for("my_orders"))
        if order.get("payment_status") != "Paid" or order["status"] != "Completed":
            flash("flash_not_ready_to_pay")
            return redirect(url_for("track_order", order_id=order_id))
        if order.get("rating") is not None:
            flash("flash_already_paid")
            return redirect(url_for("track_order", order_id=order_id))
        try:
            rating = int(request.form.get("rating", 0))
            review = request.form.get("review", "").strip()[:300]
            if rating < 1 or rating > 5:
                raise ValueError
        except:
            flash("flash_fill_fields")
            return redirect(url_for("track_order", order_id=order_id))
        models.add_rating(order_id, rating, review)
        if order.get("technician_id"):
            models.add_notification(order["technician_id"], f"تقييم جديد ⭐ {rating}", f"من العميل: {review or 'بدون تعليق'}")
        flash("flash_rated")
        return redirect(url_for("track_order", order_id=order_id))

    @app.route("/order_chat/<int:order_id>", methods=["GET", "POST"])
    @login_required
    def order_chat(order_id):
        order = models.get_order_by_id(order_id)
        if not order:
            return render_template("404.html"), 404
        uid = session["user_id"]
        if uid not in (order["customer_id"], order.get("technician_id")):
            # العميل أو الفني المخصص فقط
            if session.get("role") == "technician" and order["status"] == "Pending":
                pass  # الفني يقدر يشوف قبل القبول للسؤال
            else:
                flash("flash_no_access")
                return redirect(url_for("landing"))
        if request.method == "POST":
            msg = request.form.get("message", "").strip()
            photo = None
            if "photo" in request.files and request.files["photo"].filename:
                photo = save_fault_photo(request.files["photo"])
                if not msg:
                    msg = "📷 صورة"
            if msg or photo:
                models.add_message(order_id, uid, msg or "📷 صورة", photo)
                other = order["customer_id"] if uid != order["customer_id"] else order.get("technician_id")
                if other:
                    sender = models.get_user_by_id(uid)
                    preview = msg[:40] if msg else "صورة"
                    models.add_notification(other, f"رسالة جديدة 💬", f"من {sender['name']}: {preview}")
        # إذا طلب JSON
        if request.args.get("format") == "json":
            from flask import jsonify
            return jsonify(models.get_messages(order_id))
        messages = models.get_messages(order_id)
        return render_template("chat.html", order=order, messages=messages)

    @app.route("/approve_technician/<int:user_id>", methods=["POST"])
    @owner_required
    def approve_technician(user_id):
        models.approve_technician(user_id)
        u = models.get_user_by_id(user_id)
        if u:
            models.add_notification(user_id, "تمت الموافقة ✅", "يمكنك الآن استقبال الطلبات")
        flash("flash_tech_approved")
        return redirect(url_for("admin_dashboard"))

    @app.route("/ban_technician/<int:user_id>", methods=["POST"])
    @owner_required
    def ban_technician(user_id):
        with models.get_db() as conn:
            conn.execute("UPDATE users SET is_approved=0 WHERE id=?", (user_id,))
        flash("تم حظر الفني")
        return redirect(url_for("admin_dashboard"))

    @app.route("/remove_technician/<int:user_id>", methods=["POST"])
    @owner_required
    def remove_technician(user_id):
        with models.get_db() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            conn.execute("DELETE FROM wallets WHERE user_id=?", (user_id,))
        flash("تم حذف الفني")
        return redirect(url_for("admin_dashboard"))

    @app.route("/invoice/<int:order_id>")
    @login_required
    def invoice(order_id):
        order = models.get_order_by_id(order_id)
        if not order or (session["user_id"] not in (order["customer_id"], order.get("technician_id")) and session.get("role") != "admin" and models.get_user_by_id(session["user_id"])["email"].lower() != Config.OWNER_EMAIL.lower()):
            flash("flash_no_access")
            return redirect(url_for("landing"))
        customer = models.get_user_by_id(order["customer_id"])
        technician = models.get_user_by_id(order["technician_id"]) if order.get("technician_id") else None
        return render_template("invoice.html", order=order, customer=customer, technician=technician)

    @app.route("/update_location", methods=["POST"])
    @role_required("technician")
    def update_location():
        lat = request.form.get("lat") or request.json.get("lat") if request.is_json else None
        lng = request.form.get("lng") or request.json.get("lng") if request.is_json else None
        try:
            lat = float(lat); lng = float(lng)
        except:
            return "bad", 400
        # حدّث موقع الفني نفسه
        with models.get_db() as conn:
            conn.execute("UPDATE users SET lat=?, lng=? WHERE id=?", (lat, lng, session["user_id"]))
        # حدّث كل طلباته النشطة In Progress
        with models.get_db() as conn:
            conn.execute("UPDATE orders SET tech_lat=?, tech_lng=? WHERE technician_id=? AND status='In Progress'", (lat, lng, session["user_id"]))
        return "ok"

    # -----------------------------------------------------------------
    # Technician area
    # -----------------------------------------------------------------
    @app.route("/technical_dashboard")
    @role_required("technician")
    def technical_dashboard():
        raw_pending = models.get_orders_by_status("Pending")
        tech = models.get_user_by_id(session["user_id"])
        pending_orders = []
        for o in raw_pending:
            cust = models.get_user_by_id(o["customer_id"])
            o_lat = o.get("lat") or (cust.get("lat") if cust else None)
            o_lng = o.get("lng") or (cust.get("lng") if cust else None)
            t_lat = tech.get("lat") if tech else None
            t_lng = tech.get("lng") if tech else None
            dist = haversine(t_lat, t_lng, o_lat, o_lng)
            eta = f"{int(dist / 0.67) + 5} د" if dist is not None else None
            same_gov = cust and tech and cust.get("governorate") and cust.get("governorate") == tech.get("governorate")
            # حصر القريب فقط: نفس المحافظة أو أقل من 30 كم، غير كده من آخر الدنيا ما يظهرش
            if tech.get("governorate"):
                if not same_gov and (dist is None or dist > 30):
                    continue
            pending_orders.append({**o, "distance": dist, "eta": eta, "same_gov": same_gov, "customer_gov": cust.get("governorate") if cust else ""})
        pending_orders.sort(key=lambda x: (x["distance"] if x["distance"] is not None else 9999))
        my_active_orders = [
            o for o in models.get_orders_by_technician(session["user_id"])
            if o["status"] == "In Progress"
        ]
        # تقويم الحجوزات حسب التاريخ
        from collections import defaultdict
        calendar = defaultdict(list)
        for o in my_active_orders:
            day = (o.get("scheduled_at") or "")[:10] or "بدون ميعاد"
            calendar[day].append(o)
        earnings = models.get_technician_earnings(session["user_id"], Config.COMMISSION_RATE)
        wallet = models.get_wallet(session["user_id"])
        return render_template(
            "technical_dashboard.html",
            pending_orders=pending_orders,
            my_active_orders=my_active_orders,
            earnings=earnings,
            wallet=wallet,
            calendar=dict(calendar),
        )

    @app.route("/technician_tasks")
    @role_required("technician")
    def technician_tasks():
        tasks = models.get_orders_by_technician(session["user_id"])
        return render_template("technician_tasks.html", tasks=tasks)

    @app.route("/accept_order/<int:order_id>")
    @role_required("technician")
    def accept_order(order_id):
        order = models.get_order_by_id(order_id)
        if order and order["status"] == "Pending":
            with models.get_db() as conn:
                conn.execute("UPDATE orders SET status='In Progress', technician_id=? WHERE id=?", (session["user_id"], order_id))
            tech = models.get_user_by_id(session["user_id"])
            models.add_notification(order["customer_id"], "الفني قبل طلبك ✅", f"{tech['name']} قبل طلب #{order_id} وهيجيلك قريباً — شوف خط السير")
            flash("flash_order_accepted")
        return redirect(url_for("technical_dashboard"))

    @app.route("/reject_order/<int:order_id>")
    @role_required("technician")
    def reject_order(order_id):
        models.update_order_status(order_id, "Rejected")
        return redirect(url_for("technical_dashboard"))

    @app.route("/set_price/<int:order_id>", methods=["POST"])
    @role_required("technician")
    def set_price(order_id):
        order = models.get_order_by_id(order_id)
        if not order or order["technician_id"] != session["user_id"]:
            flash("flash_no_access")
            return redirect(url_for("technician_tasks"))
        try:
            price = int(request.form.get("final_price", 0))
            if price <= 0:
                raise ValueError
        except:
            flash("flash_fill_fields")
            return redirect(url_for("technician_tasks"))
        with models.get_db() as conn:
            conn.execute("UPDATE orders SET service_price=? WHERE id=?", (price, order_id))
        flash("تم تحديث السعر ✅")
        return redirect(url_for("technician_tasks"))

    @app.route("/technician_complete_order/<int:order_id>", methods=["GET", "POST"])
    @role_required("technician")
    def technician_complete_order(order_id):
        order = models.get_order_by_id(order_id)
        if order and order["technician_id"] == session["user_id"]:
            otp = str(random.randint(1000, 9999))
            with models.get_db() as conn:
                conn.execute("UPDATE orders SET status='Awaiting Payment', otp_code=? WHERE id=?", (otp, order_id))
            models.add_notification(order["customer_id"], "الفني أنهى الشغل ⏳", f"طلب #{order_id} جاهز للدفع — كود التأكيد: {otp} — لا تعطيه إلا بعد التأكد من الخدمة")
            flash("flash_waiting_payment")
        return redirect(url_for("technician_tasks"))

    @app.route("/reverse_order/<int:order_id>")
    @role_required("technician")
    def reverse_order(order_id):
        order = models.get_order_by_id(order_id)
        if not order:
            return render_template("404.html"), 404
        status_label = (
            "tech_status_arrived" if order["status"] == "Completed"
            else "tech_status_not_arrived"
        )
        return render_template("reverse_order.html", order=order, technician_status=status_label)

    # -----------------------------------------------------------------
    # Admin area
    # -----------------------------------------------------------------
    @app.route("/admin_dashboard")
    @owner_required
    def admin_dashboard():
        stats = {
            "total_orders": models.count_orders(),
            "pending_orders": models.count_orders("Pending"),
            "completed_orders": models.count_orders("Completed"),
            "total_clients": models.count_users_by_role("client"),
            "total_technicians": models.count_users_by_role("technician"),
        }
        stats["total_users"] = stats["total_clients"] + stats["total_technicians"] + models.count_users_by_role("admin")
        stats["revenue_paid"] = models.get_total_revenue()
        stats["revenue_pending"] = models.get_pending_revenue()
        stats["rejected_orders"] = models.count_orders("Rejected")
        stats["commission_total"] = stats["revenue_paid"] * Config.COMMISSION_RATE
        all_paid = [o for o in models.get_all_orders() if o.get("payment_status") == "Paid"]
        stats["payout_pending_total"] = sum(o["service_price"] for o in all_paid if o.get("payout_status") != "Paid") * (1 - Config.COMMISSION_RATE)
        # تحليلات آخر 7 أيام
        from datetime import datetime, timedelta
        chart_labels = []
        chart_orders = [0]*7
        chart_revenue = [0]*7
        try:
            all_orders = models.get_all_orders()
            for i in range(7):
                day = datetime.now() - timedelta(days=6-i)
                chart_labels.append(day.strftime("%m/%d"))
                day_start = datetime(day.year, day.month, day.day).timestamp()
                day_end = day_start + 86400
                for o in all_orders:
                    ts = o.get("created_at") or 0
                    if day_start <= ts < day_end:
                        chart_orders[i] += 1
                        if o.get("payment_status") == "Paid":
                            chart_revenue[i] += o.get("service_price") or 0
        except:
            chart_labels = [""]*7
        recent_orders = models.get_recent_orders(limit=10)

        # كشف احتيال: طلب ملغي لكن كان فيه فني مستلم — ده اللي تقصده "لغى وخد الفلوس"
        all_orders = models.get_all_orders(limit=50)
        suspicious = [o for o in all_orders if o["status"] == "Rejected" and o["technician_id"] is not None]
        # مستحقات الفنيين المعلقة
        pending_payouts = models.get_pending_payouts()

        # بيانات كل المستخدمين مع عدد طلباتهم/مهامهم — للمالك فقط
        raw_users = models.get_all_users()
        users_data = []
        for u in raw_users:
            if u["role"] == "client":
                cnt = models.count_orders_by_customer(u["id"])
            elif u["role"] == "technician":
                cnt = models.count_orders_by_technician(u["id"])
            else:
                cnt = 0
            users_data.append({**u, "orders_count": cnt})

        # موافقة الفنيين
        pending_techs = models.get_pending_technicians()
        # أرباح كل فني + محفظته المباشرة زي أوبر
        tech_earnings = {}
        wallets = {}
        for u in raw_users:
            if u["role"] == "technician":
                tech_earnings[u["id"]] = models.get_technician_earnings(u["id"], Config.COMMISSION_RATE)
                wallets[u["id"]] = models.get_wallet(u["id"])

        return render_template("admin_dashboard.html", stats=stats, recent_orders=recent_orders, users_data=users_data, suspicious=suspicious, pending_payouts=pending_payouts, tech_earnings=tech_earnings, wallets=wallets, pending_techs=pending_techs, chart_labels=chart_labels, chart_orders=chart_orders, chart_revenue=chart_revenue)

    @app.route("/admin/services", methods=["GET", "POST"])
    @owner_required
    def admin_services():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add":
                cat = request.form.get("category", "").strip()
                new_cat = request.form.get("new_category", "").strip()
                if cat == "New Category" and new_cat:
                    cat = new_cat
                name = request.form.get("name", "").strip()
                desc = request.form.get("description", "").strip()
                try:
                    price = int(request.form.get("base_price", 0))
                except:
                    price = 0
                if cat and name and price:
                    import services_data as sd
                    if cat not in sd.categories:
                        sd.categories[cat] = []
                    new_id = max((s["id"] for s in sd.get_all_services()), default=0) + 1
                    sd.categories[cat].append({"id": new_id, "name": name, "description": desc, "base_price": price})
                    flash("تمت إضافة الخدمة ✅")
            elif action == "delete":
                try:
                    sid = int(request.form.get("service_id", 0))
                except:
                    sid = 0
                import services_data as sd
                for cat in list(sd.categories.keys()):
                    sd.categories[cat] = [s for s in sd.categories[cat] if s["id"] != sid]
                flash("تم الحذف")
        # عرض كل الخدمات
        all_svc = []
        for cat, svcs in categories.items():
            for s in svcs:
                all_svc.append({**s, "category": cat})
        return render_template("admin_services.html", services=all_svc, categories=list(categories.keys()))

    @app.route("/admin/export")
    @owner_required
    def admin_export():
        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Customer", "Service", "Price", "Status", "Payment", "Car", "Location", "Date"])
        for o in models.get_all_orders():
            writer.writerow([o["id"], o["name"], o["service_name"], o["service_price"], o["status"], o.get("payment_status"), f"{o.get('car_make','')} {o.get('car_model','')}".strip(), o["location"], o.get("created_at")])
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=sallahly_orders.csv"}
        )

    @app.route("/mark_payout/<int:order_id>", methods=["POST"])
    @owner_required
    def mark_payout(order_id):
        order = models.get_order_by_id(order_id)
        if order and order.get("payment_status") == "Paid" and order.get("payout_status") == "Pending":
            models.mark_payout_done(order_id)
            flash("flash_payout_done")
        return redirect(url_for("admin_dashboard"))

    # -----------------------------------------------------------------
    # Error handlers
    # -----------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG", "0") == "1")