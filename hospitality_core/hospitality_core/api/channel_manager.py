# -*- coding: utf-8 -*-
"""
Cổng Kết Nối Kênh Phân Phối (Channel Manager Gateway).

Inbound: OTA/channel-manager aggregators (Agoda, Booking.com, Traveloka,
Trip.com, or a middleware like SiteMinder/Channex/Cloudbeds) POST new
bookings to `receive_ota_webhook`. This creates the Guest + Hotel
Reservation (tagged booking_source="OTA") using the same validated
`Document.insert()` path as every other reservation, so availability
checks / folio creation / accounting all behave identically regardless of
where the booking came from.

Outbound: `push_availability` / `push_rates` are the other half of a real
two-way integration (telling the OTA how many rooms/what price is left).
Real OTAs each have their own REST/XML API and require a signed
partnership agreement, so these are stubbed to log intent and return a
mock response until real credentials are configured.
"""
import json

import frappe
from frappe import _
from frappe.utils import getdate


def _get_settings():
    return frappe.get_single("Hospitality Channel Manager Settings")


def _verify_secret(settings, secret):
    if not settings.enabled:
        frappe.throw(_("Channel Manager Gateway is disabled."), frappe.PermissionError)

    expected = settings.get_password("webhook_secret", raise_exception=False)
    if not expected or secret != expected:
        frappe.throw(_("Invalid webhook secret."), frappe.PermissionError)


