"""`igni-service-bundle`: the bundle builder as a command."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from igni_service.bundle.builder import BundleBuilder, BundleReport
from igni_service.bundle.platforms import PLATFORMS
from igni_service.errors import BundleError


class BundleCommand:
    """`igni-service-bundle`: the builder as a command."""

    @staticmethod
    def parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="igni-service-bundle",
            description="Build the extension bundle a service ships to igni.",
        )
        parser.add_argument(
            "--extension", type=Path, default=Path("extension"), help="the extension's directory"
        )
        parser.add_argument("--out", type=Path, default=Path("extension-bundle.tar.gz"))
        parser.add_argument(
            "--allow-sdist",
            action="append",
            default=[],
            metavar="NAME",
            help="a dependency that publishes no wheel and may be built from its sdist",
        )
        parser.add_argument("--find-links", action="append", type=Path, default=[], metavar="DIR")
        parser.add_argument("--no-index", action="store_true")
        parser.add_argument(
            "--no-build-isolation",
            action="store_true",
            help="build with this interpreter's packages instead of fetching build backends",
        )
        parser.add_argument(
            "--platform",
            action="append",
            default=[],
            choices=[platform.asset.value for platform in PLATFORMS],
            help=(
                "build wheels for this platform only (repeatable). Every platform by "
                "default; fewer makes a smaller bundle that machines on the others cannot "
                "install, for a deployment whose machines are all on these"
            ),
        )
        return parser

    @classmethod
    def main(cls, argv: Sequence[str] | None = None) -> int:
        args = cls.parser().parse_args(argv)
        try:
            report = BundleBuilder(
                args.extension,
                allow_sdist=args.allow_sdist,
                find_links=args.find_links,
                no_index=args.no_index,
                build_isolation=not args.no_build_isolation,
                platforms=[
                    p for p in PLATFORMS if not args.platform or p.asset.value in args.platform
                ],
            ).build(args.out)
        except BundleError as exc:
            print(f"extension bundle: {exc}", file=sys.stderr)
            return 1
        cls._say(report)
        return 0

    @staticmethod
    def _say(report: BundleReport) -> None:
        for line in report.notes:
            print(f"extension bundle: {line}")
        print(
            f"extension bundle: wrote {report.out} — {report.extension_id} {report.version}, "
            f"{len(report.wheels)} wheels, {report.size} bytes, sha256 {report.sha256}"
        )
        for asset in report.assets:
            print(
                f"extension bundle: asset {asset.name} ({asset.platform}) {asset.file}, "
                f"{asset.size} bytes, sha256 {asset.sha256} in {report.assets_dir}"
            )


def main(argv: Sequence[str] | None = None) -> int:
    """The console script's entry point."""
    return BundleCommand.main(argv)


if __name__ == "__main__":
    sys.exit(main())
