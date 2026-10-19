"""SSH/SFTP engine: uploads files to many store PCs in parallel.
Workers only push 3-tuples (kind, payload, tag) onto a queue; the UI polls it."""
import concurrent.futures
import os
import threading
import time

import paramiko

from config import (
    CONNECT_TIMEOUT_SEC, KNOWN_HOSTS_FILE, PROGRESS_UPDATE_SEC,
    UPLOAD_MAX_ATTEMPTS, UPLOAD_RETRY_DELAY_SEC,
)

ICON = {"ok": "✓", "failed": "✗", "cancelled": "–"}
LABEL = {"ok": "OK", "failed": "Failed", "cancelled": "Stopped"}

_hosts_lock = threading.Lock()


# ---------------------------------------------------------------- helpers
def fmt_size(nbytes):
    if nbytes >= 1024 * 1024:
        return f"{nbytes / 1048576:.1f} MB"
    if nbytes >= 1024:
        return f"{nbytes / 1024:.0f} KB"
    return f"{nbytes} B"


def store_label(store):
    """'3138 ATP SAN CARLOS - SERVER (172.26.187.81)'"""
    ip = store["ip"]
    name = store.get("name", "")
    head = " ".join(p for p in (store.get("code", ""), name if name != ip else "") if p)
    pos = store.get("pos", "")
    if pos:
        head = f"{head} - {pos}" if head else pos
    return f"{head} ({ip})" if head else ip


# ------------------------------------------------------------- connection
def _remember_host_key(ssh, ip):
    """Trust on first use: save a PC's key the first time; a later change is rejected."""
    try:
        key = ssh.get_transport().get_remote_server_key()
        with _hosts_lock:
            hk = paramiko.HostKeys()
            if os.path.exists(KNOWN_HOSTS_FILE):
                hk.load(KNOWN_HOSTS_FILE)
            if hk.lookup(ip) is None:
                hk.add(ip, key.get_name(), key)
                hk.save(KNOWN_HOSTS_FILE)
    except Exception:
        pass


def _open_ssh(store):
    ssh = paramiko.SSHClient()
    with _hosts_lock:
        if os.path.exists(KNOWN_HOSTS_FILE):
            try:
                ssh.load_host_keys(KNOWN_HOSTS_FILE)
            except Exception:
                pass
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(store["ip"], username=store["user"], password=store["pwd"],
                    timeout=CONNECT_TIMEOUT_SEC, look_for_keys=False, allow_agent=False)
        _remember_host_key(ssh, store["ip"])
    except Exception:
        ssh.close()
        raise
    return ssh


def _explain_connect_error(exc):
    if isinstance(exc, paramiko.AuthenticationException):
        return "Wrong username or password"
    if isinstance(exc, paramiko.BadHostKeyException):
        return ("This PC's identity changed since the last connection "
                "(if it was reinstalled, delete its line from known_hosts.txt)")
    text = str(exc).lower()
    if "timed out" in text:
        return "This PC didn't answer — it may be turned off or not on the network"
    if "refused" in text or "10061" in text:
        return "This PC is on, but its remote-access (SSH) service isn't running or is blocked"
    if any(k in text for k in ("unreachable", "no route", "10051", "10065", "11001", "getaddrinfo")):
        return "This PC can't be reached — check the IP address and the network"
    return "Could not connect to this PC"


# ------------------------------------------------------------------- SFTP
def _remote_size(sftp, path):
    try:
        return sftp.stat(path).st_size
    except OSError:
        return None


def ensure_remote_dir(sftp, remote_dir):
    """Create remote_dir (and missing parents). Raises IOError if it still isn't there."""
    parts = [p for p in remote_dir.replace("\\", "/").split("/") if p]
    current = ""
    for i, part in enumerate(parts):
        current = part if i == 0 else current + "/" + part
        try:
            sftp.stat(current)
        except OSError:
            try:
                sftp.mkdir(current)
            except OSError:
                pass
    if current:
        try:
            sftp.stat(current)
        except OSError as e:
            raise IOError(f"Could not create or open the folder {remote_dir}: {e}")


def _ensure_sftp_alive(conn, detail):
    try:
        conn["sftp"].stat(".")
        return
    except Exception:
        pass
    try:
        try:
            conn["sftp"].close()
        except Exception:
            pass
        conn["sftp"] = conn["ssh"].open_sftp()
        detail("SFTP session reopened after a failed attempt.")
    except Exception as e:
        detail(f"Could not reopen the SFTP session: {e}")


def _explain_upload_error(err, name):
    text = str(err).lower()
    if "permission denied" in text:
        return f"Permission denied while copying {name}"
    if "no space" in text:
        return "The PC's disk is full"
    return f"Couldn't copy {name} (it may be in use by a running program)"


def _explain_transfer_error(err):
    text = str(err)
    if "Could not create or open the folder" in text:
        return "Couldn't create or open the remote folder (check the path and permissions)"
    return "The transfer broke off (connection problem?)"


def _progress_cb(q, label):
    last = [0.0]

    def cb(sent, total):
        now = time.monotonic()
        if sent < total and now - last[0] < PROGRESS_UPDATE_SEC:
            return
        last[0] = now
        pct = int(sent * 100 / total) if total else 100
        q.put(("status", f"{label}: {fmt_size(sent)} / {fmt_size(total)} ({pct}%)", None))
    return cb


