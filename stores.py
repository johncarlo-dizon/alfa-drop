import ipaddress
import os

from config import STORES_FILE

TEMPLATE = """# AlfaDrop store list
# A line without commas is a group name (DC). The store lines under it use:
#   ip, username, password, name, code, pos
#
# Example:
# DC Mexico
# 172.26.187.81, Server, mypassword, ATP SAN CARLOS, 3138, SERVER
"""


def _is_ip(text):
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def ensure_stores_file():
    if not os.path.exists(STORES_FILE):
        try:
            with open(STORES_FILE, "w", encoding="utf-8") as f:
                f.write(TEMPLATE)
        except OSError:
            pass


def load_stores():
    """Parse stores.txt. Returns (stores, warnings).
    stores: list of dicts {ip, user, pwd, dc, name, code, pos}"""
    ensure_stores_file()
    stores, warnings = [], []
    if not os.path.exists(STORES_FILE):
        return stores, warnings

    current_dc = "Ungrouped"
    seen_ips = {}
    with open(STORES_FILE, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if "," not in line:
                if _is_ip(line):
                    warnings.append(f"stores.txt line {lineno}: '{line}' is an IP with no login — skipped.")
                else:
                    current_dc = line
                continue

            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                warnings.append(f"stores.txt line {lineno}: needs at least ip,user,pwd — skipped.")
                continue

            ip, user, pwd = parts[0], parts[1], parts[2]
            if not _is_ip(ip):
                if ip.lower() != "ip":
                    warnings.append(f"stores.txt line {lineno}: '{ip}' is not a valid IP — skipped.")
                continue

            name = parts[3] if len(parts) > 3 and parts[3] else ip
            code = parts[4] if len(parts) > 4 else ""
            pos = parts[5] if len(parts) > 5 else ""

            if ip in seen_ips:
                warnings.append(f"stores.txt line {lineno}: duplicate IP {ip} (first on line {seen_ips[ip]}).")
            else:
                seen_ips[ip] = lineno

            stores.append({"ip": ip, "user": user, "pwd": pwd,
                           "dc": current_dc, "name": name, "code": code, "pos": pos})
    return stores, warnings

def read_stores_raw():
    """Raw text of stores.txt for the editor (the file is created first if missing)."""
    ensure_stores_file()
    try:
        with open(STORES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def write_stores_raw(content):
    """Overwrite stores.txt with the text from the editor."""
    with open(STORES_FILE, "w", encoding="utf-8") as f:
        f.write(content.rstrip("\n") + "\n")