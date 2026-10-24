"""Testes do limite de requisições (RNF08).

O caso CT16 da especificação envia 61 requisições em um minuto a partir do
mesmo IP; a 61ª deve ser recusada.
"""

from geohabita.application.rate_limit import REQUESTS_PER_WINDOW, WINDOW_S, RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limit_is_sixty_requests_per_minute():
    assert (REQUESTS_PER_WINDOW, WINDOW_S) == (60, 60.0)


def test_ct16_sixty_first_request_is_refused():
    limiter = RateLimiter(clock=FakeClock())
    results = [limiter.allow("203.0.113.7") for _ in range(61)]
    assert all(results[:60])
    assert results[60] is False


def test_clients_are_counted_separately():
    limiter = RateLimiter(limit=1, clock=FakeClock())
    assert limiter.allow("203.0.113.7") is True
    assert limiter.allow("198.51.100.2") is True
    assert limiter.allow("203.0.113.7") is False


def test_requests_older_than_window_stop_counting():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window_s=60, clock=clock)
    assert limiter.allow("ip") and limiter.allow("ip")
    clock.now += 30
    assert limiter.allow("ip") is False
    clock.now += 30.1
    assert limiter.allow("ip") is True


def test_refused_requests_do_not_extend_the_block():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_s=60, clock=clock)
    limiter.allow("ip")
    for _ in range(5):
        clock.now += 10
        limiter.allow("ip")
    clock.now += 10.1
    assert limiter.allow("ip") is True
