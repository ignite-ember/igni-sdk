"""`python -m igni_service.bundle`: the same as the `igni-service-bundle` command."""

from __future__ import annotations

import sys

from igni_service.bundle.command import main

sys.exit(main())
