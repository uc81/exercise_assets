#!/usr/bin/env python3

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath


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


def load_catalog(source: Path, filename: str) -> list[dict]:
    catalog_path = source / filename
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read exercise catalog {filename}: {exc}") from exc
    if not isinstance(catalog, list) or any(not isinstance(item, dict) for item in catalog):
        raise RuntimeError(f"Exercise catalog {filename} must contain a JSON array of objects.")
    return catalog


def referenced_file(
    source: Path,
    media_directory: str,
    reference: object,
    context: str,
    issues: list[str],
) -> Path | None:
    if not isinstance(reference, str) or not reference.strip():
        issues.append(f"{context}: media path is missing.")
        return None

    normalized = reference.strip().replace("\\", "/")
    segments = normalized.split("/")
    if (
        normalized.startswith("/")
        or segments[0].endswith(":")
        or any(segment in ("", ".", "..") for segment in segments)
    ):
        issues.append(f"{context}: unsafe media path {reference!r}.")
        return None

    relative = PurePosixPath(*segments)
    source_root = source.resolve()
    candidate = (source / media_directory / Path(*relative.parts)).resolve()
    if candidate != source_root and source_root not in candidate.parents:
        issues.append(f"{context}: media path escapes the exercise asset root.")
        return None
    if not candidate.is_file():
        archive_path = (PurePosixPath(media_directory) / relative).as_posix()
        issues.append(f"{context}: missing exercises/{archive_path}.")
        return None
    return candidate


def validate_catalog_media(source: Path) -> None:
    issues: list[str] = []

    free_exercises = load_catalog(source, "exercises.json")
    for index, exercise in enumerate(free_exercises):
        name = exercise.get("name", f"record {index}")
        context = f"exercises.json[{index}] {name!r}"
        images = exercise.get("images")
        image_reference = images[0] if isinstance(images, list) and images else None
        referenced_file(
            source, "images", image_reference, f"{context}.images[0]", issues
        )
        if isinstance(image_reference, str) and image_reference.strip():
            image_path = PurePosixPath(image_reference.replace("\\", "/"))
            gif_reference = image_path.with_suffix(".gif").as_posix()
            referenced_file(
                source, "videos", gif_reference, f"{context}.animated GIF", issues
            )

    hasaneyldrm_exercises = load_catalog(source, "hasaneyldrm_exercises.json")
    for index, exercise in enumerate(hasaneyldrm_exercises):
        name = exercise.get("name", f"record {index}")
        context = f"hasaneyldrm_exercises.json[{index}] {name!r}"
        referenced_file(
            source, "", exercise.get("image"), f"{context}.image", issues
        )
        referenced_file(
            source, "", exercise.get("gif_url"), f"{context}.gif_url", issues
        )

    pilates_exercises = load_catalog(source, "pilates_reformer_exercises.json")
    for index, exercise in enumerate(pilates_exercises):
        name = exercise.get("name", f"record {index}")
        context = f"pilates_reformer_exercises.json[{index}] {name!r}"
        images = exercise.get("images")
        image_reference = images[0] if isinstance(images, list) and images else None
        # AssetExerciseProvider resolves Pilates images by their filename.
        filename = (
            PurePosixPath(image_reference.replace("\\", "/")).name
            if isinstance(image_reference, str) and image_reference.strip()
            else image_reference
        )
        referenced_file(
            source, "pilates", filename, f"{context}.images[0]", issues
        )

    if issues:
        preview = "\\n".join(f"  - {issue}" for issue in issues[:10])
        remaining = len(issues) - 10
        suffix = f"\\n  - ... and {remaining} more." if remaining > 0 else ""
        raise RuntimeError(
            f"Exercise catalogs contain {len(issues)} missing or invalid media references:\\n"
            f"{preview}{suffix}"
        )


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

    validate_catalog_media(source)


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
