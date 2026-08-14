"""
SENZO LICENSE MANAGER — OWNER TOOL ONLY (never share with users)

Generates RSA-2048 keys, issues per-user signed license files,
verifies licenses, and prints machine ID helper strings.

Usage:
    python senzo_license.py keygen                  first time only — creates keys
    python senzo_license.py machine                 get YOUR machine id (owner demo)
    python senzo_license.py issue -m <MACHINE_ID> -u <USERNAME> [-d 365]
                                                    issue one license file
    python senzo_license.py verify <file.lic>       verify a license file
"""

import argparse
import base64
import json
import os
import sys
import hashlib
import platform
from datetime import datetime, timedelta, timezone

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
except ImportError:  # cryptography not installed — fall back to pycryptodome?
    raise SystemExit("Install with:  pip install cryptography")

PRODUCT = "Senzo Desktop Cloner"
KEYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licenses")


def ensure_keys():
    os.makedirs(KEYS_DIR, exist_ok=True)
    priv_path = os.path.join(KEYS_DIR, "senzo_owner.key")
    pub_path = os.path.join(KEYS_DIR, "senzo_public.key")
    if not os.path.exists(priv_path) or not os.path.exists(pub_path):
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537,
                                       key_size=2048,
                                       backend=default_backend())
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())
        with open(priv_path, "wb") as f:
            f.write(pem)
        pub = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        with open(pub_path, "wb") as f:
            f.write(pub)
        print("New RSA keypair created in licenses/")
        print("KEEP senzo_owner.key SECRET — never share it.")
    return priv_path, pub_path


def load_private():
    priv_path, _ = ensure_keys()
    with open(priv_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None,
                                                  backend=default_backend())


def machine_id():
    """Stable fingerprint of this PC: mac + hostname + username."""
    try:
        import uuid
        mac = uuid.getnode()
    except Exception:
        mac = 0
    raw = f"{mac}:{platform.node()}:{platform.uname().machine}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"SENZO-MC-{h}"


def issue(user, machine, days=365):
    key = load_private()
    payload = {
        "user": user,
        "machine_id": machine,
        "product": PRODUCT,
        "issued": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "expires": (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d"),
    }
    data = json.dumps(payload, separators=(",", ":")).encode()
    sig = key.sign(data, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256())
    lic = {"payload": base64.b64encode(data).decode(),
           "signature": base64.b64encode(sig).decode()}
    lic_text = base64.b64encode(json.dumps(lic).encode()).decode()
    out = os.path.join(KEYS_DIR, f"SENZO_{user}.lic")
    with open(out, "w") as f:
        f.write(lic_text)
    print(f"License issued: {out}")
    print(f"  user: {user}   machine: {machine}   expires: {lic['payload']}")
    print("Send this file to the user. They paste/activate it in the app.")
    return lic_text


def licprint(user, machine, days=365):
    """Issue and print the raw license key string — safe to paste/DM in
    Telegram. No file created. Used by the owner bot activate flow."""
    key = load_private()
    payload = {
        "user": user,
        "machine_id": machine,
        "product": PRODUCT,
        "issued": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "expires": (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d"),
    }
    data = json.dumps(payload, separators=(",", ":")).encode()
    sig = key.sign(data, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256())
    lic = {"payload": base64.b64encode(data).decode(),
           "signature": base64.b64encode(sig).decode()}
    print(base64.b64encode(json.dumps(lic).encode()).decode())


def verify(path):
    _, pub_path = ensure_keys()
    with open(pub_path, "rb") as f:
        pub = serialization.load_pem_public_key(f.read(),
                                                backend=default_backend())
    raw = base64.b64decode(open(path, "rb").read())
    lic = json.loads(raw.decode())
    data = base64.b64decode(lic["payload"].encode())
    sig = base64.b64decode(lic["signature"].encode())
    try:
        pub.verify(sig, data, padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
        payload = json.loads(data.decode())
        print("VALID LICENSE")
        for k, v in payload.items():
            print(f"  {k}: {v}")
        if payload["expires"] < datetime.now(timezone.utc).strftime("%Y-%m-%d"):
            print("  WARNING: license expired")
        return True
    except Exception as e:
        print(f"INVALID LICENSE: {e}")
        return False


def public_key_pem():
    """Return the public key PEM as bytes — embedded in the desktop app."""
    _, pub_path = ensure_keys()
    return open(pub_path, "rb").read()


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("keygen", help="generate RSA keypair (first time)")
    sub.add_parser("machine", help="print this PC's machine id")
    i = sub.add_parser("issue", help="issue a license")
    i.add_argument("-m", "--machine", required=True)
    i.add_argument("-u", "--user", required=True)
    i.add_argument("-d", "--days", type=int, default=365)
    lp = sub.add_parser("licprint", help="print license key text (Telegram-safe)")
    lp.add_argument("-m", "--machine", required=True)
    lp.add_argument("-u", "--user", required=True)
    lp.add_argument("-d", "--days", type=int, default=365)
    v = sub.add_parser("verify")
    v.add_argument("file")
    a = p.parse_args()
    if a.cmd == "keygen":
        ensure_keys()
    elif a.cmd == "machine":
        print(machine_id())
    elif a.cmd == "issue":
        issue(a.user, a.machine, a.days)
    elif a.cmd == "licprint":
        licprint(a.user, a.machine, a.days)
    elif a.cmd == "verify":
        verify(a.file)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
