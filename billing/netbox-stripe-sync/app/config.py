import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    netbox_base_url: str
    netbox_token: str
    stripe_webhook_secret: str
    event_store_path: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            netbox_base_url=_required("NETBOX_BASE_URL").rstrip("/"),
            netbox_token=_required("NETBOX_TOKEN"),
            stripe_webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", "").strip(),
            event_store_path=os.getenv("EVENT_STORE_PATH", "/data/events.db"),
        )
