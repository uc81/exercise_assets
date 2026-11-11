import json
import tempfile
import unittest
from pathlib import Path

from package_exercise_assets import validate_catalog_media


class CatalogMediaValidationTest(unittest.TestCase):
    def write_catalog(self, root: Path, name: str, records: list[dict]) -> None:
        (root / name).write_text(json.dumps(records), encoding="utf-8")

    def prepare_catalogs(self, root: Path) -> None:
        self.write_catalog(
            root,
            "exercises.json",
            [{"name": "Nested exercise", "images": ["Nested/0.jpg"]}],
        )
        self.write_catalog(
            root,
            "hasaneyldrm_exercises.json",
            [{"name": "Provider exercise", "image": "images/provider.jpg", "gif_url": "videos/provider.gif"}],
        )
        self.write_catalog(
            root,
            "pilates_reformer_exercises.json",
            [{"name": "Pilates exercise", "images": ["Pilates.png"]}],
        )

    def create_media(self, root: Path) -> None:
        for relative in (
            "images/Nested/0.jpg",
            "videos/Nested/0.gif",
            "images/provider.jpg",
            "videos/provider.gif",
            "pilates/Pilates.png",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"asset")

    def test_validates_nested_free_media_and_all_other_catalogue_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_catalogs(root)
            self.create_media(root)

            validate_catalog_media(root)

    def test_rejects_missing_animated_media_even_when_catalogue_images_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_catalogs(root)
            self.create_media(root)
            (root / "videos/Nested/0.gif").unlink()

            with self.assertRaisesRegex(RuntimeError, "Nested exercise.*animated GIF"):
                validate_catalog_media(root)

    def test_rejects_path_traversal_in_catalogue_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_catalogs(root)
            self.create_media(root)
            free_catalog = json.loads((root / "exercises.json").read_text(encoding="utf-8"))
            free_catalog[0]["images"] = ["../outside.jpg"]
            (root / "exercises.json").write_text(
                json.dumps(free_catalog), encoding="utf-8"
            )

            with self.assertRaisesRegex(RuntimeError, "unsafe media path"):
                validate_catalog_media(root)


if __name__ == "__main__":
    unittest.main()
