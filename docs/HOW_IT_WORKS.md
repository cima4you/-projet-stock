# كيفية عمل التطبيق — نظام إدارة المخزون

شرح عملي لكيفية عمل التطبيق خطوة بخطوة: من الإقلاع إلى العمليات اليومية.

---

## 1) إقلاع التطبيق (Startup)

يبدأ كل شيء من `main.py`:

1. إنشاء `Flask` app مع إعدادات الجلسة (`SESSION_SECRET`).
2. إنشاء المجلدات المطلوبة (uploads، static، templates...).
3. `init_database()` من `db.py`:
   - إنشاء الجداول إن لم تكن موجودة (users, products, stock_movements, audit_log, workshops...).
   - تشغيل الترحيلات (Migration): إضافة أعمدة مفقودة مثل `workshop_id`, `deleted_at`, `min_quantity`, وتحويل `quantity` إلى `REAL` (كميات عشرية) في `products` و`stock_movements`.
   - إنشاء مستخدم أدمن افتراضي إن لم يوجد (`admin`).
4. تفعيل حماية CSRF عبر `init_csrf(app)`.
5. تسجيل كل الـ Blueprints عبر `register_blueprints(app)`.
6. تشغيل `start_scheduler()` للمهام المجدولة (مثل التقرير اليومي).
7. تشغيل الخادم على المنفذ **8050** وفتح المتصفح تلقائيًا.

> قاعدة البيانات: SQLite محليًا (`stock.db`) — وعند توفّر `DATABASE_URL` يتحول تلقائيًا إلى PostgreSQL (لتشغيل Render). `db.py` يترجم `?` إلى `%s` و`AUTOINCREMENT` إلى `SERIAL` عند الحاجة.

---

## 2) تدفق المصادقة (Login Flow)

```
المستخدم → /login (POST)
    ├─ الفحص: مستخدم نشط؟ كلمة المرور صحيحة؟ (hash عبر werkzeug)
    ├─ 5 محاولات خاطئة خلال 5 دقائق → رفض + رسالة انتظار
    ├─ عند النجاح: تخزين الجلسة:
    │     user_id, username, role, workshop_id, workshop_name, lang ('fr')
    ├─ تحديث last_login في قاعدة البيانات
    └─ توجيه إلى /dashboard
```

- جلسة `workshop_id` هي **مفتاح العزل**: كل الاستعلامات اللاحقة تَقيّد بها.
- `/forgot_password` يولّد رمزًا آمنًا (`secrets.token_urlsafe`) صالحًا ساعة، ويرسل بريدًا عبر `send_password_reset_email`.
- **الواجهة بالفرنسية فقط**: `/change_language/<lang>` موجود للتوافق فقط ويُجبر `lang = 'fr'` دائمًا — لا يوجد تبديل للغة في الواجهة.

---

## 3) العزل حسب الورشة — النمط الأساسي (Multi-Workshop)

هذا أهم نمط في المشروع. كل مسار يقرأ/يكتب بيانات مخزون يستخدم `workshop_filter()`:

```python
ws_clause, ws_params = workshop_filter()        # مثال: (' AND workshop_id = ?', [3])
cursor.execute('SELECT ... FROM products WHERE ...' + ws_clause, ws_params)
```

- `admin`/`principal_admin` → `('', [])` (يرون كل شيء).
- مستخدم عادي → `(' AND workshop_id = ?', [workshop_id])` (ورشته فقط).
- لا يوجد ورشة → `(' AND workshop_id IS NULL', [])` (السجلات القديمة).

نفس المبدأ في الإشعارات: دوال مثل `send_product_addition_notification(..., workshop_id=...)` تُرسل فقط لمستلمي نفس الورشة.

---

## 4) تدفق المنتجات (Products Flow)

