<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.fa.md">فارسی</a>
</p>

<h1 align="center">RayPulse</h1>

<p align="center">
  داشبورد سبک برای مانیتورینگ اوت‌باندهای Xray
</p>

<p align="center">
  <a href="https://github.com/Matialz7/RayPulse/releases/tag/v1.0.0">
    <img src="https://img.shields.io/badge/release-v1.0.0-3b82f6?style=flat-square" alt="release">
  </a>
  <a href="https://github.com/Matialz7/RayPulse/releases/download/v1.0.0/RayPulse-v1.0.0.zip">
    <img src="https://img.shields.io/badge/download-ZIP-22c55e?style=flat-square" alt="download zip">
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-f59e0b?style=flat-square" alt="license">
  </a>
  <a href="./README.md">
    <img src="https://img.shields.io/badge/docs-English-8b5cf6?style=flat-square" alt="English docs">
  </a>
</p>

<p align="center">
  پنل ساده و سبک برای نمایش وضعیت اوت‌باندها، تاریخچه تاخیر، کاربران آنلاین و ترافیک
</p>

---

## نصب سریع

```bash
bash <(curl -Ls https://raw.githubusercontent.com/Matialz7/RayPulse/main/install.sh)
```

## RayPulse چه چیزهایی را نمایش می‌دهد؟

- تاخیر و وضعیت اوت‌باندها
- بهترین اوت‌باند در لحظه
- پایدارترین اوت‌باندها
- کاربران آنلاین بر اساس access log
- مصرف ترافیک اوت‌باندها در صورتی که `debug/vars` این آمار را بدهد

## قابلیت‌ها

- برنامه تک‌فایل پایتون
- نصب ساده به‌صورت سرویس systemd
- امکان استفاده از HTTPS با سرتیفیکیت خودتان
- نصب تعاملی
- نمایش کاربران آنلاین بر اساس access log
- نمودار تاخیر 30 دقیقه اخیر
- جدول ترافیک اوت‌باندها
- نمایش زنده وضعیت سلامت اوت‌باندها

## اسکرین‌شات

<details>
<summary>برای دیدن اسکرین‌شات کلیک کنید</summary>

<p align="center">
  <img src="screenshots/1.png" alt="RayPulse Dashboard" width="100%">
</p>

</details>

## مستندات انگلیسی

برای نسخه انگلیسی این فایل را باز کنید:

**[README.md](./README.md)**

## نصب از فایل ZIP

1. فایل ZIP ریلیز را دانلود کنید
2. روی سرور extract کنید
3. این دستورات را اجرا کنید:

```bash
chmod +x install.sh
./install.sh
```

## نصب‌کننده چه چیزهایی می‌پرسد؟

- آدرس Metrics URL
- مسیر Access Log
- آدرس Bind Host
- شماره پورت
- حالت TLS
- مسیر فایل گواهی TLS
- مسیر فایل کلید TLS

## مسیرهای پیش‌فرض

- Metrics URL: `http://127.0.0.1:11112/debug/vars`
- Access log: `/usr/local/x-ui/access.log`

## مدیریت سرویس

```bash
systemctl status RayPulse
systemctl restart RayPulse
systemctl stop RayPulse
journalctl -u RayPulse -f
```

## حذف پنل

```bash
chmod +x uninstall.sh
./uninstall.sh
```

## نکات مهم

- قبل از استفاده از پورت `443` مطمئن شوید که خالی باشد.
- اگر دامنه را پشت CDN گذاشته‌اید، Origin و TLS باید درست تنظیم شده باشند.
- نمایش ترافیک اوت‌باندها فقط وقتی کار می‌کند که Xray آمار لازم را در `debug/vars` ارائه دهد.

## لینک‌های پروژه

- ریپازیتوری: <https://github.com/Matialz7/RayPulse>
- ریلیز: <https://github.com/Matialz7/RayPulse/releases/tag/v1.0.0>
- فایل ZIP: <https://github.com/Matialz7/RayPulse/releases/download/v1.0.0/RayPulse-v1.0.0.zip>

## لایسنس

MIT
