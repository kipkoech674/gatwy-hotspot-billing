# Hotspot Billing System

## Agreed requirements

- Start with one location; keep locations configurable for future expansion.
- Customers buy time-based internet access and are activated after successful M-Pesa STK Push payment.
- Use Safaricom Daraja M-Pesa Express while development is in progress. Payments remain disabled until a live Till or PayBill, production credentials, and stable HTTPS hosting are ready.
- Package duration starts when payment succeeds and continues while the customer is disconnected.
- Apply a 5 Mbps limit to each connected device.
- Two-device access is available only with the two-device 14-day and 30-day packages.
- Offer an optional voucher login path.
- Customer support: +254 716 719 022.
- One owner admin account initially.
- Router: MikroTik hAP lite (RB941-2nD), RouterOS 6.45.9.

## Initial package catalogue

| Duration | One device | Two devices |
|---|---:|---:|
| 1 hour | KSh 10 | — |
| 3 hours | KSh 20 | — |
| 12 hours | KSh 40 | — |
| 24 hours | KSh 50 | — |
| 7 days | KSh 250 | — |
| 14 days | KSh 300 | KSh 400 |
| 30 days | KSh 600 | KSh 750 |

## Router notes

- Upstream connection is on `ether1`, using DHCP from `192.168.100.1`.
- Customer Wi-Fi is `wlan1`, bridged with the LAN ports.
- LAN network is `192.168.88.0/24`, with the router at `192.168.88.1` and a DHCP pool of `192.168.88.10-192.168.88.254`.
- The LAN address was moved from `ether2` to `bridge` and committed in RouterOS Safe Mode.
- The `customer-wifi` HotSpot server is configured on `bridge` and directs unauthenticated customers to the local billing portal.
- The billing laptop has a fixed address of `192.168.88.253`, is allowed through the HotSpot on port 8000, and is bypassed for router management.
- The router has 32 MiB RAM with about 7 MiB free, so the billing application must run on a separate computer or hosted server.

## Build outline

1. Customer portal for package selection, phone number, STK Push, and voucher redemption.
2. Payment callback handling with duplicate-safe transaction processing.
3. MikroTik integration to create access accounts, apply one- or two-device limits and per-device speed limits, and expire packages.
4. Owner admin area for packages and prices, payments, customers, vouchers, and location settings.
5. Deployment configuration for a public HTTPS callback URL and protected Daraja and router credentials.

Daraja production credentials and a registered shortcode will be needed before collecting real payments. RouterOS API access and the final Hotspot configuration will be set up after the application flow is ready.

## Current application scaffold

- Django with SQLite for local development. Django 5.2 is the long-term support line; Python 3.14 is supported by Django 5.2.8 and later.
- Django Admin is the owner dashboard. Create only the owner's account with `createsuperuser`.
- The customer portal lists the seeded packages and accepts a Kenyan M-Pesa number.
- STK Push is intentionally paused. Do not enable payments until a live Till or PayBill, production Daraja credentials, and a stable public HTTPS callback address are ready.
- Local MikroTik API access uses port 8728 and is restricted on the router to the app PC's fixed LAN address. Set `MIKROTIK_HOST`, `MIKROTIK_PORT`, `MIKROTIK_USERNAME`, and `MIKROTIK_PASSWORD` in the app process environment; do not expose the API port to the internet.
- Run `python manage.py check_mikrotik` to verify the local router API credentials and connection without changing router settings.
- A matched paid callback provisions a MikroTik HotSpot user with a 5 Mbps profile and the package device limit when the router is reachable. Run `python manage.py run_access_sync` in a separate terminal to retry failed activations and remove expired accounts every minute.
- After payment activation, the customer page submits the generated HotSpot credentials to the router login form automatically. This local prototype uses HTTP-PAP for that handoff; use only with the app and router on the trusted local network, and move the portal to HTTPS before real payments.
- `router/login.html` is the MikroTik captive-portal handoff page. Its content has been installed as `hotspot/login.html` on the router.
- Production M-Pesa activation and public HTTPS deployment remain to be completed. Localhost cannot receive Daraja callbacks.
- `.env.example` is a reference for required settings. The local Django settings load `.env` automatically. Do not commit real credentials.

### Local setup on Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DJANGO_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/` for the customer portal and `http://127.0.0.1:8000/admin/` for owner management. The local development server is not a public Daraja callback destination; sandbox payment requests need an HTTPS callback that can reach the app.

In a second terminal, keep package expiry running:

```powershell
.\.venv\Scripts\python.exe manage.py run_access_sync
```
