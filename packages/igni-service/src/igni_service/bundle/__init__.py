"""Building the extension bundle a service ships to igni.

    igni-service-bundle --extension extension/ --out extension-bundle.tar.gz

A gzipped tar with `manifest.json` at its root (declaring the `python`
packaging), the extension's own files — `README.md`, `plugin/`, `ui/`
when present — and a wheelhouse: the extension's wheel and every
dependency's, for CPython 3.12 on each platform igni runs on, so a
machine with no network can install it. Beside the archive, in
`extension-bundle.assets/`, every asset the manifest declares.

One module per concern:

- `platforms` — the platforms a wheelhouse is filled for.
- `manifest` — the extension's `manifest.json`, as a model.
- `project` — the parts of its `pyproject.toml` the builder reads.
- `sources` — where uv and pip find packages, and how they build.
- `requirements` — requirement names and hashed requirement lines.
- `runner` — running uv and pip.
- `resolver` — resolving the dependencies for one platform.
- `downloads` — downloading wheels, and building one from an sdist.
- `wheelhouse` — the extension's wheel and every dependency's.
- `code_tools` — the tools the extension's code registers.
- `permissions_tools` — `permissions.tools` written from, or held to, the code.
- `archive` — the deterministic archive, and reading its manifest back.
- `builder` — one extension directory into a bundle.
- `command` — `igni-service-bundle`.
"""