### إضافة منتج — `/add_product`
1. التحقق من عدم تكرار الرمز (`code`) داخل الورشة.
2. إدراج المنتج مع `workshop_id` و `created_by`.
3. **تلقائيًا**: إذا الكمية > 0، تُنشأ حركة `entry` في `stock_movements`.
4. إرسال إشعار دخول لمن يتلقى نوع `achat_par_bc` / `achat_par_caisse` في نفس الورشة.
5. تسجيل العملية في `audit_log`.

### تعديل/حذف
- التعديل: تحديث الحقول + `log_audit` — **المسؤولون فقط** (`@admin_required`).
- الحذف: **حذف ناعم** (وضع `deleted_at`) + إشعار حذف للمستلمين.

### استيراد/تصدير Excel
- الاستيراد: يقرأ `pandas` ملف Excel، يطابق أعمدة بأسماء متعددة (عربي/فرنسي/إنجليزي)، يتخطى المنتجات المكررة ويجمع الأخطاء في `session['import_errors']`.
- التصدير: يبني ملف `.xlsx` عبر `xlsxwriter` مع تنسيق تواريخ صحيح.

---

## 5) تدفق حركات المخزون (Movements Flow) — جوهر النظام

```
/add_movement (POST)
    ├─ النوع entry (دخول): quantity = current + qty
    ├─ النوع exit (خروج):  التحقق current >= qty (منع الكمية السالبة)
    │                      quantity = current - qty
    ├─ إدراج صف في stock_movements بكل التفاصيل:
    │   مورد، BC، BL، فاتورة، نوع شراء، ورشة عمل، سائق، شاحنة، matricule...
    ├─ تحديث products.quantity
    ├─ إشعار entry → send_product_addition_notification
    ├─ إشعار exit  → send_product_exit_notification
    └─ log_audit
```

- **الكمية المخزنية ليست حقلاً يُكتب مباشرة** عند إضافة حركة؛ بل تُحسب من `current ± quantity`. هذا يضمن الاتساق مع سجل الحركات.
- **الكميات عشرية** (`REAL`): تُقرأ عبر `parse_quantity()` وتُعرض بعلامتين عشريتين.
- **تعديل/حذف حركة** (`/edit_movement`, `/delete_movement`): للمسؤولين فقط، مع **إعادة حساب تلقائية** لكمية المنتج من بقية الحركات (مع حماية من رصيد سالب).
- `/product_history/<id>` يعيد بناء تطور المخزون من سلسلة الحركات لرسم الرسم البياني.
- عند إضافة منتج جديد أو استيراد Excel بكمية، تُنشأ حركة `entry` تلقائيًا — فلا يوجد مَن يضيف كمية دون أثر في سجل الحركات.

---

## 6) الإشعارات (Email / WhatsApp)

تعتمد على `notifications.py` و `recipient_emails`:

| الحدث | نوع الإشعار |
|---|---|
| دخول منتج (شراء بطلب/نقدًا) | `achat_par_bc` / `achat_par_caisse` |
| خروج/استهلاك | `consumption` |
| حذف منتج | `product_deletion` |
| انتهاء صلاحية قريب | `product_expiration` |
| تحويل بين الورشات | `transfert` |

- الإشعارات مُصفّاة حسب `workshop_id` — مستلمي ورشة معينة فقط يتلقون أخبارها.
- `email_management` يسمح بإدارة المستلمين وعناوينهم وتفعيل/تعطيل كل نوع لكل عنوان.
- `notification_logs` يحفظ سجل كل إشعار (موضوع، محتوى، حالة: `sent`/`read`)، وتقرأه واجهات `/api/unread_notifications` و `/api/unread_count` لعرض الجرس في القوالب.
- **WhatsApp**: يدعم UltraMsg و CallMeBot.

---

## 7) المهام المجدولة والتقارير اليومية

- `scheduler.py` يشغّل فحص المنتجات القاربة على الانتهاء وإرسال التقرير اليومي.
- `/cron/daily-report?token=<CRON_SECRET>` نقطة زمنية خارجية (مثل cron-job.org) تُرسل التقرير اليومي مرة واحدة في اليوم — `send_daily_report_if_not_sent` يمنع الإرسال المزدوج.

