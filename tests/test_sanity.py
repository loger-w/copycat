from __future__ import annotations

import copycat


def test_package_importable() -> None:
    assert copycat.__doc__ is not None
