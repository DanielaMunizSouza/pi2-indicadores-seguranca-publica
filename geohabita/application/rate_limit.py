"""Limite de requisições por endereço IP.

Cobre o limite de 60 requisições por minuto por endereço IP nas rotas
públicas (RNF08). Requisições acima do limite recebem HTTP 429. Clientes
inativos há mais de uma janela são esquecidos, para que a memória não cresça
com cada IP que já passou pelo site.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

REQUESTS_PER_WINDOW = 60
WINDOW_S = 60.0


class RateLimiter:
    """Janela deslizante de requisições por cliente."""

    def __init__(
        self,
        limit: int = REQUESTS_PER_WINDOW,
        window_s: float = WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self._requests: dict[str, deque[float]] = {}
        self._next_cleanup = clock() + window_s

    def _forget_idle_clients(self, now: float) -> None:
        idle = [c for c, times in self._requests.items() if not times or now - times[-1] >= self.window_s]
        for client in idle:
            del self._requests[client]
        self._next_cleanup = now + self.window_s

    def allow(self, client: str) -> bool:
        """Registra a requisição e indica se ela está dentro do limite."""
        now = self.clock()
        if now >= self._next_cleanup:
            self._forget_idle_clients(now)
        requests = self._requests.setdefault(client, deque())
        while requests and now - requests[0] >= self.window_s:
            requests.popleft()
        if len(requests) >= self.limit:
            return False
        requests.append(now)
        return True
