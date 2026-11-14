"""The npm SDKs, as a consumer outside a bundler sees them.

The packages ship their TypeScript source, which a bundler compiles. A
consumer that does not — a Node program, a test runner, a tool that
reads the types — got nothing: ``exports`` pointed at ``src/index.ts``,
and under ``moduleResolution: node16`` the extensionless imports inside
it could not be resolved, so ``connect`` was not exported and the
consumer's own type-check failed with ``TS2305``.

This builds the packages, packs them the way npm publishes them, and
installs the tarballs into a scratch consumer that resolves the way a
Node program does: ``module`` and ``moduleResolution`` are ``node16``.
The consumer then type-checks, and runs. A package that cannot be
resolved from outside a bundler fails here, before it is published.

    uv run python scripts/check_npm_consumers.py

The consumer lives inside this repository, because it needs React: the
packages' peers are the repository's own dependencies, and a scratch
directory outside it would have none.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The npm packages with TypeScript in them. The stylesheet
#: (``clients/ui``) is CSS and has nothing to compile.
PACKAGES = ("packages/extension-bridge", "packages/ui-react")

#: The stylesheet, packed and installed too: a page imports it for its effect,
#: and TypeScript 6 and later fail a side-effect import that resolves to no types.
STYLESHEET = "clients/ui"

#: Where the scratch consumer is built. Inside the repository: see the
#: module's docstring.
SCRATCH = ROOT / ".tmp" / "npm-consumer"

#: The consumer's own program. It uses the packages the way an
#: extension's page does — the bridge, the wire format, the tokens,
#: the components — and it names the types it expects, so a type that
#: changed shape fails here rather than in somebody's editor.
CONSUMER = """\
import { connect, HostError, type Bridge } from "@ignite-ember/extension-bridge";
import { BRIDGE_VERSION, type HostMessage } from "@ignite-ember/extension-bridge/protocol";
import { applyThemeTokens, type ThemeTokens } from "@ignite-ember/extension-bridge/tokens";
import { AppShell, Button, type ButtonProps } from "@ignite-ember/ui-react";
import "@ignite-ember/ui-css";

export async function main(): Promise<void> {
  const bridge: Bridge = await connect({ timeoutMs: 1000 });
  const version: number = BRIDGE_VERSION;
  const message: HostMessage | null = null;
  const tokens: ThemeTokens = { "igni-radius": "4px" };
  const props: ButtonProps = { variant: "primary" };

  // The names are used, so a type that changed shape fails the check.
  console.log(bridge, version, message, tokens, props, AppShell, Button, HostError);
}
"""

#: The consumer's compiler options. ``node16`` is the point of the
#: exercise: it is how a Node program resolves, and it is the
#: resolution that failed.
TSCONFIG = {
    "compilerOptions": {
        "target": "ES2022",
        "lib": ["ES2022", "DOM", "DOM.Iterable"],
        "module": "NodeNext",
        "moduleResolution": "NodeNext",
        "jsx": "react-jsx",
        "strict": True,
        "noEmit": True,
        "skipLibCheck": True,
        "noUncheckedSideEffectImports": True,
        "types": [],
    },
    "include": ["consumer.ts"],
}


class ConsumerError(Exception):
    """A consumer outside a bundler cannot use a package."""


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a command in a directory."""
    try:
        return subprocess.run(  # noqa: S603 — our own commands, on our own files
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise ConsumerError(f"cannot run {command[0]}: {error}") from None


def manifest_of(package: str, *keys: str) -> dict:
    """The package's ``package.json``, which must have ``keys``."""
    manifest = json.loads((ROOT / package / "package.json").read_text(encoding="utf-8"))
    missing = [key for key in keys if key not in manifest]
    if missing:
        raise ConsumerError(f"{package}'s package.json has no {missing}")
    return manifest


def targets(value: object) -> set[str]:
    """Every file path an ``exports`` value names, however deep its conditions nest."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(targets(inner) for inner in value.values()))
    return set()


def build() -> None:
    """Compile the packages' ``dist/``: the JS Node runs, the types it reads."""
    for package in PACKAGES:
        done = run(
            [
                str(ROOT / "node_modules" / ".bin" / "tsc"),
                "-p",
                f"{package}/tsconfig.build.json",
            ],
            cwd=ROOT,
        )
        if done.returncode != 0:
            raise ConsumerError(f"{package} does not build:\n{done.stdout}{done.stderr}")


def pack(destination: Path, packages: tuple[str, ...] = PACKAGES) -> dict[str, Path]:
    """Pack each package the way npm publishes it, and name the tarballs."""
    tarballs: dict[str, Path] = {}
    for package in packages:
        done = run(
            ["npm", "pack", "--silent", "--pack-destination", str(destination)],
            cwd=ROOT / package,
        )
        if done.returncode != 0:
            raise ConsumerError(f"{package} does not pack:\n{done.stdout}{done.stderr}")
        lines = done.stdout.strip().splitlines()
        if not lines:
            raise ConsumerError(f"{package} packed, and npm named no tarball")
        name = lines[-1]
        tarballs[package] = destination / name
    return tarballs


def install(tarballs: dict[str, Path], into: Path) -> None:
    """Unpack the tarballs into the consumer's ``node_modules``.

    This is what ``npm install <tarball>`` does with them: the package's
    own manifest, its files, and nothing else.
    """
    for package, tarball in tarballs.items():
        manifest = manifest_of(package, "name")
        target = into / "node_modules" / manifest["name"]
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball) as archive:
            for member in archive.getmembers():
                if not member.name.startswith("package/"):
                    continue
                member.name = member.name[len("package/") :]
                if not member.name:
                    continue
                archive.extract(member, target, filter="data")  # noqa: S202 — our own tarball


