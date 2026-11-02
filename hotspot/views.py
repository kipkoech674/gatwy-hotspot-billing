import base64
import json
import hashlib
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlsplit

from django.db import IntegrityError, connection, transaction
from django.core.cache import cache
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Location, PassPlan, Purchase
from .mikrotik import provision_device, provision_purchase, router_configured
from .routeros_api import RouterOSError

_provision_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mikrotik-provision")


def portal(request):
    location = Location.objects.filter(is_active=True).first()
    support_phone = location.support_phone if location else "+254716719022"
    default_login_url = f"http://{os.environ.get('MIKROTIK_HOST', '192.168.88.1')}/login"
    login_url = request.GET.get("login_url", default_login_url)[:1024]
    parsed_login = urlsplit(login_url)
    if parsed_login.scheme not in ("http", "https") or not parsed_login.netloc:
        login_url = default_login_url
    destination = request.GET.get("dst", "http://neverssl.com/")[:1024]
    parsed_destination = urlsplit(destination)
    if parsed_destination.scheme not in ("http", "https") or not parsed_destination.netloc:
        destination = "http://neverssl.com/"
    device_mac = _normalise_mac(request.GET.get("mac", ""))
    portal_plans = list(PassPlan.objects.filter(is_active=True).values(
        "id", "code", "name", "duration_seconds", "price_kes", "device_count"
    ))
    for plan in portal_plans:
        seconds = plan["duration_seconds"]
        plan["category"] = (
            "Hourly" if seconds < 24 * 60 * 60 else
            "Daily" if seconds < 7 * 24 * 60 * 60 else
            "Weekly" if seconds < 30 * 24 * 60 * 60 else
            "Monthly"
        )
    return render(request, "portal.html", {
        "support_phone": support_phone,
        "hotspot_login": {
            "destination": destination,
            "device_mac": device_mac,
            "login_url": login_url,
        },
        "portal_plans": portal_plans,
        "payments_enabled": settings.MPESA_PAYMENTS_ENABLED,
    })


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def plans(request):
    items = PassPlan.objects.filter(is_active=True).values(
        "id", "code", "name", "duration_seconds", "price_kes", "device_count"
    )
    return JsonResponse({"plans": list(items)})


def _normalise_phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif digits.startswith("7") or digits.startswith("1"):
        digits = "254" + digits
    if not re.fullmatch(r"254[17]\d{8}", digits):
        return None
    return digits


def _normalise_mac(value):
    digits = re.sub(r"[^0-9a-fA-F]", "", str(value or ""))
    if not re.fullmatch(r"[0-9a-fA-F]{12}", digits):
        return ""
    return ":".join(digits[index:index + 2].upper() for index in range(0, 12, 2))


def _client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _daraja_base_url():
    env = os.environ.get("MPESA_ENVIRONMENT", "sandbox").strip().lower()
    return "https://api.safaricom.co.ke" if env == "production" else "https://sandbox.safaricom.co.ke"


def _mpesa_credentials_present():
    required = ("MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET", "MPESA_SHORTCODE", "MPESA_PASSKEY", "MPESA_CALLBACK_URL")
    callback_url = os.environ.get("MPESA_CALLBACK_URL", "")
    env = os.environ.get("MPESA_ENVIRONMENT", "sandbox").strip().lower()
    return (
        env in ("sandbox", "production")
        and all(os.environ.get(key) for key in required)
        and callback_url.startswith("https://")
    )


def _daraja_access_token():
    cache_key = "daraja:oauth_token"
    cached_token = cache.get(cache_key)
    if cached_token:
        return cached_token

    credentials = f"{os.environ['MPESA_CONSUMER_KEY']}:{os.environ['MPESA_CONSUMER_SECRET']}".encode()
    token = __import__("base64").b64encode(credentials).decode()
    request = urllib.request.Request(
        f"{_daraja_base_url()}/oauth/v1/generate?grant_type=client_credentials",
        headers={"Authorization": f"Basic {token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read())
        access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3599))
        cache.set(cache_key, access_token, timeout=max(60, expires_in - 300))
        return access_token


