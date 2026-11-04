"""Let a phone on the same Wi-Fi open the customer site, with its microphone.

Phones only allow the microphone on a secure page (https). For the demo the PC makes its own certificate
(self-signed: valid for this PC's addresses only). The phone shows a warning the first time ("not
private"); accept it once and the call page works. The private key stays in frontend/certs/, which git
ignores, so it is never committed.

Run once: ``callverse phone-cert``, then start the site with ``npm run dev:phone`` (in frontend/).
"""

# How it works: lan_addresses() finds this PC's IPv4 addresses on the local network; make_certificate()
# writes a certificate valid for those addresses (and localhost) for one year, with the cryptography library.
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from callverse.config import PROJECT_ROOT

CERT_DIR = PROJECT_ROOT / "frontend" / "certs"
CERT_FILE = CERT_DIR / "callverse-dev.crt"
KEY_FILE = CERT_DIR / "callverse-dev.key"
PHONE_PORT = 5173
PHONE_PATH = "/phone"


def lan_addresses() -> list[str]:
    """This PC's IPv4 addresses on the local network (the ones a phone on the same Wi-Fi can reach)."""
    found: set[str] = set()
    try:
        # A UDP "connection" sends nothing: it only asks the system which address it would use.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            found.add(probe.getsockname()[0])
    except OSError:
        pass  # no network route: fall back on the host name's addresses
    try:
        found.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return sorted(a for a in found if not a.startswith(("127.", "169.254.")))


def phone_links(addresses: list[str] | None = None) -> list[str]:
    """The links to open on the phone."""
    return [f"https://{a}:{PHONE_PORT}{PHONE_PATH}" for a in (addresses or lan_addresses())]


def certificate_ready() -> bool:
    return CERT_FILE.exists() and KEY_FILE.exists()


def make_certificate(addresses: list[str] | None = None, days: int = 365) -> tuple[Path, Path]:
    """Write a self-signed certificate for localhost and this PC's network addresses."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    addresses = addresses if addresses is not None else lan_addresses()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CallVerse local demo")])
    # The names and addresses the certificate is valid for (the phone checks the address it opened).
    alternative = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    alternative += [x509.IPAddress(ipaddress.ip_address(a)) for a in addresses]
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)  # self-signed: it vouches for itself
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(alternative), critical=False)
        .sign(key, hashes.SHA256())
    )
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CERT_FILE.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return CERT_FILE, KEY_FILE
