"""Download official dataset archives into local raw-data folders."""

from __future__ import annotations

import email as email_parser
import html
import imaplib
import os
import re
import shutil
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any

from src.services.ingestion.kitti_playwright_auth import cookie_header_from_playwright_storage

NUSCENES_MINI_URL = "https://www.nuscenes.org/data/v1.0-mini.tgz"
KITTI_OFFICIAL_DOWNLOADS = {
    "data_object_image_2.zip": "https://www.cvlibs.net/download.php?file=data_object_image_2.zip",
    "data_object_velodyne.zip": "https://www.cvlibs.net/download.php?file=data_object_velodyne.zip",
    "data_object_label_2.zip": "https://www.cvlibs.net/download.php?file=data_object_label_2.zip",
    "data_object_calib.zip": "https://www.cvlibs.net/download.php?file=data_object_calib.zip",
}
ProgressCallback = Callable[[str], None]


class DatasetDownloadError(RuntimeError):
    """Raised when an official dataset cannot be downloaded or unpacked."""


@dataclass(frozen=True)
class KittiEmailInboxConfig:
    host: str
    username: str
    password: str
    mailbox: str = "INBOX"
    timeout_seconds: int = 300
    poll_interval_seconds: int = 10


@dataclass(frozen=True)
class DownloadedDataset:
    dataset_root: Path
    downloaded_files: list[Path]


def _ensure_inside(target_root: Path, candidate: Path) -> None:
    try:
        candidate.resolve().relative_to(target_root.resolve())
    except ValueError as error:
        raise DatasetDownloadError(f"Archive member escapes destination: {candidate}") from error


def _looks_like_html(path: Path) -> bool:
    preview = path.read_bytes()[:512].decode("utf-8", errors="ignore").lower()
    return "<html" in preview or "email" in preview or "download" in preview or "log in" in preview


def _write_html_diagnostic(archive_path: Path) -> Path | None:
    if not _looks_like_html(archive_path):
        return None
    diagnostics = archive_path.parent.parent / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    diagnostic_path = diagnostics / f"{archive_path.name}.html"
    diagnostic_path.write_bytes(archive_path.read_bytes())
    return diagnostic_path


def _invalid_kitti_zip_message(archive_path: Path) -> str:
    diagnostic_path = _write_html_diagnostic(archive_path)
    hint = (
        " The downloaded file looks like an HTML login/email page, not a dataset zip. "
        "This usually means CVLIBS did not expose a direct archive for the current session. "
        "Open the diagnostic HTML, complete any CVLIBS email/request step, then pass the emailed/direct archive URL "
        "through KITTI_IMAGE_2_URL/KITTI_VELODYNE_URL/KITTI_LABEL_2_URL/KITTI_CALIB_URL."
        + (f" Diagnostic saved to: {diagnostic_path}." if diagnostic_path else "")
        if diagnostic_path
        else ""
    )
    return f"Downloaded KITTI archive is not a valid zip file: {archive_path}.{hint}"


def _validate_zip_archive(archive_path: Path) -> None:
    if not zipfile.is_zipfile(archive_path):
        raise DatasetDownloadError(_invalid_kitti_zip_message(archive_path))


def _validate_tar_archive(archive_path: Path) -> None:
    try:
        with tarfile.open(archive_path) as archive:
            archive.getmembers()
    except (EOFError, OSError, tarfile.TarError) as error:
        raise DatasetDownloadError(
            f"Downloaded nuScenes archive is not a valid complete tar file: {archive_path}. "
            "The cached/downloaded file may be truncated; delete it or rerun so the downloader can refresh it."
        ) from error


