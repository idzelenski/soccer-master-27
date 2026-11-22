from app.data_policy import is_reusable_license


def test_free_and_share_alike_licenses_are_allowed():
    assert is_reusable_license("CC BY 4.0")
    assert is_reusable_license("CC BY-SA 4.0")
    assert is_reusable_license("CC0 1.0")
    assert is_reusable_license("Public domain")
    assert is_reusable_license("GFDL")


def test_noncommercial_and_no_derivatives_licenses_are_rejected():
    assert not is_reusable_license("CC BY-NC 4.0")
    assert not is_reusable_license("CC BY-ND 4.0")
    assert not is_reusable_license("CC BY-NC-SA 4.0")
    assert not is_reusable_license("")
    assert not is_reusable_license(None)
