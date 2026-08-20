# خريطة التطبيق — نظام إدارة المخزون

خريطة شاملة لجميع المسارات (Routes) والأدوار المسموح لها بالوصول لكل صفحة.

---

## نظرة عامة على البنية

```
نظام إدارة المخزون (Flask)
│
├── main.py                  → نقطة الدخول: إعداد التطبيق + CSRF + التسجيل الأزرق (Blueprints)
├── config.py                → الإعدادات (SMTP, الجلسة, مسارات الملفات)
├── db.py                    → إنشاء قاعدة البيانات + الجداول + الترحيل (Migration)
├── utils.py                 → الديكورات (login/admin/principal_admin) + workshop_filter()
├── csrf.py                  → حماية CSRF
├── notifications.py         → البريد الإلكتروني + واتساب + التقارير اليومية
├── scheduler.py             → المهام المجدولة
├── translations.py          → الترجمات بالفرنسية فقط (نصوص عربية قديمة غير مستخدمة — الواجهة بالفرنسية)│
│
└── routes/                  → كل ملف يحتوي مجموعة مسارات (Blueprint)
    ├── auth.py              → المصادقة
    ├── dashboard.py         → لوحة التحكم
    ├── products.py          → المنتجات
    ├── movements.py         → حركات المخزون
    ├── users.py             → المستخدمون
    ├── categories.py        → التصنيفات
    ├── suppliers.py         → الموردون
    ├── reports.py           → التقارير
    ├── inventory.py         → جرد المخزون
    ├── email_mgmt.py        → إدارة البريد
    ├── logo.py              → الشعار
    ├── notifications_api.py → إشعارات API
    ├── search.py            → البحث
    ├── workshops.py         → الورشات + لوحات التحكم لكل ورشة + مقارنة الورشات
    └── cron.py              → نقاط زمنية خارجية
```

> ملاحظة: الواجهة بالفرنسية فقط (لا تغيير لغة). الكميات عشرية (REAL) تُعرض بعلامتين عشريتين.

---

## الأدوار والصلاحيات

| الدور | الوصول |
|---|---|
| `user` | لوحة التحكم، المنتجات، حركات المخزون، التقارير، البحث، واجهات API الأساسية |
| `admin` | كل ما يخص `user` + المستخدمين، التصنيفات، الموردون، الجرد، إدارة البريد، الشعار، الورشات، المنتجات المؤرشفة |
| `principal_admin` | كل ما يخص `admin` + تعديل أي مستخدم، إدارة حساب الأدمن الرئيسي |

الديكورات في `utils.py`:
- `@login_required` — أي مستخدم مسجّل دخول
- `@admin_required` — `admin` أو `principal_admin`
- `@principal_admin_required` — `principal_admin` فقط

---

## 1) المصادقة — `routes/auth.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/` | GET | عام | يوجّه إلى لوحة التحكم أو صفحة تسجيل الدخول |
| `/login` | GET/POST | عام | تسجيل الدخول (حد أقصى 5 محاولات / 5 دقائق حسب عنوان IP) |
| `/logout` | GET | عام | تسجيل الخروج |
| `/change_language/<lang>` | GET | عام | موجود للتوافق فقط — يُجبر اللغة الفرنسية دائمًا |
| `/forgot_password` | GET/POST | عام | إرسال رابط إعادة تعيين كلمة المرور |
| `/reset_password/<token>` | GET/POST | عام | إعادة تعيين كلمة المرور (الرمز صالح لمدة ساعة) |

---

## 2) لوحة التحكم — `routes/dashboard.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/dashboard` | GET | `login_required` | إحصائيات: إجمالي المنتجات، المخزون المنخفض، الحركات، الداخلة/الخارجة، آخر 10 حركات، المنتجات منتهية/قاربة على الانتهاء، رسوم بيانية (30 يوم، تصنيفات، أكثر المنتجات حركة، الموردون) |

---