def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
    _validate_zip_archive(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            _ensure_inside(destination, destination / member.filename)
        archive.extractall(destination)


def _safe_extract_tar(archive_path: Path, destination: Path) -> None:
    _validate_tar_archive(archive_path)
    try:
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                _ensure_inside(destination, destination / member.name)
                if member.issym() or member.islnk():
                    raise DatasetDownloadError(
                        f"Refusing to extract archive link outside the trusted dataset contract: {member.name}"
                    )
            archive.extractall(destination, filter="data")
    except (EOFError, OSError, tarfile.TarError) as error:
        raise DatasetDownloadError(f"Could not extract nuScenes archive: {archive_path}: {error}") from error


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


def _copy_or_download(
    url: str,
    destination: Path,
    headers: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        _emit(progress, f"Using cached archive: {destination} ({_format_bytes(destination.stat().st_size)})")
        return destination
    partial = destination.with_name(f".{destination.name}.part")
    partial.unlink(missing_ok=True)
    try:
        if url.startswith("file://"):
            source = Path(url.removeprefix("file://"))
            if not source.is_file():
                raise DatasetDownloadError(f"Local archive does not exist: {source}")
            total = source.stat().st_size
            copied = 0
            _emit(progress, f"Copying local archive: {source} -> {destination}")
            with source.open("rb") as source_file, partial.open("wb") as output:
                while chunk := source_file.read(1024 * 1024):
                    output.write(chunk)
                    copied += len(chunk)
                    _emit(progress, f"Copied {destination.name}: {_format_bytes(copied)} / {_format_bytes(total)}")
            shutil.copystat(source, partial)
        else:
            request = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
                content_type = response.headers.get("Content-Type", "unknown")
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                _emit(progress, f"Downloading {destination.name} from official source ({content_type})")
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = downloaded / total * 100
                        _emit(
                            progress,
                            f"Downloaded {destination.name}: {_format_bytes(downloaded)} / {_format_bytes(total)} ({percent:.1f}%)",
                        )
                    else:
                        _emit(progress, f"Downloaded {destination.name}: {_format_bytes(downloaded)}")
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise DatasetDownloadError(f"Could not download {url}: {error}") from error
    except KeyboardInterrupt:
        partial.unlink(missing_ok=True)
        _emit(progress, f"Cancelled download; removed partial archive: {partial}")
        raise
    partial.replace(destination)
    return destination


def _download_with_cache_repair(
    url: str,
    destination: Path,
    *,
    headers: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
    validate: Callable[[Path], None],
) -> Path:
    was_cached = destination.exists()
    archive = _copy_or_download(url, destination, headers=headers, progress=progress)
    try:
        validate(archive)
    except DatasetDownloadError:
        if not was_cached:
            raise
        _emit(progress, f"Cached archive is invalid; deleting and retrying: {archive}")
        archive.unlink(missing_ok=True)
        archive = _copy_or_download(url, destination, headers=headers, progress=progress)
        validate(archive)
    return archive


def _message_text(message: Message) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            if content_type not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True)
            if not isinstance(payload, (bytes, str)):
                continue
            charset = part.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="ignore") if isinstance(payload, bytes) else payload)
    else:
        payload = message.get_payload(decode=True)
        if isinstance(payload, (bytes, str)):
            charset = message.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="ignore") if isinstance(payload, bytes) else payload)
    return "\n".join(parts)


def _extract_kitti_download_url_from_text(text: str, archive_name: str) -> str | None:
    decoded: str = html.unescape(text)
    candidates: list[str] = re.findall(r"https?://[^\s<>'\"]+", decoded)
    for candidate in candidates:
        cleaned = candidate.rstrip('.),];"')
        if archive_name in cleaned and ("cvlibs.net" in cleaned or "amazonaws.com" in cleaned):
            return cleaned
    return None


def _extract_kitti_download_url_from_message(raw_message: bytes, archive_name: str) -> str | None:
    message = email_parser.message_from_bytes(raw_message)
    return _extract_kitti_download_url_from_text(_message_text(message), archive_name)


def _mailboxes_to_poll(client: imaplib.IMAP4, configured_mailbox: str) -> list[str]:
    """Include provider-declared all-mail and junk mailboxes when available."""
    mailboxes = [configured_mailbox]
    status, entries = client.list()
    if status != "OK":
        return mailboxes
    for entry in entries or []:
        line = entry.decode("utf-8", errors="replace") if isinstance(entry, bytes) else str(entry)
        if "\\All" not in line and "\\Junk" not in line:
            continue
        match = re.search(r'"([^"]+)"\s*$', line)
        if match and match.group(1) not in mailboxes:
            mailboxes.append(match.group(1))
    return mailboxes


