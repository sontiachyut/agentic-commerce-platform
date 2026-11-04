"""Original fictional pharmacy fixtures. Never representations of real patients/stores."""

import uuid

from sqlalchemy import select

from commerce.pharmacy.models import (
    Facility,
    FacilityStock,
    FamilyMember,
    Household,
    RoutineItem,
    StaffAssignment,
)

ROUTINES = [
    ("self", "Alex Rivera", "You", "vitamin-d3", "Vitamin D3", "One saved bottle", "OTC", 1199),
    (
        "dad",
        "David Rivera",
        "Father",
        "atorvastatin",
        "Atorvastatin",
        "Existing prescription · 30-tablet fill",
        "RX",
        950,
    ),
    (
        "mom",
        "Elena Rivera",
        "Mother",
        "levothyroxine",
        "Levothyroxine",
        "Existing prescription · 30-tablet fill",
        "RX",
        700,
    ),
    (
        "sister",
        "Maya Rivera",
        "Sister",
        "cetirizine",
        "Cetirizine",
        "One saved allergy-care package",
        "OTC",
        1249,
    ),
]
FACILITIES = [
    ("northbank", "Northbank", "14 Northbank Walk, Asterfield", 37.784, -122.408),
    ("cedar", "Cedar Square", "208 Cedar Avenue, Asterfield", 37.774, -122.416),
    ("lakeside", "Lakeside", "36 Lakeview Lane, Asterfield", 37.768, -122.430),
]


def key(value):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "asterfield-demo:" + value))


def ensure_demo(factory, actor):
    with factory.begin() as db:
        # Stable synthetic identities make provisioning idempotent under concurrent browser requests.
        db.execute(
            __import__("sqlalchemy").text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
            {"scope": "pharmacy-seed:" + actor.tenant_id},
        )
        for slug, name, address, lat, lon in FACILITIES:
            facility_id = key(actor.tenant_id + ":" + slug)
            if not db.get(Facility, facility_id):
                db.add(
                    Facility(
                        id=facility_id,
                        tenant_id=actor.tenant_id,
                        name=name,
                        address=address,
                        latitude=lat,
                        longitude=lon,
                    )
                )
                db.flush()
                for _, _, _, sku, _, _, _, _ in ROUTINES:
                    db.add(
                        FacilityStock(
                            id=key(facility_id + ":" + sku),
                            facility_id=facility_id,
                            sku=sku,
                            stock=0 if slug == "northbank" and sku == "levothyroxine" else 10,
                        )
                    )
        if actor.role == "operator":
            facility_id = key(actor.tenant_id + ":cedar")
            existing = db.scalar(
                select(StaffAssignment).where(
                    StaffAssignment.tenant_id == actor.tenant_id,
                    StaffAssignment.user_id == actor.user_id,
                    StaffAssignment.facility_id == facility_id,
                )
            )
            if not existing:
                db.add(
                    StaffAssignment(
                        id=key(actor.tenant_id + ":" + actor.user_id + ":staff"),
                        tenant_id=actor.tenant_id,
                        user_id=actor.user_id,
                        facility_id=facility_id,
                    )
                )
            return None
        identifier = key(actor.tenant_id + ":" + actor.user_id + ":household")
        if not db.get(Household, identifier):
            db.add(
                Household(
                    id=identifier,
                    tenant_id=actor.tenant_id,
                    user_id=actor.user_id,
                    home_label="72 Cedar Row, Asterfield",
                    latitude=37.782,
                    longitude=-122.409,
                )
            )
            db.flush()
            for alias, name, relationship, sku, title, package, kind, price in ROUTINES:
                member_id = key(identifier + ":" + alias)
                db.add(
                    FamilyMember(
                        id=member_id,
                        household_id=identifier,
                        alias=alias,
                        name=name,
                        relationship=relationship,
                    )
                )
                db.flush()
                db.add(
                    RoutineItem(
                        id=key(member_id + ":regular"),
                        member_id=member_id,
                        sku=sku,
                        name=title,
                        package=package,
                        kind=kind,
                        price_minor=price,
                    )
                )
        return identifier
