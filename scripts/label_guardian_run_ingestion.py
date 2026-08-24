#!/usr/bin/env python3
"""Run Label Guardian ingestion into Supabase PostgreSQL and Google Cloud Storage."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import IngestionSettings  # noqa: E402
from src.services.ingestion.dataset_catalog import catalog_package, select_catalog_packages  # noqa: E402
from src.services.ingestion.dataset_selector import (  # noqa: E402
    DatasetLayoutError,
    DatasetType,
    scenario_for_dataset,
    scenario_profile,
    select_dataset_layout,
)
from src.services.ingestion.ingestion_service import (  # noqa: E402
    IngestionService,
    create_object_storage_client,
    create_session_factory,
)
from src.services.ingestion.interactive_menu import (  # noqa: E402
    adapter_menu_options,
    choose_from_menu,
    source_menu_options,
    topic_menu_options,
)
from src.services.ingestion.kitti_adapter import KittiAdapter  # noqa: E402
from src.services.ingestion.kitti_imap_secret_cache import (  # noqa: E402
    KittiImapSecretCacheError,
    load_kitti_imap_credentials,
    load_kitti_imap_password,
    save_kitti_imap_password,
)
from src.services.ingestion.kitti_playwright_auth import (  # noqa: E402
    KittiBrowserAuthError,
    cvlibs_cookie_pairs_from_playwright_storage,
    save_kitti_browser_session,
)
from src.services.ingestion.local_storage import LocalObjectStorageClient  # noqa: E402
from src.services.ingestion.nuscenes_adapter import NuScenesAdapter, NuScenesDatasetLayoutError  # noqa: E402
from src.services.ingestion.official_dataset_downloader import (  # noqa: E402
    DatasetDownloadError,
    KittiEmailInboxConfig,
    download_official_kitti_object,
    download_official_nuscenes,
)
from src.services.ingestion.yolo_exporter import YoloExportError, export_normalized_to_yolo  # noqa: E402


def _resolve_dataset_root(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[Path, list[Path]]:
    if not arguments.download_official:
        return arguments.dataset_root, []
    try:
        if arguments.selector == "kitti":
            try:
                if arguments.kitti_login_with_browser or not arguments.kitti_cookie_json.is_file():
                    _collect_kitti_login_credentials(arguments, parser)
                    print("[auth] Opening KITTI/CVLIBS browser login to save a reusable session")
                    save_kitti_browser_session(
                        arguments.kitti_cookie_json,
                        headless=False,
                        email=arguments.kitti_login_email,
                        password=arguments.kitti_login_password,
                    )
                else:
                    cookie_count = len(cvlibs_cookie_pairs_from_playwright_storage(arguments.kitti_cookie_json))
                    print(
                        f"[auth] Reusing saved KITTI/CVLIBS session: {arguments.kitti_cookie_json} ({cookie_count} cookie(s))"
                    )
            except KittiBrowserAuthError as error:
                parser.error(str(error))
            kitti_inbox = None
            _collect_kitti_delivery_credentials(arguments, parser)
            if arguments.kitti_imap_host and arguments.kitti_imap_user and arguments.kitti_imap_password:
                kitti_inbox = KittiEmailInboxConfig(
                    host=arguments.kitti_imap_host,
                    username=arguments.kitti_imap_user,
                    password=arguments.kitti_imap_password,
                    mailbox=arguments.kitti_imap_mailbox,
                    timeout_seconds=arguments.kitti_email_timeout,
                    poll_interval_seconds=arguments.kitti_email_poll_interval,
                )
            downloaded = download_official_kitti_object(
                arguments.download_root,
                image_url=arguments.kitti_image_url,
                label_url=arguments.kitti_label_url,
                calib_url=arguments.kitti_calib_url,
                velodyne_url=arguments.kitti_velodyne_url,
                cookie_file=arguments.kitti_cookie_file,
                cookie_json_file=arguments.kitti_cookie_json,
                kitti_email=arguments.kitti_email,
                kitti_inbox=kitti_inbox,
                progress=lambda message: print(f"[download] {message}"),
            )
        else:
            downloaded = download_official_nuscenes(
                arguments.download_root,
                version=arguments.nuscenes_version,
                url=arguments.nuscenes_url,
                progress=lambda message: print(f"[download] {message}"),
            )
    except DatasetDownloadError as error:
        parser.error(str(error))
    print(f"Official dataset root: {downloaded.dataset_root.resolve()}")
    return downloaded.dataset_root, downloaded.downloaded_files


def _can_prompt_for_credentials() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _collect_kitti_login_credentials(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Collect CVLIBS credentials only when a new browser session is required."""
    if arguments.kitti_login_email and arguments.kitti_login_password:
        return
    if not _can_prompt_for_credentials():
        parser.error(
            "KITTI browser login needs --kitti-login-email and --kitti-login-password when stdin is not a TTY."
        )
    arguments.kitti_login_email = arguments.kitti_login_email or input("KITTI/CVLIBS email: ").strip()
    arguments.kitti_login_password = arguments.kitti_login_password or getpass.getpass("KITTI/CVLIBS password: ")
    if not arguments.kitti_login_email or not arguments.kitti_login_password:
        parser.error("KITTI/CVLIBS email and password are required to create a browser session.")
    arguments.kitti_email = arguments.kitti_email or arguments.kitti_login_email


