# Bioinformatics runtime resources

The Git repository contains the pipeline code, exact direct dependency versions,
resource metadata, and deployment tools. It intentionally does **not** contain
reference databases, Conda environments, FASTQ files, patient data, generated
profiles, trained model artifacts, credentials, or application databases.

The current reference set is about 113 GiB before archive overhead. Store its
versioned archives on an authorised NAS, object store, encrypted disk, or release
medium. Do not place these archives in normal Git history.

## Online reconstruction

Create both bioinformatics environments from the repository:

```bash
export FMT_ROOT=/srv/wgs-fmt
bash deploy/install-bioinformatics-envs.sh
```

Reference databases must then be installed from their official/licensed sources
at the paths in `manifest.json`, or restored from an existing resource bundle.

## Offline migration

On the source server:

```bash
export FMT_ROOT=/storage/main/users/zhangrongpeng/data/fmt
bash deploy/package-bioinformatics-runtime.sh /path/to/resource-bundles/wgs-fmt-shotgun-v1
```

Transfer the resulting component archives and `SHA256SUMS` outside Git. On the
target server:

```bash
export FMT_ROOT=/srv/wgs-fmt
bash deploy/restore-bioinformatics-runtime.sh /path/to/resource-bundles/wgs-fmt-shotgun-v1
```

The packaging command uses `conda-pack` for relocatable environments and Zstandard
archives for reference databases. The restore command verifies every archive,
rejects unsafe member paths, runs `conda-unpack` at the new prefix, restores the
databases beneath `FMT_ROOT`, and runs the runtime checker.

The source server therefore needs `conda-pack`, `zstd`, and `sha256sum`; the target
server needs `zstd` and `sha256sum`.

The bundle also contains the small FMT triplet model and its donor-matching input
tables because online ranking depends on them. The matching tables are marked as
restricted derived research data: review de-identification and authorisation before
moving the bundle, encrypt it in transit and at rest, and never publish it as a Git
object or a public release asset.