def _poll_kitti_download_email(
    archive_name: str, config: KittiEmailInboxConfig, progress: ProgressCallback | None
) -> str:
    deadline = time.monotonic() + config.timeout_seconds
    _emit(progress, f"Polling inbox {config.username} for CVLIBS link: {archive_name}")
    while time.monotonic() < deadline:
        try:
            with imaplib.IMAP4_SSL(config.host) as client:
                client.login(config.username, config.password)
                for mailbox in _mailboxes_to_poll(client, config.mailbox):
                    client.select(mailbox)
                    status, payload = client.search(None, "ALL")
                    if status != "OK" or not payload or not payload[0]:
                        ids: list[bytes] = []
                    else:
                        ids = payload[0].split()[-25:]
                    for message_id in reversed(ids):
                        status, message_payload = client.fetch(message_id.decode("ascii"), "(RFC822)")
                        if status != "OK":
                            continue
                        for item in message_payload:
                            if not isinstance(item, tuple):
                                continue
                            raw_message: Any = item[1]
                            if not isinstance(raw_message, bytes):
                                continue
                            url = _extract_kitti_download_url_from_message(raw_message, archive_name)
                            if url:
                                _emit(progress, f"Found CVLIBS direct URL for {archive_name} in {mailbox}")
                                return url
        except imaplib.IMAP4.error as error:
            raise DatasetDownloadError(
                f"KITTI delivery mailbox rejected IMAP authentication for {config.username} at {config.host}: {error}. "
                "For Gmail, enable 2-Step Verification, create a 16-character App Password, and use that App Password here; "
                "do not use the normal Gmail password."
            ) from error
        except OSError as error:
            raise DatasetDownloadError(
                f"Cannot reach KITTI delivery mailbox at {config.host}: {error}. "
                "Check Internet/DNS access and whether the current network permits IMAP over TLS on port 993."
            ) from error
        _emit(progress, f"Waiting for CVLIBS email link for {archive_name}...")
        time.sleep(config.poll_interval_seconds)
    raise DatasetDownloadError(
        f"Timed out waiting for CVLIBS email link for {archive_name}. "
        "Check IMAP credentials, spam folder, or increase --kitti-email-timeout."
    )


def _request_kitti_download_email(
    url: str,
    archive_name: str,
    email: str,
    *,
    headers: dict[str, str] | None = None,
    download_root: Path,
    progress: ProgressCallback | None = None,
) -> Path:
    diagnostics = Path(download_root) / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    payload = urllib.parse.urlencode({"email": email, "submit": "Request Download Link"}).encode("utf-8")
    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=payload, headers=request_headers, method="POST")
    _emit(progress, f"Requesting CVLIBS emailed download link for {archive_name} -> {email}")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
    except OSError as error:
        raise DatasetDownloadError(f"Could not request KITTI download email for {archive_name}: {error}") from error
    diagnostic_path = diagnostics / f"{archive_name}.request.html"
    diagnostic_path.write_bytes(body)
    _emit(progress, f"Saved CVLIBS email-request response: {diagnostic_path}")
    return diagnostic_path


def _read_cookie_header(cookie_file: Path | None, cookie_json_file: Path | None = None) -> str | None:
    cookie_header = os.environ.get("KITTI_COOKIE_HEADER")
    if cookie_header:
        return cookie_header
    cookie_file = cookie_file or (
        Path(os.environ["KITTI_COOKIE_FILE"]) if os.environ.get("KITTI_COOKIE_FILE") else None
    )
    if cookie_file is not None:
        if not cookie_file.is_file():
            raise DatasetDownloadError(f"KITTI cookie file does not exist: {cookie_file}")
        return cookie_file.read_text(encoding="utf-8").strip()
    cookie_json_file = cookie_json_file or (
        Path(os.environ["KITTI_COOKIE_JSON"]) if os.environ.get("KITTI_COOKIE_JSON") else None
    )
    if cookie_json_file is None:
        return None
    return cookie_header_from_playwright_storage(cookie_json_file)


def download_official_nuscenes(
    download_root: Path,
    *,
    version: str = "v1.0-mini",
    url: str = NUSCENES_MINI_URL,
    progress: ProgressCallback | None = None,
) -> DownloadedDataset:
    """Download and unpack the official nuScenes mini split."""
    if version != "v1.0-mini":
        raise DatasetDownloadError("Only nuScenes v1.0-mini has a stable public official URL in this script.")
    dataset_root = Path(download_root) / "nuscenes"
    archive = _download_with_cache_repair(
        url,
        Path(download_root) / "archives" / Path(url).name,
        progress=progress,
        validate=_validate_tar_archive,
    )
    _emit(progress, f"[download 1/1] Extracting nuScenes archive: {archive.name}")
    _safe_extract_tar(archive, dataset_root)
    _emit(progress, f"[complete 1/1] nuScenes dataset ready: {dataset_root}")
    return DownloadedDataset(dataset_root=dataset_root, downloaded_files=[archive])


