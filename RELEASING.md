# Releasing

Releases are built by GitHub Actions from an annotated tag on the exact `main`
commit. Do not build or upload package assets by hand. Do not tag until you
intend to publish. A `READY` result from this tool is not a reason to release,
and a release is not an approval of any client file.

The first published version is intended to be `0.1.1`. The protected `v0.1.0`
tag failed its release-notes-header gate before any GitHub Release, asset or
PyPI project was created. Never move or reuse that tag. Before the first
successful workflow, no PyPI project exists.
The first successful workflow creates the PyPI project.

## One-time setup before the first tag

1. Create the GitHub Actions environment `pypi` on
   `ryanduguid/review-ready-gate` (Settings → Environments). Set its URL to
   `https://pypi.org/p/review-ready-gate`.
2. Register a PyPI trusted publisher (Account → Publishing → "Add a new
   pending publisher" while the project does not exist) with exactly these
   values:

| Field | Value |
| --- | --- |
| PyPI project name | `review-ready-gate` |
| Owner | `ryanduguid` |
| Repository name | `review-ready-gate` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

Until both exist, the `pypi` job fails closed after the GitHub Release is
published. Once the publisher exists, backfill with `workflow_dispatch` on
`release.yml` and the existing tag. Do not retag.

## Before tagging

1. Merge the release pull request and require every `main` check to pass.
2. Enable release immutability in the repository settings.
3. From an operator session authenticated with repository Administration read
   access, run:

    ```bash
    gh api -H "X-GitHub-Api-Version: 2026-03-10" \
      repos/ryanduguid/review-ready-gate/immutable-releases --jq .enabled
    ```

    Do not push the tag unless the output is exactly `true`. The Actions
    `GITHUB_TOKEN` cannot be granted repository Administration read access, so
    the tag workflow cannot perform this preflight itself.
4. Confirm the versions in `pyproject.toml` and `uv.lock` match the
   `RELEASE_NOTES.md` heading.
5. Create an annotated tag on current remote `main`, for example
   `git tag -a v0.1.1 -m "v0.1.1"` (or `-s` when signing is configured), then
   push only that tag.

The workflow runs the locked tests, builds the wheel and source distribution
once, generates an SPDX 2.3 SBOM for the wheel and `SHA256SUMS`, records GitHub
provenance and an SBOM attestation, then publishes the completed draft. An
existing release is never overwritten.

Verify the downloaded release with:

```bash
gh release download v0.1.1 -R ryanduguid/review-ready-gate --dir release-v0.1.1
cd release-v0.1.1
sha256sum --check SHA256SUMS
gh attestation verify review_ready_gate-0.1.1-py3-none-any.whl \
  -R ryanduguid/review-ready-gate
gh attestation verify review_ready_gate-0.1.1-py3-none-any.whl \
  -R ryanduguid/review-ready-gate \
  --predicate-type https://spdx.dev/Document/v2.3
gh release view v0.1.1 -R ryanduguid/review-ready-gate --json isImmutable
gh release verify v0.1.1 -R ryanduguid/review-ready-gate
gh release verify-asset v0.1.1 review_ready_gate-0.1.1-py3-none-any.whl \
  -R ryanduguid/review-ready-gate
```

If any gate fails, inspect it before touching the tag or draft. Never move a
published tag. Cut a new version rather than rewriting history.