def _find_or_create_guest(guest_name, mobile_no=None, identification_no=None):
    guest = None
    if identification_no:
        guest = frappe.db.get_value("Guest", {"identification_no": identification_no}, "name")
    if not guest and mobile_no:
        guest = frappe.db.get_value("Guest", {"mobile_no": mobile_no}, "name")

    if guest:
        from hospitality_core.hospitality_core.api.guest_crm import canonical
        return canonical(guest)

    doc = frappe.get_doc({
        "doctype": "Guest",
        "full_name": guest_name,
        "mobile_no": mobile_no,
        "identification_no": identification_no,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _auto_assign_room(room_type, arrival_date, departure_date, property=None):
    """
    Picks the first room of `room_type` with no overlapping Reserved/Checked
    In booking in the requested date range. Raises if none is free — this
    IS the overbooking guard the Channel Manager pillar is meant to provide.
    """
    room_filters = {"room_type": room_type, "is_enabled": 1, "status": ["!=", "Out of Order"]}
    if property:
        room_filters["property"] = property

    candidate_rooms = frappe.get_all(
        "Hotel Room",
        filters=room_filters,
        pluck="name",
        order_by="room_number asc",
    )

    if not candidate_rooms:
        frappe.throw(_("No rooms configured for Room Type {0}.").format(room_type))

    # Lock the candidate rooms for the rest of this DB transaction so a concurrent
    # webhook assigning the same room type/dates blocks here instead of reading the
    # same "free" snapshot and double-booking the same room.
    frappe.db.sql(
        "SELECT name FROM `tabHotel Room` WHERE name IN %(rooms)s FOR UPDATE",
        {"rooms": candidate_rooms},
    )

    booked_rooms = frappe.get_all(
        "Hotel Reservation",
        filters={
            "room": ["in", candidate_rooms],
            "status": ["in", ["Reserved", "Checked In"]],
            "arrival_date": ["<", departure_date],
            "departure_date": [">", arrival_date],
        },
        pluck="room",
    )
    booked_set = set(booked_rooms)

    for room in candidate_rooms:
        if room not in booked_set:
            return room

    frappe.throw(_(
        "No available room of type {0} for {1} → {2}. Overbooking prevented."
    ).format(room_type, arrival_date, departure_date))


@frappe.whitelist(allow_guest=True)
def receive_ota_webhook(platform, secret, payload):
    """
    Inbound webhook entry point. Expected `payload` (dict or JSON string):
        {
            "guest_name": "...", "mobile_no": "...", "identification_no": "...",
            "room_type": "Deluxe", "arrival_date": "2026-09-01",
            "departure_date": "2026-09-03", "external_booking_id": "AGD-12345"
        }
    """
    settings = _get_settings()
    _verify_secret(settings, secret)

    platform_flags = {
        "Agoda": settings.enable_agoda,
        "Booking.com": settings.enable_booking_com,
        "Traveloka": settings.enable_traveloka,
        "Trip.com": settings.enable_trip_com,
    }
    if platform not in platform_flags:
        frappe.throw(_("Unknown platform: {0}").format(platform))
    if not platform_flags[platform]:
        frappe.throw(_("Platform {0} is not enabled in Hospitality Channel Manager Settings.").format(platform))

    if isinstance(payload, str):
        payload = json.loads(payload)

    required = ["guest_name", "room_type", "arrival_date", "departure_date", "external_booking_id"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        frappe.throw(_("Missing required fields: {0}").format(", ".join(missing)))

    arrival_date = getdate(payload["arrival_date"])
    departure_date = getdate(payload["departure_date"])

    # Khóa mutex đặt tên (MySQL GET_LOCK) theo (platform, external_booking_id)
    # — TRƯỚC ĐÂY câu kiểm tra "đã tồn tại chưa" chỉ là 1 SELECT thường, không
    # khóa gì cả: 2 lần gọi webhook gần như đồng thời cho CÙNG 1 booking (OTA
    # gửi trùng do retry mạng, hoặc do chính OTA gửi 2 lần) đều có thể cùng
    # đọc thấy "chưa tồn tại" trước khi bên kia kịp insert, rồi cả hai cùng
    # tạo ra 2 Hotel Reservation cho cùng 1 booking thật — double-book cùng 1
    # phòng, khách phải trả tiền 2 lần nếu cả 2 đều được check-in/tính tiền.
    # Không có dòng nào sẵn có để SELECT...FOR UPDATE (bản ghi CHƯA tồn tại),
    # nên dùng named lock cấp DB để tuần tự hóa toàn bộ đoạn kiểm tra+tạo mới.
    lock_key = f"ota_webhook:{platform}:{payload['external_booking_id']}"
    got_lock = frappe.db.sql("SELECT GET_LOCK(%s, 10)", lock_key)[0][0]
    if not got_lock:
        frappe.throw(_("Hệ thống đang xử lý một booking khác trùng mã tham chiếu này. Vui lòng thử lại sau."))

    try:
        existing = frappe.db.get_value(
            "Hotel Reservation",
            {"external_booking_id": payload["external_booking_id"], "ota_platform": platform},
            "name",
        )
        if existing:
            return {"reservation": existing, "status": "already_exists"}

        if not settings.default_hotel_reception:
            frappe.throw(_("Please set a Default Hotel Reception in Hospitality Channel Manager Settings."))

        guest = _find_or_create_guest(
            payload["guest_name"], payload.get("mobile_no"), payload.get("identification_no")
        )
        prop = payload.get("property")
        room = _auto_assign_room(payload["room_type"], arrival_date, departure_date, property=prop)
        room_prop = frappe.db.get_value("Hotel Room", room, "property")
        resolved_prop = prop or room_prop

        res_data = {
            "doctype": "Hotel Reservation",
            "hotel_reception": settings.default_hotel_reception,
            "guest": guest,
            "room_type": payload["room_type"],
            "room": room,
            "arrival_date": arrival_date,
            "departure_date": departure_date,
            "booking_source": "OTA",
            "ota_platform": platform,
            "external_booking_id": payload["external_booking_id"],
        }
        if resolved_prop:
            res_data["property"] = resolved_prop
        reservation = frappe.get_doc(res_data)
        reservation.insert(ignore_permissions=True)

        frappe.logger("channel_manager").info(
            f"OTA booking received: platform={platform} ref={payload['external_booking_id']} -> {reservation.name}"
        )

        return {"reservation": reservation.name, "room": room, "guest": guest, "status": "created"}
    finally:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", lock_key)


@frappe.whitelist()
def push_availability(room_type, start_date, end_date, property=None):
    """
    MOCK: would call each enabled OTA's inventory API to push remaining
    room-nights for `room_type` between start_date/end_date. Wire in real
    HTTP calls per platform once partnership API credentials exist.
    """
    # TRƯỚC ĐÂY: không hề kiểm tra quyền — hiện tại chỉ là mock/log nên rủi ro
    # thấp, nhưng cần chặn TRƯỚC KHI có API key/tích hợp thật, không phải sau.
    if not frappe.has_permission("Hospitality Channel Manager Settings", "write"):
        frappe.throw(_("Not permitted to manage channel manager integrations."), frappe.PermissionError)
    settings = _get_settings()
    enabled_platforms = [
        name for name, flag in {
            "Agoda": settings.enable_agoda,
            "Booking.com": settings.enable_booking_com,
            "Traveloka": settings.enable_traveloka,
            "Trip.com": settings.enable_trip_com,
        }.items() if flag
    ]

    room_filters = {"room_type": room_type, "is_enabled": 1, "status": ["!=", "Out of Order"]}
    res_filters = {
        "room_type": room_type,
        "status": ["in", ["Reserved", "Checked In"]],
        "arrival_date": ["<", end_date],
        "departure_date": [">", start_date],
    }
    if property:
        room_filters["property"] = property
        res_filters["property"] = property

    available_count = frappe.db.count("Hotel Room", room_filters) - len(
        frappe.get_all("Hotel Reservation", filters=res_filters)
    )

    frappe.logger("channel_manager").info(
        f"[MOCK] push_availability room_type={room_type} {start_date}->{end_date} "
        f"available={available_count} platforms={enabled_platforms}"
    )

    return {"mode": "mock", "platforms": enabled_platforms, "available": max(available_count, 0)}


@frappe.whitelist()
def push_rates(room_type, date, rate):
    """MOCK: would call each enabled OTA's rate API to update the sell rate."""
    if not frappe.has_permission("Hospitality Channel Manager Settings", "write"):
        frappe.throw(_("Not permitted to manage channel manager integrations."), frappe.PermissionError)
    settings = _get_settings()
    enabled_platforms = [
        name for name, flag in {
            "Agoda": settings.enable_agoda,
            "Booking.com": settings.enable_booking_com,
            "Traveloka": settings.enable_traveloka,
            "Trip.com": settings.enable_trip_com,
        }.items() if flag
    ]
    frappe.logger("channel_manager").info(
        f"[MOCK] push_rates room_type={room_type} date={date} rate={rate} platforms={enabled_platforms}"
    )
    return {"mode": "mock", "platforms": enabled_platforms}
