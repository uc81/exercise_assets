# Exercise Assets

Versioned exercise catalog and media assets for the HealthOS/anumi Android application.

## Source layout

The complete source asset set lives under `exercises/`:

- `exercises/images/`
- `exercises/pilates/`
- `exercises/videos/`
- `exercises/exercises.json`
- `exercises/hasaneyldrm_exercises.json`
- `exercises/hasaneyldrm_exercises.schema.json`
- `exercises/pilates_reformer_exercises.json`

## Release packaging

Run the `Package and publish exercise assets` GitHub Actions workflow and provide a positive integer version, such as `1`.

The workflow generates and publishes an immutable release tagged `exercise-assets-vN` containing:

- `exercise-assets-vN.zip`
- `exercise-assets-vN.zip.sha256`

The ZIP contains one top-level `exercises/` directory and preserves the source relative paths exactly.

Existing release versions are never replaced. When the asset set changes, publish a new version.

The Android app downloads the version-specific checksum and ZIP, verifies the SHA-256, extracts to private application storage, validates the required structure, atomically activates the extracted pack, and deletes the downloaded ZIP.