## 3) المنتجات — `routes/products.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/products` | GET | `login_required` | قائمة المنتجات مع ترقيم الصفحات وفلاتر (تصنيف، بحث، نوع الشراء، مورد، منطقة تخزين، ماركة، تواريخ، ورشة) |
| `/add_product` | GET/POST | `login_required` | إضافة منتج (ينشئ حركة دخول تلقائيًا إذا الكمية > 0) |
| `/edit_product/<id>` | GET/POST | `admin_required` | تعديل منتج (المسؤولون فقط) |
| `/delete_product/<id>` | POST | `admin_required` | أرشفة منتج (حذف ناعم `deleted_at`) — POST فقط + CSRF |
| `/restore_product/<id>` | POST | `admin_required` | استعادة منتج من الأرشيف — POST فقط + CSRF |
| `/archived_products` | GET | `admin_required` | قائمة المنتجات المؤرشفة |
| `/import_products` | GET/POST | `login_required` | استيراد منتجات من ملف Excel |
| `/import_errors` | GET | `login_required` | عرض أخطاء الاستيراد |
| `/product_reports` | GET | `login_required` | تقرير المنتجات |
| `/export_products_excel` | GET | `login_required` | تصدير المنتجات إلى Excel |

---

## 4) حركات المخزون — `routes/movements.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/movements` | GET | `login_required` | قائمة الحركات مع فلاتر (نوع، بحث، مورد، تصنيف، نوع شراء، ورشة عمل، تواريخ) |
| `/product_history/<id>` | GET | `login_required` | سجل حركات منتج مع رسم بياني لتطور المخزون |
| `/add_movement` | GET/POST | `login_required` | إضافة حركة دخول/خروج (يحدّث كمية المنتج، يمنع خروج أكثر من المتاح) |
| `/edit_movement/<id>` | GET/POST | `admin_required` | تعديل حركة (يعيد حساب كمية المنتج، حماية من رصيد سالب) |
| `/delete_movement/<id>` | POST | `admin_required` | حذف حركة (يعيد حساب كمية المنتج) — POST فقط + CSRF |
| `/movement_reports` | GET | `login_required` | تقرير الحركات مع ملخص حسب النوع |
| `/export_movements_excel` | GET | `login_required` | تصدير الحركات إلى Excel |

---

## 5) المستخدمون — `routes/users.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/users` | GET | `admin_required` | قائمة المستخدمين |
| `/add_user` | GET/POST | `admin_required` | إضافة مستخدم (لا يمكن إنشاء `principal_admin`) |
| `/edit_user/<id>` | GET/POST | `principal_admin_required` | تعديل مستخدم (مع حماية من خفض/تعطيل الأدمن الرئيسي) |
| `/delete_user/<id>` | POST | `admin_required` | حذف مستخدم (ممنوع حذف نفسك أو الأدمن الرئيسي) — POST فقط + CSRF |

---

## 6) التصنيفات — `routes/categories.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/categories` | GET | `admin_required` | قائمة التصنيفات |
| `/add_category` | POST | `admin_required` | إضافة تصنيف |
| `/edit_category/<id>` | POST | `admin_required` | تعديل تصنيف |
| `/delete_category/<id>` | POST | `admin_required` | حذف تصنيف — POST فقط + CSRF |

---

## 7) الموردون — `routes/suppliers.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/suppliers` | GET | `admin_required` | قائمة الموردين |
| `/add_supplier` | POST | `admin_required` | إضافة مورد |
| `/edit_supplier/<id>` | POST | `admin_required` | تعديل مورد |
| `/delete_supplier/<id>` | POST | `admin_required` | حذف مورد — POST فقط + CSRF |

---

## 8) التقارير — `routes/reports.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/reports` | GET | `login_required` | صفحة مركز التقارير |
| `/audit_log` | GET | `admin_required` | سجل التدقيق (Audit Trail): جدولان (تغييرات + اتصالات) مع فلاتر وترقيم صفحات وتفاصيل قبل/بعد |
| `/export_pdf_products` | GET | `login_required` | تصدير تقرير المنتجات PDF |
| `/export_pdf_movements` | GET | `login_required` | تصدير تقرير الحركات PDF |

---

## 9) جرد المخزون — `routes/inventory.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/inventory` | GET | `admin_required` | صفحة الجرد (آخر 100 عملية + قائمة المنتجات) |
| `/inventory/count` | POST | `admin_required` | تسجيل جرد: يسجّل الكمية النظرية/الفعلية/الفرق ويحدّث كمية المنتج |
| `/api/product_info/<id>` | GET | `login_required` | معلومات منتج بصيغة JSON |

---

