import os
from django.db import transaction
from django.utils import timezone

from .models import HotspotDevice
from .routeros_api import RouterOSAPI, RouterOSError


PROFILE_NAMES = {1: "billing-one-device", 2: "billing-two-devices"}


def router_configured():
    return all(os.environ.get(name) for name in (
        "MIKROTIK_HOST", "MIKROTIK_USERNAME", "MIKROTIK_PASSWORD"
    ))


def get_router():
    return _router()


def _router():
    if not router_configured():
        raise RouterOSError("MikroTik API settings are not configured.")
    return RouterOSAPI(
        os.environ["MIKROTIK_HOST"],
        os.environ["MIKROTIK_USERNAME"],
        os.environ["MIKROTIK_PASSWORD"],
        port=os.environ.get("MIKROTIK_PORT", "8728"),
    )


def _find(router, path, name):
    return router.command(
        f"{path}/print",
        attributes={".proplist": ".id,name,profile,disabled"},
        queries=(f"name={name}",),
    )


def ensure_profile(router, device_count):
    name = PROFILE_NAMES.get(device_count)
    if not name:
        raise RouterOSError("Unsupported package device count.")
    if not _find(router, "/ip/hotspot/user/profile", name):
        router.command("/ip/hotspot/user/profile/add", {
            "name": name,
            "rate-limit": "5M/5M",
            "shared-users": str(device_count),
        })
    return name


def provision_purchase(purchase, router=None):
    """Authorize the device that started a paid purchase."""
    if not purchase.device_mac:
        raise RouterOSError("The customer device address was not received from the HotSpot.")
    return provision_device(purchase, purchase.device_mac, router=router)


def provision_device(purchase, mac_address, router=None):
    """Authorize one device by its MAC address for an active paid purchase."""
    if not router_configured():
        return False
    with transaction.atomic():
        locked = purchase.__class__.objects.select_for_update().select_related("plan").get(pk=purchase.pk)
        if locked.status != purchase.Status.PAID or not locked.expires_at or locked.expires_at <= timezone.now():
            return False
        device = HotspotDevice.objects.select_for_update().filter(mac_address=mac_address).first()
        if device and device.purchase_id != locked.pk:
            previous = device.purchase
            if previous.status == previous.Status.PAID and previous.expires_at and previous.expires_at > timezone.now():
                raise RouterOSError("This device already has an active Wi-Fi package.")
            if locked.devices.count() >= locked.plan.device_count:
                raise RouterOSError("This package has reached its device limit.")
            device.purchase = locked
            device.save(update_fields=["purchase"])
        elif not device:
            if locked.devices.count() >= locked.plan.device_count:
                raise RouterOSError("This package has reached its device limit.")
            HotspotDevice.objects.create(purchase=locked, mac_address=mac_address)
        username = mac_address

    def _apply_router(r):
        profile = ensure_profile(r, locked.plan.device_count)
        existing = _find(r, "/ip/hotspot/user", username)
        if existing:
            user = existing[0]
            r.command("/ip/hotspot/user/set", {
                ".id": user[".id"],
                "password": username,
                "profile": profile,
                "disabled": "no",
                "comment": f"billing-device:{purchase.public_id}",
            })
        else:
            try:
                r.command("/ip/hotspot/user/add", {
                    "name": username,
                    "password": username,
                    "profile": profile,
                    "comment": f"billing-device:{purchase.public_id}",
                })
            except RouterOSError:
                if not _find(r, "/ip/hotspot/user", username):
                    raise

    try:
        if router is not None:
            _apply_router(router)
        else:
            with _router() as active_router:
                _apply_router(active_router)
    except RouterOSError:
        raise
    if not purchase.access_activated_at:
        purchase.access_activated_at = timezone.now()
    purchase.access_error = ""
    purchase.save(update_fields=["access_activated_at", "access_error"])
    return True


def remove_purchase_user(username, router=None):
    """Disconnect active sessions and remove an expired purchase account."""
    if not username or not router_configured():
        return False

    def _cleanup(r):
        sessions = r.command(
            "/ip/hotspot/active/print",
            attributes={".proplist": ".id,user"},
            queries=(f"user={username}",),
        )
        for session in sessions:
            if ".id" in session:
                r.command("/ip/hotspot/active/remove", {".id": session[".id"]})
        users = _find(r, "/ip/hotspot/user", username)
        for user in users:
            if ".id" in user:
                r.command("/ip/hotspot/user/remove", {".id": user[".id"]})
        return True

    if router is not None:
        return _cleanup(router)
    with _router() as r:
        return _cleanup(r)


def remove_purchase_devices(purchase, router=None):
    """Disconnect and remove all MAC-authorized devices for an expired purchase."""
    usernames = {device.mac_address for device in purchase.devices.all() if device.mac_address}
    if purchase.device_mac:
        usernames.add(purchase.device_mac)
    if purchase.router_username:
        usernames.add(purchase.router_username)

    if router is not None:
        for name in usernames:
            remove_purchase_user(name, router=router)
    else:
        with _router() as r:
            for name in usernames:
                remove_purchase_user(name, router=r)
