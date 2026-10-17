"""Print a fresh VAPID key pair for Web Push check-in reminders.

    python generate_vapid_keys.py

Paste the two lines into .env locally and into the cPanel "Setup Python App"
environment variables on the server. Never commit them. Generating a new
pair later invalidates every device's subscription; turn reminders back on
from the Today page afterwards.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main():
    key = ec.generate_private_key(ec.SECP256R1())
    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    print(f"VAPID_PUBLIC_KEY={b64url(public_raw)}")
    print(f"VAPID_PRIVATE_KEY={b64url(private_raw)}")


if __name__ == "__main__":
    main()
