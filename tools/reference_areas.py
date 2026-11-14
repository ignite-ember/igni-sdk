"""Which page of the reference each name of the hand-written packages is on.

igni-service's and igni-extension's pages take Python modules (or
``module:Name`` constants); the npm packages' pages take TypeScript files,
relative to the package's ``src``. A public name no page takes fails the
generator (``tools/package_reference.py``).
"""

from __future__ import annotations

from collections.abc import Mapping

from tools.reference_area import Area

#: Each package's reference pages, and the modules (or ``module:Name``
#: constants) on each. A public name no page takes fails the generator.
PYTHON_AREAS: Mapping[str, list[Area]] = {
    "igni-service": [
        Area(
            "igni-service-class",
            "IgniService and its settings",
            ("igni_service.service", "igni_service.settings", "igni_service.tables"),
        ),
        Area(
            "callers",
            "Callers: Person, App, Space",
            ("igni_service.tokens", "igni_service:Caller", "igni_service:PEOPLE_ONLY"),
        ),
        Area(
            "web-sign-in",
            "Web sign-in, sessions and CORS",
            ("igni_service.web", "igni_service.web_sessions", "igni_service.cors"),
        ),
        Area(
            "host-and-directory",
            "Host and directory",
            ("igni_service.host", "igni_service.directory"),
        ),
        Area("notifications", "Notifications", ("igni_service.notifications",)),
        Area(
            "producers-and-agents",
            "Producers, agents and events",
            ("igni_service.events", "igni_service.agents", "igni_service.agent_wire"),
        ),
        Area("subjects", "Erasure and export: Subject", ("igni_service.subjects",)),
        Area(
            "vm-profiles",
            "VM profiles and IgniApp",
            ("igni_service.vm_profiles", "igni_service.app"),
        ),
        Area("key-storage", "Key storage", ("igni_service.keystore", "igni_service.sql_keystore")),
        Area("errors", "Errors", ("igni_service.errors",)),
        Area(
            "testing",
            "igni_service.testing",
            (
                "igni_service.testing",
                "igni_service.testing_notifications",
                "igni_service.testing_items",
                "igni_service.testing_item_records",
                "igni_service.testing_vm_rules",
                "igni_service.testing_vm_profiles",
                "igni_service.testing_bundles",
                "igni_service.testing_wire",
                "igni_service.testing_seams",
                "igni_service.testing_directory",
                "igni_service.testing_claims",
                "igni_service.testing_sessions",
                "igni_service.testing_settings",
                "igni_service.bundle",
                "igni_service.urls",
            ),
        ),
    ],
    "igni-extension": [
        Area("igni-extension-class", "IgniExtension", ("igni_extension.extension",)),
        Area("tools", "Tools: hints and names", ("igni_extension.hints", "igni_extension.tools")),
        Area(
            "callers-and-service",
            "Callers and the backend service",
            ("igni_extension.caller", "igni_extension.service", "igni_extension.tokens"),
        ),
        Area(
            "host",
            "The host",
            (
                "igni_extension.host_model",
                "igni_extension.members",
                "igni_extension.notifications",
                "igni_extension:SCHEMA_VERSION",
            ),
        ),
        Area("hooks", "Hooks", ("igni_extension.hooks",)),
        Area(
            "service-events-and-prompts",
            "Service events and prompt conditions",
            ("igni_extension.service_events", "igni_extension.prompt"),
        ),
        Area("environment", "Environment", ("igni_extension.environment",)),
        Area("errors", "Errors", ("igni_extension.errors",)),
        Area(
            "testing",
            "igni_extension.testing",
            ("igni_extension.testing", "igni_extension.testing:Minter"),
        ),
    ],
}


#: The npm packages' entry points: the files whose exports are the
#: package's published surface — the main one, and any subpath it publishes.
NPM_ENTRIES: Mapping[str, tuple[str, ...]] = {
    "extension-bridge": ("index.ts", "protocol.ts", "tokens.ts"),
    "ui-react": ("index.ts",),
}

#: The npm packages' reference pages: an area each, and the TypeScript
#: files the names come from. A public name no area takes is an error.
NPM_AREAS: Mapping[str, list[Area]] = {
    "extension-bridge": [
        Area(
            "the-bridge",
            "The bridge",
            ("bridge.ts",),
            "`connect()` is the whole entry point: it waits for igni's "
            "hello, applies the theme and hands the page its bridge.",
        ),
        Area(
            "what-a-page-is-handed",
            "What a page is handed",
            ("contract.ts",),
            "The `Bridge` interface `connect()` resolves to: the launch "
            "params, the settings, the host, the service, and the methods "
            "that act on them.",
        ),
        Area(
            "the-host-object-model",
            "The host object model",
            ("hostModel.ts", "hostModel.generated.ts"),
            "How igni appears to a page: the objects, their properties and "
            "their signals. The generated half comes from igni's own host "
            "schema, and `SCHEMA_VERSION` says which version of it. A field "
            "the schema does not describe is listed without a description: "
            "the SDK has none to give, and would rather say nothing than "
            "write what it does not know.",
        ),
        Area(
            "the-extensions-service",
            "The extension's service",
            ("service.ts",),
            "Reaching the extension's own backend service, as the person signed in to igni.",
        ),
        Area(
            "the-wire",
            "The wire",
            ("protocol.ts",),
            "The messages the host and the page exchange. The host imports "
            "this too, so there is one description of the wire.",
        ),
        Area(
            "the-design-tokens",
            "The design tokens",
            ("tokens.ts",),
            "The tokens under the compatibility floor: the ones an "
            "extension may rely on, and the ones that may be read live.",
        ),
    ],
    "ui-react": [
        Area(
            "the-primitives",
            "The primitives",
            ("primitives.tsx",),
            "Thin typed wrappers over the classes igni's own app uses: "
            "buttons, fields, rows, items, chips, dialogs.",
        ),
        Area(
            "the-shell",
            "The shell",
            ("Shell.tsx",),
            "The frame an extension's page is drawn in: the app shell and "
            "the scroll area inside it.",
        ),
        Area(
            "the-table",
            "The table",
            ("DataTable.tsx",),
            "A table with a sortable header and a status cell.",
        ),
        Area(
            "feedback",
            "Feedback",
            ("ErrorBoundary.tsx", "Toast.tsx", "LiveRegion.tsx"),
            "What a page says when something goes wrong, what it says "
            "while it works, and what it announces to a screen reader.",
        ),
        Area(
            "content",
            "Content",
            ("Markdown.tsx", "MarkdownInline.tsx", "Mermaid.tsx", "fenceInfo.ts"),
            "Reading what igni said: Markdown, a diagram, and the "
            "information a fenced block carries.",
        ),
        Area(
            "utilities",
            "Utilities",
            (
                "Split.tsx",
                "MenuIcon.tsx",
                "Monogram.tsx",
                "OverflowMenu.tsx",
                "Skeleton.tsx",
                "Tooltip.tsx",
            ),
            "The small pieces: a split pane, an icon, a monogram, an "
            "overflow menu, a placeholder and a tooltip.",
        ),
    ],
}


__all__ = ["NPM_AREAS", "NPM_ENTRIES", "PYTHON_AREAS"]