def download_official_kitti_object(
    download_root: Path,
    *,
    image_url: str | None = None,
    label_url: str | None = None,
    calib_url: str | None = None,
    velodyne_url: str | None = None,
    cookie_file: Path | None = None,
    cookie_json_file: Path | None = None,
    kitti_email: str | None = None,
    kitti_inbox: KittiEmailInboxConfig | None = None,
    progress: ProgressCallback | None = None,
) -> DownloadedDataset:
    """Download and unpack the official KITTI object detection training files.

    KITTI requires a logged-in CVLIBS account or emailed official archive links.
    The default URLs point at the official CVLIBS request endpoints; provide
    KITTI_COOKIE_HEADER, KITTI_COOKIE_FILE, or direct KITTI_*_URL archive links
    when CVLIBS does not return archives directly.
    """
    urls = {
        "data_object_image_2.zip": image_url
        or os.environ.get("KITTI_IMAGE_2_URL")
        or KITTI_OFFICIAL_DOWNLOADS["data_object_image_2.zip"],
        "data_object_velodyne.zip": velodyne_url
        or os.environ.get("KITTI_VELODYNE_URL")
        or KITTI_OFFICIAL_DOWNLOADS["data_object_velodyne.zip"],
        "data_object_label_2.zip": label_url
        or os.environ.get("KITTI_LABEL_2_URL")
        or KITTI_OFFICIAL_DOWNLOADS["data_object_label_2.zip"],
        "data_object_calib.zip": calib_url
        or os.environ.get("KITTI_CALIB_URL")
        or KITTI_OFFICIAL_DOWNLOADS["data_object_calib.zip"],
    }
    cookie_header = _read_cookie_header(cookie_file, cookie_json_file)
    kitti_email = kitti_email or os.environ.get("KITTI_EMAIL")
    if cookie_header:
        _emit(progress, "Loaded KITTI/CVLIBS cookies for official download session.")
    else:
        _emit(progress, "No KITTI/CVLIBS cookie session was provided; CVLIBS may return an HTML request page.")
    headers = {"Cookie": cookie_header} if cookie_header else None
    dataset_root = Path(download_root) / "kitti_object"
    downloaded: list[Path] = []
    for archive_index, (archive_name, url) in enumerate(urls.items(), start=1):
        _emit(progress, f"[download {archive_index}/{len(urls)}] Preparing KITTI archive: {archive_name}")
        archive_path = Path(download_root) / "archives" / archive_name
        try:
            archive = _download_with_cache_repair(
                url,
                archive_path,
                headers=headers,
                progress=progress,
                validate=_validate_zip_archive,
            )
        except DatasetDownloadError as error:
            if kitti_email and archive_path.is_file() and _looks_like_html(archive_path):
                diagnostic_path = _request_kitti_download_email(
                    url,
                    archive_name,
                    kitti_email,
                    headers=headers,
                    download_root=Path(download_root),
                    progress=progress,
                )
                if kitti_inbox is None:
                    raise DatasetDownloadError(
                        f"CVLIBS requires an emailed direct download link for {archive_name}. "
                        f"A request was submitted to {kitti_email}. To keep this fully automatic, rerun with "
                        "--kitti-imap-host, --kitti-imap-user, and --kitti-imap-password so the CLI can read the link. "
                        f"Response saved to: {diagnostic_path}"
                    ) from error
                direct_url = _poll_kitti_download_email(archive_name, kitti_inbox, progress)
                archive_path.unlink(missing_ok=True)
                archive = _download_with_cache_repair(
                    direct_url,
                    archive_path,
                    headers=headers,
                    progress=progress,
                    validate=_validate_zip_archive,
                )
            else:
                raise
        _emit(progress, f"[download {archive_index}/{len(urls)}] Extracting KITTI archive: {archive_name}")
        _safe_extract_zip(archive, dataset_root)
        downloaded.append(archive)
    _emit(progress, f"[complete {len(urls)}/{len(urls)}] KITTI dataset ready: {dataset_root}")
    return DownloadedDataset(dataset_root=dataset_root, downloaded_files=downloaded)