def _upload_one(conn, entry, remote_dir, replace, force, on_progress, detail):
    """Returns (status, reason). status: uploaded | unchanged | skipped | failed."""
    name = entry["name"]
    remote_path = f"{remote_dir}/{name}"
    remote_size = _remote_size(conn["sftp"], remote_path)
    exists = remote_size is not None

    if exists and not replace:
        detail(f"Skipped {name} — already on the PC and 'Replace' is off.")
        return "skipped", ""

    try:
        local_size = os.path.getsize(entry["path"])
    except OSError:
        return "failed", f"Can't read {name} on this computer"

    if exists and not force and remote_size == local_size:
        detail(f"Skipped {name} — already up to date ({fmt_size(local_size)}, same size).")
        return "unchanged", ""

    started = time.monotonic()
    last_err = None
    for attempt in range(1, UPLOAD_MAX_ATTEMPTS + 1):
        try:
            conn["sftp"].put(entry["path"], remote_path, callback=on_progress)
            detail(f"Uploaded {name} ({fmt_size(local_size)} in {time.monotonic() - started:.1f}s)")
            return "uploaded", ""
        except Exception as e:
            last_err = e
            detail(f"Upload attempt {attempt} for {name} failed: {e}")
            if attempt < UPLOAD_MAX_ATTEMPTS:
                time.sleep(UPLOAD_RETRY_DELAY_SEC)
                _ensure_sftp_alive(conn, detail)
    return "failed", _explain_upload_error(last_err, name)


# ------------------------------------------------------------ one store PC
def _outcome_text(counts):
    parts = []
    if counts["uploaded"]:
        parts.append(f"{counts['uploaded']} uploaded")
    if counts["unchanged"]:
        parts.append(f"{counts['unchanged']} already up to date")
    if counts["skipped"]:
        parts.append(f"{counts['skipped']} skipped")
    return ", ".join(parts) or "Nothing to do"


def _deploy_one(store, files, remote_dir, replace, force, q, cancel):
    t0 = time.monotonic()
    ip = store["ip"]
    label = store_label(store)

    def detail(text):
        q.put(("detail", f"[{ip}] {text}", None))

    def finish(status, reason, outcome=None, show=True):
        secs = time.monotonic() - t0
        q.put(("result", {"store": label, "ip": ip, "code": store.get("code", ""),
                          "pos": store.get("pos", ""), "status": status,
                          "reason": reason, "seconds": secs}, None))
        if show:
            q.put(("log", f"{ICON[status]} {label} · {secs:.1f}s · {outcome or reason}", status))
        q.put(("progress", 1, None))

    if cancel.is_set():
        finish("cancelled", "Cancelled before it started", show=False)
        return

    q.put(("status", f"Connecting to {ip}...", None))
    try:
        ssh = _open_ssh(store)
    except Exception as e:
        detail(f"Connection error: {e!r}")
        finish("failed", _explain_connect_error(e))
        return

    conn = {"ssh": ssh, "sftp": None}
    counts = {"uploaded": 0, "unchanged": 0, "skipped": 0}
    problems = []
    cancelled = False
    try:
        conn["sftp"] = ssh.open_sftp()
        ensure_remote_dir(conn["sftp"], remote_dir)
        detail(f"Target folder ready: {remote_dir}")
        for i, entry in enumerate(files, 1):
            if cancel.is_set():
                cancelled = True
                break
            step = f"Uploading {entry['name']} to {ip} ({i}/{len(files)})"
            q.put(("status", step + "...", None))
            status, reason = _upload_one(conn, entry, remote_dir, replace, force,
                                         _progress_cb(q, step), detail)
            if status == "failed":
                problems.append(reason)
            else:
                counts[status] += 1
    except Exception as e:
        detail(f"Transfer error: {e!r}")
        problems.append(_explain_transfer_error(e))
    finally:
        try:
            if conn["sftp"] is not None:
                conn["sftp"].close()
        except Exception:
            pass
        ssh.close()

    if problems:
        extra = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
        finish("failed", problems[0] + extra)
    elif cancelled:
        finish("cancelled", "Cancelled before all files were sent")
    else:
        finish("ok", "Completed", outcome=_outcome_text(counts))


def start_deployment(stores, files, remote_dir, replace, force, workers, q):
    """Run the whole batch on a background thread. Returns a threading.Event;
    set() it to cancel (running PCs finish their current file, the rest are skipped)."""
    cancel = threading.Event()
    remote_dir = remote_dir.replace("\\", "/").rstrip("/")
    workers = max(1, int(workers))

    def work(store):
        try:
            _deploy_one(store, files, remote_dir, replace, force, q, cancel)
        except Exception as e:  # safety net: one PC can never hang the batch
            reason = "Unexpected error in the deployer"
            q.put(("log", f"✗ {store_label(store)} · {reason}: {e}", "failed"))
            q.put(("result", {"store": store_label(store), "ip": store["ip"],
                              "code": store.get("code", ""), "pos": store.get("pos", ""),
                              "status": "failed", "reason": reason, "seconds": 0.0}, None))
            q.put(("progress", 1, None))

    def run_all():
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, stores))
        q.put(("done", None, None))

    threading.Thread(target=run_all, daemon=True).start()
    return cancel