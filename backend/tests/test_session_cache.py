from typing import cast

from app.analysis import AnalysisBundle
from app.session_cache import AnalysisSessionCache


def test_session_cache_expires_and_evicts_oldest_analysis() -> None:
    now = [100.0]
    cache = AnalysisSessionCache(
        ttl_seconds=30,
        max_sessions=2,
        clock=lambda: now[0],
    )
    first_bundle = cast(AnalysisBundle, object())
    second_bundle = cast(AnalysisBundle, object())
    third_bundle = cast(AnalysisBundle, object())

    first_id = cache.create(first_bundle, "USD")
    second_id = cache.create(second_bundle, "USD")
    third_id = cache.create(third_bundle, "USD")

    assert cache.get(first_id) is None
    assert cache.get(second_id) is not None
    assert cache.get(third_id) is not None

    now[0] = 131.0

    assert cache.get(second_id) is None
    assert cache.get(third_id) is None