---

## 8) الجرد المادي (Inventory)

`/inventory/count`:
1. يقرأ الكمية النظرية الحالية للمنتج.
2. يدخل المسؤول الكمية الفعلية.
3. يحسب الفرق (`actual - theoretical`).
4. يُسجّل سطرًا في `inventory_counts` (نظري/فعلي/فرق/ملاحظات/مَن نفّذ).
5. يحدّث `products.quantity` إلى الكمية الفعلية.
6. يسجّل العملية في `audit_log` مع الفرق.

---

## 9) سجل التدقيق (Audit Log)

دالة `log_audit(action, entity_type, entity_id, details)` في `utils.py` تُستدعى بعد كل عملية مهمة:

- `create` / `update` / `delete` / `restore` / `inventory`
- تُخزَّن: الإجراء، نوع الكيان، معرّفه، التفاصيل، المستخدم، والوقت.
- **تفاصيل قبل/بعد**: `build_change_details()` تُولّد نصًا يوضح الحقل، القيمة القديمة، والقيمة الجديدة؛ و`parse_change_details()` تعيد تحليله لعرضه جدوليًا.
- **سجل الاتصالات**: جدول `login_logs` يسجّل كل دخول/فشل دخول/خروج (مستخدم، عنوان IP، وقت).
- تُعرض في `/audit_log` (**للمسؤولين فقط**): جدولان (تغييرات + اتصالات) مع فلاتر وترقيم صفحات (50 سطرًا).

---

## 10) لوحات تحكم الورشات والمقارنة (المنطقة المحجوزة للمسؤول)

- `/workshop_dashboard/<id>`: لوحة تحكم مفردة لكل ورشة — إحصائيات، منتجات منخفضة/منتهية، آخر الحركات، ومقارنة الفترات.
- `/workshop_comparison`: جدول مقارنة بين الورشات (منتجات، مخزون، حركات، قيمة) + رسوم بيانية.
- الاثنان محجوزان بـ `@admin_required`؛ المستخدم العادي يرى ورشته فقط عبر لوحة التحكم الرئيسية.

---

## 11) الأمان

| الطبقة | التفاصيل |
|---|---|
| كلمات المرور | مشفّرة بـ `werkzeug.generate_password_hash` — لا تُخزَّن نصًا |
| الجلسة | `SESSION_SECRET` من `.env` |
| CSRF | حماية عبر `csrf.py` |
| تقييد المحاولات | 5 محاولات تسجيل دخول خاطئة / 5 دقائق |
| الأدوار | ديكورات `login_required` / `admin_required` / `principal_admin_required` |
| رفع الملفات | التحقق من الامتدادات (`allowed_file`) + حد أقصى 16MB |
| الاستيراد | `secure_filename` + حذف الملف بعد المعالجة |
| رمز Cron | `CRON_SECRET` للتحقق من النقطة الزمنية |
| حماية الأدمن الرئيسي | لا يمكن إنشاء/حذف/تعطيل/تغيير كلمة مرور `principal_admin` |

---

## 12) البنية (Architecture) في سطر واحد

```
Flask app → Blueprints (routes/) → db.py (SQLite/PostgreSQL) + utils.py (صلاحيات وعزل ورشة)
              │
              └── notifications.py (بريد/واتساب) + scheduler.py (مهام) + csrf.py (أمان)
```

---

## 13) التطوير والنشر

- **محليًا**: `python main.py` → `http://127.0.0.1:8050`
- **التبعيات**: `uv sync` أو `pip install -r requirements.txt`
- **التشفير**: `python protect_env.py` يشفر `.env` إلى `.env.encrypted`
- **الإنتاج (Render)**: `render.yaml` ينشئ Web Service + PostgreSQL تلقائيًا، وبيئة الإنتاج تكشف PostgreSQL عبر `DATABASE_URL` ويترجم `db.py` الاستعلامات تلقائيًا.