## 10) إدارة البريد — `routes/email_mgmt.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/email_management` | GET | `admin_required` | إدارة مستلمي الإشعارات وتفعيل أنواع الإشعارات |
| `/test_email` | GET | `admin_required` | إرسال بريد تجريبي |
| `/add_recipient` | POST | `admin_required` | إضافة مستلم (مع عدة عناوين بريد) |
| `/edit_recipient/<id>` | POST | `admin_required` | تعديل مستلم |
| `/delete_email/<id>` | POST | `admin_required` | حذف بريد إلكتروني من مستلم — POST فقط + CSRF |
| `/check_expiring_products_manual` | GET | `admin_required` | فحص يدوي للمنتجات القاربة على الانتهاء وإرسال إشعار |

أنواع الإشعارات: `achat_par_bc`، `achat_par_caisse`، `achat_a_regulariser`، `transfert`، `consommation`، حذف منتج، انتهاء صلاحية.

---

## 11) الشعار — `routes/logo.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/logo_management` | GET | `admin_required` | إدارة شعار النظام |
| `/upload_logo` | POST | `admin_required` | رفع شعار جديد |
| `/logo` | GET | عام | عرض الشعار (مع شعار افتراضي) |

---

## 12) إشعارات API — `routes/notifications_api.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/api/unread_notifications` | GET | تسجيل دخول | آخر 20 إشعار مرسل |
| `/api/mark_notification_read/<id>` | GET | تسجيل دخول | تعليم إشعار كمقروء |
| `/api/unread_count` | GET | تسجيل دخول | عدد الإشعارات غير المقروءة |

---

## 13) البحث — `routes/search.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/api/search_products` | GET | `login_required` | بحث JSON عن المنتجات (رمز/اسم/مورد/تصنيف) — حتى 20 نتيجة |

---

## 14) الورشات — `routes/workshops.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/workshops` | GET | `admin_required` | قائمة الورشات (مع بحث) |
| `/add_workshop` | GET/POST | `admin_required` | إضافة ورشة |
| `/edit_workshop/<id>` | GET/POST | `admin_required` | تعديل ورشة |
| `/delete_workshop/<id>` | POST | `admin_required` | حذف ورشة (ممنوع إذا عليها مستخدمون أو منتجات) — POST فقط + CSRF |
| `/api/workshops` | GET | `login_required` | قائمة ورشات JSON (المسؤول يرى الكل، المستخدم يرى ورشته فقط) |
| `/workshop_dashboard/<id>` | GET | `admin_required` | لوحة تحكم لورشة واحدة (إحصائيات، منتجات منخفضة، حركات) |
| `/workshop_comparison` | GET | `admin_required` | مقارنة بين الورشات (جداول + رسوم بيانية) |

---

## 15) المهام الزمنية — `routes/cron.py`

| المسار | الطريقة | الصلاحية | الوصف |
|---|---|---|---|
| `/cron/daily-report` | GET | رمز `CRON_SECRET` | إرسال التقرير اليومي (مرة واحدة في اليوم) — للخدمات الخارجية مثل cron-job.org |

---

## قواعد بيانات

| الجدول | الوصف |
|---|---|
| `users` | المستخدمون (اسم، كلمة مرور مشفّرة، بريد، دور، نشط، `workshop_id`) |
| `products` | المنتجات (رمز فريد لكل ورشة `UNIQUE(code, workshop_id)`, كميات عشرية) |
| `stock_movements` | حركات المخزون (دخول/خروج مع كل التفاصيل: مورد، BC/BL/فاتورة، ورشة عمل، سائق، شاحنة... — كميات عشرية) |
| `categories` | التصنيفات |
| `suppliers` | الموردون |
| `notification_recipients` | مستلمو الإشعارات (مجموعة) |
| `recipient_emails` | عناوين البريد لكل مستلم مع تفعيلات الإشعارات |
| `notification_logs` | سجل الإشعارات المرسلة |
| `audit_log` | سجل التدقيق (من فعل ماذا + تفاصيل قبل/بعد) |
| `login_logs` | سجل الاتصالات (دخول/فشل/خروج، عنوان IP) |
| `login_attempts` | عدّاد محاولات الدخول الفاشلة حسب IP (5/5 دقائق) |
| `inventory_counts` | عمليات الجرد (نظري/فعلي/فرق) |
| `workshops` | الورشات |

---

## قواعد العزل حسب الورشة (Workshop Filtering)

- `workshop_filter()` في `utils.py` تُلحق `AND workshop_id = ?` بكل استعلام.
- `admin` و `principal_admin` يرون كل الورشات (لا فلتر).
- المستخدم العادي يرى منتجات/حركات ورشته فقط.
- السجلات القديمة بدون `workshop_id` تُعامَل عبر `workshop_id IS NULL`.
