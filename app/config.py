import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://lab:lab@localhost:5432/lab")
    pool_max_size: int = _int("POOL_MAX_SIZE", 10)

    # Valores para o seu código de resiliência. A infraestrutura não usa nenhum deles.
    timeout_ms: int = _int("TIMEOUT_MS", 1000)
    bulkhead_max_concurrent: int = _int("BULKHEAD_MAX_CONCURRENT", 6)
    bulkhead_max_wait_ms: int = _int("BULKHEAD_MAX_WAIT_MS", 50)
    breaker_failure_threshold: int = _int("BREAKER_FAILURE_THRESHOLD", 5)
    breaker_recovery_ms: int = _int("BREAKER_RECOVERY_MS", 5000)


settings = Settings()
