# AutoCare - Car Service Booking Platform (نسخة احترافية)

## الفرق عن الكود الأصلي

### مشاكل أمنية اتصلحت
- **الباسوردات كانت بتتخزن كنص عادي** (`password = db.Column(db.String)` وبتتقارن مباشرة) — دلوقتي كل باسورد بيتخزن مُشفّر (`werkzeug.security`).
- **`secret_key` و بيانات إيميل Gmail الحقيقية** كانوا مكتوبين صريح في الكود — دلوقتي كلهم بيتقروا من متغيرات البيئة.
- **كل صفحات الداشبورد كانت مفتوحة بدون أي حماية** (`customer_dashboard`, `technical_dashboard`, `admin_dashboard` ملهاش أي تحقق تسجيل دخول) — دلوقتي فيه `@role_required("client"/"technician"/"admin")` على كل صفحة، فمينفعش حد يدخل داشبورد مش بتاعته.
- **مفيش أي تحقق إن الطلب فعلاً بتاع اليوزر اللي بيحاول يشوفه** (`track_order`, `cancel_order`) — دلوقتي بيتحقق إن `customer_id` بتاع الطلب هو نفسه اليوزر الحالي.
- **الـ OTP كان بيتبعت لكن مفيش صفحة تتحقق منه** — يعني أي حد يقدر يوصل مباشرة لـ `reset_password` بدون ما يعرف الكود خالص. دلوقتي فيه صفحة `/verify_otp` كاملة، والكود بيتخزن مُشفّر (hash) في الـ session مش نص عادي، وله صلاحية 10 دقايق بس.

### مشاكل هيكلية
- **بيانات الخدمات (`categories`) كانت متكررة 3 مرات** في نفس الملف (مرة import من `services_data` مش موجود أصلاً، ومرة inline، ومرة تالتة جوه `customer_dashboard`) — دلوقتي فيها نسخة واحدة بس في `services_data.py`.
- **`my_orders` كانت بترجع بيانات وهمية ثابتة** (`orders = [{"id": 1, ...}]`) بدل ما تجيب طلبات اليوزر الحقيقية من قاعدة البيانات.
- **متغير `orders = []` و `tasks = orders` عالميين ملهومش استخدام حقيقي** جنب وجود موديل `Order` كامل في قاعدة البيانات — كود ميت اتشال.
- **فصل الكود لطبقات واضحة**:
  - `config.py` - الإعدادات
  - `database.py` - الاتصال بقاعدة البيانات وإنشاء الجداول
  - `models.py` - كل عمليات القراءة/الكتابة
  - `services_data.py` - كتالوج الخدمات (مصدر واحد)
  - `auth.py` - decorators الحماية (`login_required`, `role_required`)
  - `mailer.py` - إرسال OTP (بيرجع تلقائياً لوضع "طباعة في الـ console" لو مفيش إعدادات بريد)
  - `app.py` - الـ routes فقط

### تحسينات وظيفية
- الطلب بيتحفظ بربط حقيقي بين العميل (`customer_id`) والفني (`technician_id`) وسعر واسم الخدمة وقت الطلب (عشان لو السعر اتغيّر بعدين، الطلب القديم يفضل زي ما كان).
- فني بيقدر يقبل/يرفض/ينهي طلب، والطلب بيتربط بيه تلقائياً.
- تتبع الطلب (`track_order`) بيوضح خطوات حقيقية بناءً على حالة الطلب الفعلية.
- الأدمن بيشوف إحصائيات حقيقية (عدد الطلبات/العملاء/الفنيين) بدل بيانات وهمية.

## طريقة التشغيل

```bash
pip install -r requirements.txt
python app.py
```

هيتعمل تلقائياً 3 حسابات تجريبية أول مرة:

| الدور | الإيميل | الباسورد |
|---|---|---|
| Admin | admin@example.com | ChangeMe123! |
| Client | client@example.com | ChangeMe123! |
| Technician | tech@example.com | ChangeMe123! |

**غيّر البيانات دي قبل أي نشر حقيقي** عن طريق متغيرات البيئة:

```bash
export SECRET_KEY="مفتاح-عشوائي-طويل"
export DEFAULT_ADMIN_EMAIL="admin@yourcompany.com"
export DEFAULT_ADMIN_PASSWORD="كلمة-مرور-قوية"
python app.py
```

## تفعيل إرسال OTP بالإيميل فعلياً (اختياري)

لو عايز الـ OTP يتبعت بإيميل حقيقي بدل ما يتطبع في الـ terminal بس:

```bash
pip install Flask-Mail
export MAIL_USERNAME="your-email@gmail.com"
export MAIL_PASSWORD="app-password-from-gmail"   # مش الباسورد العادي، لازم App Password
python app.py
```

من غير الإعدادات دي، الكود هيشتغل عادي بس هيطبع الـ OTP في التيرمنال (وضع تطوير آمن).

## نقاط تحتاج انتباه قبل النشر الفعلي

1. **لا تشغّل بـ `debug=True` في الإنتاج**.
2. **SQLite مناسب للتطوير فقط** - للمواقع الحقيقية استخدم PostgreSQL.
3. أضف **CSRF protection** (`Flask-WTF`) لكل النماذج.
4. أضف **rate limiting** على `/login` و `/forgot_password` لمنع محاولات التخمين.
5. فعّل **HTTPS** وخلي الكوكيز `Secure`.
