from __future__ import annotations


def is_reusable_license(value: str | None) -> bool:
    """Allow permissive/share-alike licenses and reject NC/ND variants."""
    license_text = (value or "").strip().casefold().replace("_", "-")
    blocked = ("non-commercial", "noncommercial", "no derivatives", "no-derivatives", "by-nc", "by-nd")
    if not license_text or any(term in license_text for term in blocked):
        return False
    accepted = (
        "cc0", "cc-by", "cc by", "cc-by-sa", "cc by-sa",
        "public domain", "public-domain", "gfdl", "gnu free documentation license",
    )
    return any(term in license_text for term in accepted)