def _default_imap_host(email: str | None) -> str | None:
    domain = (email or "").rsplit("@", 1)[-1].lower()
    return {
        "gmail.com": "imap.gmail.com",
        "googlemail.com": "imap.gmail.com",
        "outlook.com": "outlook.office365.com",
        "hotmail.com": "outlook.office365.com",
        "live.com": "outlook.office365.com",
        "yahoo.com": "imap.mail.yahoo.com",
    }.get(domain)


def _collect_kitti_delivery_credentials(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Set up mailbox polling required by CVLIBS emailed signed-link flow."""
    if arguments.cache_kitti_imap_password and not any(
        (arguments.kitti_email, arguments.kitti_imap_host, arguments.kitti_imap_user, arguments.kitti_imap_password)
    ):
        try:
            cached_credentials = load_kitti_imap_credentials(arguments.kitti_imap_password_cache)
        except KittiImapSecretCacheError as error:
            parser.error(str(error))
        if cached_credentials:
            (
                arguments.kitti_email,
                arguments.kitti_imap_host,
                arguments.kitti_imap_user,
                arguments.kitti_imap_password,
            ) = cached_credentials
            print(f"[auth] Reusing cached KITTI delivery-mail profile: {arguments.kitti_imap_password_cache}")
            return
    if arguments.kitti_imap_host and arguments.kitti_imap_user and arguments.kitti_imap_password:
        arguments.kitti_email = arguments.kitti_email or arguments.kitti_imap_user
        return
    if not _can_prompt_for_credentials():
        return
    email = arguments.kitti_email or arguments.kitti_login_email
    arguments.kitti_email = email or input("KITTI download delivery email: ").strip()
    if not arguments.kitti_email:
        parser.error("A delivery email is required for KITTI official download links.")
    default_host = _default_imap_host(arguments.kitti_email)
    host_hint = f" [{default_host}]" if default_host else ""
    entered_host = input(f"IMAP host{host_hint} (press Enter to use default): ").strip()
    if "@" in entered_host:
        if default_host:
            print(f"[auth] An email address is not an IMAP host; using {default_host}.")
            entered_host = default_host
        else:
            parser.error("IMAP host must be a server name such as imap.example.com, not an email address.")
    arguments.kitti_imap_host = entered_host or default_host
    entered_username = input(f"IMAP username [{arguments.kitti_email}] (press Enter to use delivery email): ").strip()
    if default_host == "imap.gmail.com" and entered_username and "@" not in entered_username:
        print("[auth] Gmail IMAP uses the full email address; using the delivery email.")
        entered_username = arguments.kitti_email
    arguments.kitti_imap_user = entered_username or arguments.kitti_email
    if arguments.cache_kitti_imap_password:
        try:
            cached_password = load_kitti_imap_password(
                arguments.kitti_imap_password_cache,
                email=arguments.kitti_email,
                host=arguments.kitti_imap_host,
                username=arguments.kitti_imap_user,
            )
        except KittiImapSecretCacheError as error:
            parser.error(str(error))
        if cached_password:
            arguments.kitti_imap_password = cached_password
            print(f"[auth] Reusing cached KITTI delivery credential: {arguments.kitti_imap_password_cache}")
            return
    arguments.kitti_imap_password = getpass.getpass("IMAP app password (used only for this run): ").strip()
    if default_host == "imap.gmail.com":
        arguments.kitti_imap_password = arguments.kitti_imap_password.replace(" ", "")
    if not arguments.kitti_imap_host or not arguments.kitti_imap_user or not arguments.kitti_imap_password:
        parser.error("IMAP host, username, and app password are required for fully automatic KITTI download.")
    if arguments.cache_kitti_imap_password:
        try:
            save_kitti_imap_password(
                arguments.kitti_imap_password_cache,
                email=arguments.kitti_email,
                host=arguments.kitti_imap_host,
                username=arguments.kitti_imap_user,
                password=arguments.kitti_imap_password,
            )
        except KittiImapSecretCacheError as error:
            parser.error(str(error))
        print(f"[auth] Cached KITTI delivery credential: {arguments.kitti_imap_password_cache}")


def _resolve_selector(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if arguments.interactive_selector:
        try:
            arguments.source = choose_from_menu(source_menu_options(), title="Select data source").value
            selected_adapter = choose_from_menu(adapter_menu_options(), title="Select implemented data adapter")
            package = catalog_package(selected_adapter.value)
            arguments.selector = package.dataset_type.value
            arguments.dataset_type = package.dataset_type.value
            arguments.nuscenes_version = package.version or arguments.nuscenes_version
            arguments.scenario = scenario_for_dataset(package.dataset_type).value
            arguments.dataset_count = None
            arguments.city = "any"
            arguments.time_of_day = "any"
            if package.dataset_type == DatasetType.NUSCENES:
                arguments.topic = choose_from_menu(
                    topic_menu_options(package.topics), title="Select nuScenes data topic"
                ).value
            else:
                arguments.topic = "2d"
        except (KeyboardInterrupt, RuntimeError) as error:
            parser.error(str(error) or "interactive selector was cancelled")
    else:
        if arguments.scenario is not None:
            profile = scenario_profile(arguments.scenario)
            requested_selector = arguments.selector or arguments.dataset_type
            if requested_selector is None:
                arguments.selector = profile.dataset_type.value
            elif requested_selector != profile.dataset_type.value:
                parser.error(
                    f"scenario={arguments.scenario} maps to dataset={profile.dataset_type}; "
                    f"received selector={requested_selector}"
                )
            else:
                arguments.selector = requested_selector
        else:
            arguments.selector = arguments.selector or arguments.dataset_type or DatasetType.KITTI.value
            arguments.scenario = scenario_for_dataset(arguments.selector).value
    profile = scenario_profile(arguments.scenario)
    if arguments.city == "any":
        arguments.city = "karlsruhe_urban" if arguments.selector == DatasetType.KITTI else "multi_region"
    if arguments.time_of_day == "any" and arguments.selector == DatasetType.KITTI:
        arguments.time_of_day = "day"
    if arguments.download_official:
        arguments.source = "official"
    if arguments.source == "official":
        arguments.download_official = True
    print(
        "Ingestion request: "
        f"source={arguments.source}, scenario={arguments.scenario}, dataset={arguments.selector}, "
        f"topic={arguments.topic}, city={arguments.city}, time={arguments.time_of_day}, "
        f"tags={','.join(profile.tags)}"
    )
    print(f"Context: {profile.risk_note}")


def _select_dataset(arguments: argparse.Namespace, dataset_root: Path, parser: argparse.ArgumentParser):
    try:
        selected = select_dataset_layout(
            arguments.selector,
            dataset_root,
            nuscenes_version=arguments.nuscenes_version,
            strict=arguments.strict_layout,
            scenario=arguments.scenario,
        )
    except (DatasetLayoutError, ValueError) as error:
        parser.error(str(error))
    print(f"Selected dataset: {selected.dataset_type} - {selected.description}")
    return selected


def _default_storage_prefix(arguments: argparse.Namespace) -> str:
    city = arguments.city.replace("_", " ").capitalize()
    prefix = f"{arguments.selector}/{arguments.topic.upper()}/{city}/{arguments.time_of_day}"
    return f"{prefix}/{arguments.split}" if arguments.split else prefix


def _split_bucket_uri(raw_bucket: str) -> tuple[str, str]:
    parsed = urlparse(raw_bucket)
    if parsed.scheme == "gs":
        return parsed.netloc, parsed.path.strip("/")
    if parsed.scheme:
        raise ValueError("Only gs:// bucket URIs are supported for cloud ingestion.")
    return raw_bucket, ""


def _combined_storage_prefix(bucket_prefix: str, requested_prefix: str) -> str:
    parts = [part.strip("/") for part in (bucket_prefix, requested_prefix) if part.strip("/")]
    return "/".join(parts)


def _storage_settings(arguments: argparse.Namespace) -> tuple[IngestionSettings, object, str]:
    bucket, bucket_prefix = _split_bucket_uri(arguments.bucket)
    storage_prefix = _combined_storage_prefix(
        bucket_prefix,
        arguments.storage_prefix or _default_storage_prefix(arguments),
    )
    base_settings = IngestionSettings()
    settings_update = {
        "database_url": arguments.database_url or base_settings.database_url,
        "object_key_prefix": storage_prefix,
        "dataset_provider": arguments.selector,
        "dataset_name": arguments.selector,
        "dataset_release": arguments.nuscenes_version if arguments.selector == DatasetType.NUSCENES else "object",
    }
    if arguments.storage_backend == "local":
        settings = base_settings.model_copy(
            update={
                **settings_update,
                "storage_backend": "gcs",
                "gcs_bucket": bucket,
                "gcs_public_url": f"file://{arguments.object_root.resolve() / bucket}",
            }
        )
        return settings, LocalObjectStorageClient(arguments.object_root), storage_prefix
    if arguments.storage_backend == "gcs":
        settings = base_settings.model_copy(
            update={
                **settings_update,
                "storage_backend": "gcs",
                "gcs_bucket": bucket,
                "gcs_project": arguments.gcp_project or base_settings.gcs_project,
                "gcs_credentials_path": arguments.gcp_credentials or base_settings.gcs_credentials_path,
                "gcs_public_url": arguments.gcs_public_url or base_settings.gcs_public_url,
            }
        )
        return settings, create_object_storage_client(settings), storage_prefix
    raise ValueError(f"Unsupported storage backend: {arguments.storage_backend}")


def _upload_downloaded_archives(
    storage_client: object,
    settings: IngestionSettings,
    downloaded_files: list[Path],
) -> int:
    uploads = 0
    key_prefix = settings.object_key_prefix.strip("/")
    for archive_path in downloaded_files:
        object_key = f"{key_prefix}/raw/{archive_path.name}" if key_prefix else f"raw/{archive_path.name}"
        storage_client.upload_file(
            str(archive_path),
            settings.bucket_name,
            object_key,
            ExtraArgs={"ContentType": "application/octet-stream"},
        )
        uploads += 1
    return uploads


def _limit_normalized_output(images: list, cases: list, max_images: int | None) -> tuple[list, list]:
    if max_images is None:
        return images, cases
    selected_images = images[:max_images]
    selected_ids = {image.source_image_id for image in selected_images}
    return selected_images, [qa_case for qa_case in cases if qa_case.source_image_id in selected_ids]


def _run_ingestion(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    dataset_root, downloaded_files = _resolve_dataset_root(arguments, parser)
    print("[ingest] Validating selected dataset layout")
    selected = _select_dataset(arguments, dataset_root, parser)
    try:
        settings, storage_client, storage_prefix = _storage_settings(arguments)
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    service = IngestionService(
        selected.dataset_root,
        create_session_factory(settings.database_url),
        storage_client,
        settings,
        dataset_split=arguments.split,
    )
    service.ensure_bucket()
    if downloaded_files and arguments.upload_source_archives:
        archive_uploads = _upload_downloaded_archives(storage_client, settings, downloaded_files)
        print(f"[ingest] Uploaded {archive_uploads} official source archive(s) to object storage")
    elif downloaded_files:
        print("[ingest] Skipped official source archive upload; pass --upload-source-archives to copy raw archives")
    try:
        if selected.dataset_type == DatasetType.KITTI:
            images, cases = KittiAdapter(selected.dataset_root, split=arguments.split).load()
        else:
            images, cases = NuScenesAdapter(
                selected.dataset_root,
                selected.version or arguments.nuscenes_version,
                max_images=arguments.max_images,
            ).load()
    except NuScenesDatasetLayoutError as error:
        parser.error(str(error))
    if selected.dataset_type != DatasetType.NUSCENES:
        images, cases = _limit_normalized_output(images, cases, arguments.max_images)
    if arguments.max_images is not None:
        print(f"[ingest] Limited smoke run to {len(images)} image(s) and {len(cases)} object(s)")
    if arguments.export_yolo_root:
        try:
            label_map = (
                json.loads(arguments.yolo_label_map.read_text(encoding="utf-8")) if arguments.yolo_label_map else None
            )
            if (
                label_map is not None
                and not isinstance(label_map, dict)
                or (
                    isinstance(label_map, dict)
                    and not all(isinstance(key, str) and isinstance(value, str) for key, value in label_map.items())
                )
            ):
                raise YoloExportError("YOLO label-map JSON must be an object of source-label to COCO-label strings.")
            export_result = export_normalized_to_yolo(
                source_root=selected.dataset_root,
                images=images,
                objects=cases,
                output_root=arguments.export_yolo_root,
                split=arguments.yolo_split,
                label_map=label_map,
            )
        except (OSError, json.JSONDecodeError, YoloExportError) as error:
            parser.error(str(error))
        print(
            f"[yolo-export] Wrote {export_result.images} images and {export_result.annotations} annotations "
            f"to {export_result.output_root}; skipped {export_result.skipped_annotations}."
        )
        print(f"[yolo-export] Manifest: {export_result.manifest_path}")
    print("[ingest] Uploading frames and persisting normalized records")
    result = service.ingest_normalized(images, cases)
    print("[ingest] Completed upload and database persistence")
    print(f"Ingested {result.images} images and {result.objects} objects; copied {result.uploads} files.")
    print(f"PostgreSQL: {make_url(settings.database_url).render_as_string(hide_password=True)}")
    if arguments.storage_backend == "local":
        print(f"Objects: {arguments.object_root.resolve() / settings.bucket_name / storage_prefix}")
    else:
        print(f"Objects: gs://{settings.bucket_name}/{storage_prefix}")


def _run_all_official(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    plan = (
        ("challenging_hard", "official nuScenes challenging/hard dataset"),
        ("baseline_easy", "official KITTI baseline/easy dataset"),
    )
    print("[batch] Running official ingestion plan: nuScenes + KITTI")
    for scenario, label in plan:
        print(f"[batch] Starting {label}")
        run_arguments = argparse.Namespace(**vars(arguments))
        run_arguments.interactive_selector = False
        run_arguments.source = "official"
        run_arguments.download_official = True
        run_arguments.scenario = scenario
        run_arguments.selector = None
        run_arguments.dataset_type = None
        run_arguments.city = "any"
        run_arguments.time_of_day = "any"
        _resolve_selector(run_arguments, parser)
        _run_ingestion(run_arguments, parser)
        print(f"[batch] Finished {label}")


def _run_catalog_packages(arguments: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        packages = select_catalog_packages(dataset_count=arguments.dataset_count, topic=arguments.topic)
    except ValueError as error:
        parser.error(str(error))
    print(f"[catalog] Selected {len(packages)} complete package(s): {', '.join(item.package_id for item in packages)}")
    for package in packages:
        run_arguments = argparse.Namespace(**vars(arguments))
        run_arguments.dataset_count = None
        run_arguments.selector = package.dataset_type.value
        run_arguments.dataset_type = package.dataset_type.value
        run_arguments.scenario = scenario_for_dataset(package.dataset_type).value
        run_arguments.nuscenes_version = package.version or arguments.nuscenes_version
        run_arguments.source = "official"
        run_arguments.download_official = True
        run_arguments.city = "any"
        run_arguments.time_of_day = "any"
        run_arguments.storage_prefix = arguments.storage_prefix or ""
        _resolve_selector(run_arguments, parser)
        _run_ingestion(run_arguments, parser)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a Label Guardian dataset to object storage and PostgreSQL.",
        epilog=(
            "Examples:\n"
            "  python scripts/label_guardian_run_ingestion.py --interactive-selector\n"
            "  python scripts/label_guardian_run_ingestion.py --all-official --topic 3d --kitti-email your@email --kitti-imap-host imap.example.com --kitti-imap-user your@email\n"
            "  python scripts/label_guardian_run_ingestion.py --source official --scenario challenging_hard --topic 3d\n"
            "  python scripts/label_guardian_run_ingestion.py --source official --scenario baseline_easy --topic 3d\n"
            "  python scripts/label_guardian_run_ingestion.py --source official --scenario baseline_easy --topic 3d "
            "--kitti-login-with-browser  # refresh saved browser session\n"
            "  python scripts/label_guardian_run_ingestion.py --source official --selector nuscenes "
            "--bucket gs://my-gcp-bucket/datasets --database-url 'postgresql+psycopg://...supabase...?sslmode=require'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dataset-root", type=Path, default=Path("eval/label_guardian_ingestion_mini"))
    parser.add_argument("--split", help="Optional dataset split such as train or val; omitted means all splits")
    parser.add_argument("--selector", choices=("kitti", "nuscenes"))
    parser.add_argument("--interactive-selector", action="store_true")
    parser.add_argument("--all-official", action="store_true")
    parser.add_argument("--dataset-count", type=int)
    parser.add_argument("--max-images", type=int, help="Limit normalized images for smoke ingestion runs")
    parser.add_argument("--storage-prefix")
    parser.add_argument("--scenario", choices=("baseline_easy", "challenging_hard"))
    parser.add_argument("--source", choices=("local", "official"), default="local")
    parser.add_argument("--topic", choices=("2d", "3d"), default="2d")
    parser.add_argument("--city", default="any")
    parser.add_argument("--time-of-day", choices=("any", "day", "night"), default="any")
    parser.add_argument("--dataset-type", choices=("kitti", "nuscenes"), default=None, help=argparse.SUPPRESS)
    parser.add_argument("--nuscenes-version", default="v1.0-mini")
    parser.add_argument("--strict-layout", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--download-official", action="store_true")
    parser.add_argument("--download-root", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--upload-source-archives",
        action="store_true",
        help="Upload official raw archives to object storage; disabled by default for smoke runs.",
    )
    parser.add_argument("--nuscenes-url", default="https://www.nuscenes.org/data/v1.0-mini.tgz")
    parser.add_argument("--kitti-image-url")
    parser.add_argument("--kitti-label-url")
    parser.add_argument("--kitti-calib-url")
    parser.add_argument("--kitti-velodyne-url")
    parser.add_argument("--kitti-cookie-file", type=Path)
    parser.add_argument("--kitti-cookie-json", type=Path, default=Path("data/secrets/kitti_cookies.json"))
    parser.add_argument("--kitti-login-with-browser", action="store_true")
    parser.add_argument("--kitti-login-email")
    parser.add_argument("--kitti-login-password")
    parser.add_argument("--kitti-email")
    parser.add_argument("--kitti-imap-host")
    parser.add_argument("--kitti-imap-user")
    parser.add_argument("--kitti-imap-password")
    parser.add_argument("--cache-kitti-imap-password", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--kitti-imap-password-cache", type=Path, default=Path("data/secrets/kitti_imap_credentials.json")
    )
    parser.add_argument("--kitti-imap-mailbox", default="INBOX")
    parser.add_argument("--kitti-email-timeout", type=int, default=300)
    parser.add_argument("--kitti-email-poll-interval", type=int, default=10)
    parser.add_argument("--object-root", type=Path, default=Path("data/e2e/objects"))
    parser.add_argument("--bucket", default="gs://label-guardian-e2e")
    parser.add_argument("--storage-backend", choices=("local", "gcs"), default="gcs")
    parser.add_argument("--database-url", help="Sync SQLAlchemy URL for ingestion, e.g. Supabase psycopg URL")
    parser.add_argument("--gcp-project")
    parser.add_argument("--gcp-credentials", type=Path)
    parser.add_argument("--gcs-public-url")
    parser.add_argument(
        "--export-yolo-root", type=Path, help="Optional derived YOLO output directory, outside --dataset-root"
    )
    parser.add_argument("--yolo-split", default="val", help="Output YOLO split name (default: val)")
    parser.add_argument(
        "--yolo-label-map", type=Path, help="Optional JSON mapping from source label to COCO traffic label"
    )
    arguments = parser.parse_args()
    if arguments.all_official:
        _run_all_official(arguments, parser)
        return
    if arguments.dataset_count is not None and not arguments.interactive_selector:
        _run_catalog_packages(arguments, parser)
        return
    _resolve_selector(arguments, parser)
    if arguments.dataset_count is not None:
        _run_catalog_packages(arguments, parser)
        return
    _run_ingestion(arguments, parser)


if __name__ == "__main__":
    main()