def _start_stk_push(purchase):
    token = _daraja_access_token()
    eat = dt_timezone(timedelta(hours=3))
    timestamp = datetime.now(eat).strftime("%Y%m%d%H%M%S")
    shortcode = os.environ["MPESA_SHORTCODE"]
    password = __import__("base64").b64encode(
        f"{shortcode}{os.environ['MPESA_PASSKEY']}{timestamp}".encode()
    ).decode()
    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": os.environ.get("MPESA_TRANSACTION_TYPE", "CustomerPayBillOnline"),
        "Amount": purchase.amount_kes,
        "PartyA": purchase.phone_number,
        "PartyB": shortcode,
        "PhoneNumber": purchase.phone_number,
        "CallBackURL": os.environ["MPESA_CALLBACK_URL"],
        "AccountReference": f"HS-{str(purchase.public_id)[:8]}",
        "TransactionDesc": f"Hotspot {purchase.plan.name}",
    }
    request = urllib.request.Request(
        f"{_daraja_base_url()}/mpesa/stkpush/v1/processrequest",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        response_text = exc.read().decode("utf-8", errors="replace")[:500]
        try:
            provider_error = json.loads(response_text)
            detail = (
                provider_error.get("errorMessage")
                or provider_error.get("ResponseDescription")
                or provider_error.get("errorCode")
                or response_text
            )
        except json.JSONDecodeError:
            detail = response_text
        raise ValueError(f"Daraja HTTP {exc.code}: {detail}") from exc
    if str(result.get("ResponseCode")) != "0" or not result.get("CheckoutRequestID") or not result.get("MerchantRequestID"):
        raise ValueError("Daraja did not accept the STK request")
    purchase.merchant_request_id = result.get("MerchantRequestID", "")
    purchase.checkout_request_id = result.get("CheckoutRequestID")
    purchase.status = Purchase.Status.PENDING
    purchase.save(update_fields=["merchant_request_id", "checkout_request_id", "status"])
    return result


def _enqueue_activation(purchase_id):
    def _task():
        try:
            purchase = Purchase.objects.select_related("plan").filter(pk=purchase_id).first()
            if purchase:
                _activate_paid_purchase(purchase)
        finally:
            connection.close()

    _provision_pool.submit(_task)


@require_POST
def checkout(request):
    if not settings.MPESA_PAYMENTS_ENABLED:
        return JsonResponse({"error": "M-Pesa payments are temporarily unavailable while GATWY payment setup is completed."}, status=503)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({"error": "Choose a valid package."}, status=400)
        plan_id = int(data.get("plan_id"))
    except (ValueError, TypeError, json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Choose a valid package."}, status=400)

    phone = _normalise_phone(data.get("phone", ""))
    if not phone:
        return JsonResponse({"error": "Enter a valid Kenyan mobile number."}, status=400)
    device_mac = _normalise_mac(data.get("device_mac", ""))
    if not device_mac:
        return JsonResponse({"error": "Join the Hotspot Wi-Fi first, then open the payment page."}, status=400)

    plan = PassPlan.objects.filter(pk=plan_id, is_active=True).first()
    if not plan:
        return JsonResponse({"error": "That package is unavailable. Refresh and choose another."}, status=404)

    if not _mpesa_credentials_present():
        return JsonResponse({"error": "M-Pesa payment gateway is not configured yet. No payment was requested."}, status=503)

    purchase = Purchase.objects.create(
        plan=plan,
        phone_number=phone,
        device_mac=device_mac,
        amount_kes=plan.price_kes,
        status=Purchase.Status.CREATED,
    )
    try:
        result = _start_stk_push(purchase)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
        purchase.status = Purchase.Status.FAILED
        purchase.payment_error = (str(exc) or type(exc).__name__)[:160]
        purchase.save(update_fields=["status", "payment_error"])
        return JsonResponse({"error": "Could not start the M-Pesa request. Please try again."}, status=502)

    return JsonResponse({
        "purchase_id": str(purchase.public_id),
        "status": purchase.status,
        "message": result.get("CustomerMessage", "Check your phone and approve the M-Pesa request."),
    }, status=202)


@require_GET
def purchase_status(request, public_id):
    purchase = Purchase.objects.select_related("plan").filter(public_id=public_id).first()
    if not purchase:
        return JsonResponse({"error": "Purchase not found."}, status=404)
    status = purchase.status
    if status == Purchase.Status.PAID and purchase.expires_at and purchase.expires_at <= timezone.now():
        status = Purchase.Status.EXPIRED
    access_ready = status == Purchase.Status.PAID and purchase.access_activated_at is not None
    response = JsonResponse({
        "status": status,
        "plan": purchase.plan.name,
        "expires_at": purchase.expires_at,
        "mpesa_receipt": purchase.mpesa_receipt if purchase.status == Purchase.Status.PAID else "",
        "access_activated": access_ready,
        "error": purchase.payment_error or purchase.access_error or "",
    })
    response["Cache-Control"] = "no-store"
    return response


def _activate_paid_purchase(purchase):
    if purchase.access_activated_at:
        return True
    if not router_configured():
        Purchase.objects.filter(pk=purchase.pk).update(access_error="MikroTik API settings are not configured.")
        return False
    try:
        return provision_purchase(purchase)
    except RouterOSError as exc:
        Purchase.objects.filter(pk=purchase.pk).update(access_error=str(exc)[:160])
        return False


@require_POST
def reactivate(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Enter your phone number and M-Pesa receipt code."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Enter your phone number and M-Pesa receipt code."}, status=400)
    device_mac = _normalise_mac(data.get("device_mac", ""))
    if not device_mac:
        return JsonResponse({"error": "Could not detect your device Wi-Fi address. Please reconnect to the Hotspot Wi-Fi."}, status=400)
    phone = _normalise_phone(data.get("phone", ""))
    receipt = re.sub(r"[^A-Za-z0-9]", "", str(data.get("receipt", ""))).upper()
    if not phone or not re.fullmatch(r"[A-Z0-9]{8,12}", receipt):
        return JsonResponse({"error": "Check the phone number and receipt code in your M-Pesa message."}, status=400)
    client_ip = _client_ip(request)
    throttle_key = "reactivate:" + hashlib.sha256(f"{client_ip}:{phone}".encode()).hexdigest()
    attempts = cache.get(throttle_key, 0)
    if attempts >= 8:
        return JsonResponse({"error": "Too many attempts. Please wait a few minutes or call support."}, status=429)
    cache.set(throttle_key, attempts + 1, timeout=300)
    purchase = Purchase.objects.filter(
        phone_number=phone, mpesa_receipt__iexact=receipt,
        status=Purchase.Status.PAID, expires_at__gt=timezone.now(),
    ).select_related("plan").first()
    if not purchase:
        return JsonResponse({"error": "We couldn't find an active package for that phone number and receipt code."}, status=404)
    if not purchase.access_activated_at:
        return JsonResponse({"error": "Payment is confirmed, but Wi-Fi access is still being set up. Please retry shortly or contact support."}, status=503)
    try:
        provision_device(purchase, device_mac)
    except RouterOSError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    response = JsonResponse({
        "status": "active", "plan": purchase.plan.name, "expires_at": purchase.expires_at,
        "devices_connected": purchase.devices.count(),
        "devices_allowed": purchase.plan.device_count,
        "message": "Your device is authorized. Connecting you now.",
    })
    response["Cache-Control"] = "no-store"
    return response


def _callback_value(items, name):
    for item in items:
        if item.get("Name") == name:
            return item.get("Value")
    return None


@csrf_exempt
@require_POST
def mpesa_callback(request):
    """Record matched sandbox callbacks and activate paid HotSpot access."""
    try:
        callback = json.loads(request.body)["Body"]["stkCallback"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Invalid callback payload"}, status=400)

    checkout_id = callback.get("CheckoutRequestID")
    merchant_id = callback.get("MerchantRequestID", "")
    if not checkout_id:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Missing checkout identifier"}, status=400)

    try:
        purchase = Purchase.objects.get(checkout_request_id=checkout_id)
    except Purchase.DoesNotExist:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Purchase not found"}, status=404)

    if purchase.status == Purchase.Status.PAID:
        if not purchase.access_activated_at:
            _enqueue_activation(purchase.pk)
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Callback already processed"})
    if merchant_id and purchase.merchant_request_id != merchant_id:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Request identifier mismatch"}, status=400)

    try:
        result_code = int(callback.get("ResultCode"))
    except (TypeError, ValueError):
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Missing payment result"}, status=400)

    if result_code != 0:
        purchase.status = Purchase.Status.FAILED
        purchase.payment_error = str(callback.get("ResultDesc", "Payment was not completed"))[:160]
        purchase.save(update_fields=["status", "payment_error"])
        return JsonResponse({"ResultCode": 0, "ResultDesc": "Callback processed"})

    metadata = callback.get("CallbackMetadata", {}).get("Item", [])
    receipt = _callback_value(metadata, "MpesaReceiptNumber")
    amount = _callback_value(metadata, "Amount")
    phone = _callback_value(metadata, "PhoneNumber")
    try:
        paid_amount = int(round(float(amount))) if amount is not None else None
    except (ValueError, TypeError):
        paid_amount = None
    normalised_phone = _normalise_phone(phone)

    if not receipt or paid_amount != purchase.amount_kes or normalised_phone != purchase.phone_number:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Payment details did not match"}, status=400)

    paid_at = timezone.now()
    try:
        with transaction.atomic():
            locked = Purchase.objects.select_for_update().get(pk=purchase.pk)
            if locked.status != Purchase.Status.PAID:
                locked.status = Purchase.Status.PAID
                locked.mpesa_receipt = str(receipt)
                locked.paid_at = paid_at
                locked.expires_at = paid_at + timedelta(seconds=locked.plan.duration_seconds)
                locked.save(update_fields=["status", "mpesa_receipt", "paid_at", "expires_at"])
            transaction.on_commit(lambda: _enqueue_activation(purchase.pk))
    except IntegrityError:
        return JsonResponse({"ResultCode": 1, "ResultDesc": "Receipt already recorded"}, status=409)

    return JsonResponse({"ResultCode": 0, "ResultDesc": "Accepted"})
