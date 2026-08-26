#!/usr/bin/env python3

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path


REQUIRED_CATALOGS = (
    "exercises.json",
    "hasaneyldrm_exercises.json",
    "pilates_reformer_exercises.json",
)

REQUIRED_MEDIA_DIRECTORIES = (
    "images",
    "videos",
    "pilates",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the complete deterministic exercise asset archive from "
            "the repository's exercises/ directory."
        )
    )
    parser.add_argument(
        "--version",
        type=int,
        required=True,
        help="Positive exercise asset pack version.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("build/exercise-assets"),
        help="Directory for the ZIP and .sha256 files.",
    )
    return parser.parse_args()


def validate_source(source: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f"Exercise asset source directory does not exist: {source}")

    missing_catalogs = [
        name for name in REQUIRED_CATALOGS if not (source / name).is_file()
    ]
    if missing_catalogs:
        raise RuntimeError(
            "Missing required exercise catalogs: " + ", ".join(missing_catalogs)
        )

    invalid_media_directories = []
    for name in REQUIRED_MEDIA_DIRECTORIES:
        directory = source / name
        if not directory.is_dir() or not any(
            path.is_file() for path in directory.rglob("*")
        ):
            invalid_media_directories.append(name)

    if invalid_media_directories:
        raise RuntimeError(
            "Missing or empty required media directories: "
            + ", ".join(invalid_media_directories)
        )


def write_deterministic_file(
    archive: zipfile.ZipFile,
    source_file: Path,
    archive_name: str,
) -> None:
    info = zipfile.ZipInfo(
        filename=archive_name,
        date_time=(1980, 1, 1, 0, 0, 0),
    )
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3

    with source_file.open("rb") as source_stream:
        with archive.open(info, "w", force_zip64=True) as archive_stream:
            shutil.copyfileobj(
                source_stream,
                archive_stream,
                length=1024 * 1024,
            )


def create_archive(source: Path, destination: Path) -> tuple[int, int]:
    files = sorted(
        (path for path in source.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source).as_posix(),
    )

    if not files:
        raise RuntimeError("Exercise asset source directory contains no files.")

    total_source_bytes = sum(path.stat().st_size for path in files)

    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=True,
    ) as archive:
        for source_file in files:
            relative = source_file.relative_to(source).as_posix()
            write_deterministic_file(
                archive,
                source_file,
                f"exercises/{relative}",
            )

    with zipfile.ZipFile(destination, mode="r") as archive:
        archived_files = sorted(
            name for name in archive.namelist() if not name.endswith("/")
        )

    expected_files = sorted(
        f"exercises/{path.relative_to(source).as_posix()}"
        for path in files
    )

    if archived_files != expected_files:
        raise RuntimeError(
            "Generated exercise asset archive does not exactly match the source file set."
        )

    return len(files), total_source_bytes


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()

    if args.version <= 0:
        raise RuntimeError("--version must be greater than zero.")

    repository_root = Path(__file__).resolve().parents[1]
    source = repository_root / "exercises"
    output_dir = (
        args.output_dir
        if args.output_dir.is_absolute()
        else repository_root / args.output_dir
    )

    validate_source(source)
    output_dir.mkdir(parents=True, exist_ok=True)

    archive_name = f"exercise-assets-v{args.version}.zip"
    archive_path = output_dir / archive_name
    checksum_path = output_dir / f"{archive_name}.sha256"

    archive_path.unlink(missing_ok=True)
    checksum_path.unlink(missing_ok=True)

    file_count, total_source_bytes = create_archive(
        source=source,
        destination=archive_path,
    )

    checksum = sha256(archive_path)
    checksum_path.write_text(
        f"{checksum}  {archive_name}\n",
        encoding="utf-8",
    )

    release_tag = f"exercise-assets-v{args.version}"
    release_base_url = (
        "https://github.com/uc81/exercise_assets/releases/download/"
        f"{release_tag}"
    )

    print(f"Archive: {archive_path}")
    print(f"SHA-256: {checksum}")
    print(f"Files: {file_count}")
    print(f"Source bytes: {total_source_bytes}")
    print(f"Archive bytes: {archive_path.stat().st_size}")
    print(f"Release tag: {release_tag}")
    print(f"Archive URL: {release_base_url}/{archive_name}")
    print(f"Checksum URL: {release_base_url}/{archive_name}.sha256")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