def tarball_contents(tarball: Path) -> set[str]:
    """The paths a tarball carries, without the ``package/`` prefix."""
    with tarfile.open(tarball) as archive:
        return {
            name[len("package/") :] for name in archive.getnames() if name.startswith("package/")
        }


def check_the_build_is_in_the_tarball(package: str, tarball: Path) -> None:
    """The tarball carries the build, and the manifest points at it.

    A manifest that names a file the tarball does not carry is not a
    broken publish: npm accepts it, and the package fails when somebody
    installs it. This is where that is caught.
    """
    names = tarball_contents(tarball)
    manifest = manifest_of(package, "main", "types", "exports")
    wanted = {manifest["main"], manifest["types"], *targets(manifest["exports"])}
    missing = sorted(name for name in wanted if name.lstrip("./") not in names)
    if missing:
        raise ConsumerError(f"{package}'s tarball does not carry {missing}")
    if not any(name.startswith("dist/") for name in names):
        raise ConsumerError(f"{package}'s tarball carries no build")


def typecheck(consumer: Path) -> None:
    """The consumer's own type-check, with Node's resolution.

    The types it reads must come from the build, not from the source
    beside it: a consumer that fell back to the source would be reading
    TypeScript it cannot run, and the check would pass for the wrong
    reason.
    """
    done = run(
        [
            str(ROOT / "node_modules" / ".bin" / "tsc"),
            "--noEmit",
            "-p",
            str(consumer),
            "--traceResolution",
        ],
        cwd=consumer,
    )
    if done.returncode != 0:
        raise ConsumerError(
            f"a consumer cannot type-check against the packages:\n{done.stdout}{done.stderr}"
        )
    resolved = [line for line in done.stdout.splitlines() if "was successfully resolved to" in line]
    for package in ("extension-bridge", "ui-react"):
        found = [line for line in resolved if f"'@ignite-ember/{package}'" in line]
        if not found:
            raise ConsumerError(f"a consumer did not resolve @ignite-ember/{package}")
        if not all("/dist/" in line for line in found):
            raise ConsumerError(
                f"a consumer reads @ignite-ember/{package} from the source, not from the build"
            )


def run_it(consumer: Path) -> None:
    """The packages, imported by Node: the build is what runs."""
    program = consumer / "runtime.mjs"
    program.write_text(
        "const bridge = await import('@ignite-ember/extension-bridge');\n"
        "const protocol = await import('@ignite-ember/extension-bridge/protocol');\n"
        "const tokens = await import('@ignite-ember/extension-bridge/tokens');\n"
        "const ui = await import('@ignite-ember/ui-react');\n"
        "const missing = ['connect', 'HostError'].filter((n) => !(n in bridge));\n"
        "if (missing.length) throw new Error('the bridge does not export ' + missing.join(', '));\n"
        "if (typeof protocol.BRIDGE_VERSION !== 'number') throw new Error('no wire version');\n"
        "if (typeof tokens.applyThemeTokens !== 'function') throw new Error('no tokens');\n"
        "if (typeof ui.Button !== 'function') throw new Error('no components');\n"
        "console.log('the packages import and run');\n",
        encoding="utf-8",
    )
    done = run(["node", str(program)], cwd=consumer)
    if done.returncode != 0:
        raise ConsumerError(f"a consumer cannot run the packages:\n{done.stdout}{done.stderr}")


def check() -> None:
    """Build, pack, install, type-check and run — the whole way round."""
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    tarballs_dir = SCRATCH / "tarballs"
    tarballs_dir.mkdir(parents=True)
    build()
    tarballs = pack(tarballs_dir)
    for package, tarball in tarballs.items():
        check_the_build_is_in_the_tarball(package, tarball)
    tarballs.update(pack(tarballs_dir, (STYLESHEET,)))
    consumer = SCRATCH / "consumer"
    consumer.mkdir(parents=True)
    (consumer / "package.json").write_text(
        json.dumps({"name": "npm-consumer", "private": True, "type": "module"}, indent=2),
        encoding="utf-8",
    )
    (consumer / "tsconfig.json").write_text(json.dumps(TSCONFIG, indent=2), encoding="utf-8")
    (consumer / "consumer.ts").write_text(CONSUMER, encoding="utf-8")
    install(tarballs, consumer)
    typecheck(consumer)
    run_it(consumer)


def main() -> int:
    """Check the packages, and say what failed."""
    try:
        check()
    except ConsumerError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print("the npm packages resolve, type-check and run outside a bundler")
    return 0


if __name__ == "__main__":
    sys.exit(main())
