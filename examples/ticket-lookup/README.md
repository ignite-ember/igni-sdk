# Ticket lookup

The extension and service that [Your first extension](../../docs/YOUR_FIRST_EXTENSION.md)
builds, step by step. Every file the tutorial shows is a file here, and
a test checks they are the same.

```
extension/          the extension: what runs on a person's machine
  manifest.json     what it is and what it may do
  pyproject.toml    its Python package
  src/acme_tickets_extension/__init__.py
                    two tools, a PostToolUse hook
  ui/index.html     its page
  ui/main.js        the page's script (a file: the page's CSP has no inline scripts)
service/
  service.py        its service: registers with igni server, ships the
                    extension, answers export and erasure
pytest.ini          where pytest looks for tests
tests/
  test_example.py   both, tested on the SDKs' fakes
  test_extension.py the extension's tools, hook and identity
  test_service.py   the service's routes, erasure and export
```

Run the tests from this directory, in an environment with both SDKs
([Step 0](../../docs/YOUR_FIRST_EXTENSION.md#step-0-one-environment-for-the-walk-through)
of the tutorial makes one):

```bash
pytest
```

## Run it

On your own machine, with no igni server, as a development install —
the extension runs and its page shows, and `ticket_from_service` answers
that the service is not set up:

```bash
igni ext doctor extension                          # checks it; "no problems found"
IGNI_DEV_EXTENSIONS=1 igni ext install extension   # installs a copy (--replace after a change)
IGNI_DEV_EXTENSIONS=1 igni --read-only -m "What is the status of ticket T-1001?"
```

Each run here starts with a line like *"igni: …/ticket-lookup is not
trusted — its project tools, hooks, … are off"*. That is about this folder's
own `.igni/` settings, not the extension: the extension's tools and its
`PostToolUse` audit hook are the installed extension's, and they run — the
hook's lines land in `~/.igni/extensions/.data/acme.tickets/tool-audit.log`.
The first run also writes `igni.md` and a `.igni/` directory here, as igni's
first run in any folder does; they are igni's, not the example's, and
`igni-service-bundle` never reads them (delete them before committing).

Shipped the way it reaches other people — bundled, uploaded by its
service, approved and switched on in igni's portal, synced — it needs
igni server: the tutorial's steps
[2](../../docs/YOUR_FIRST_EXTENSION.md#2-bundle-it) (bundle),
[3](../../docs/YOUR_FIRST_EXTENSION.md#3-run-the-service) (run the service),
[4–6](../../docs/YOUR_FIRST_EXTENSION.md#4-a-super-admin-approves-the-service)
(approve, switch on, sign in and sync) and
[7](../../docs/YOUR_FIRST_EXTENSION.md#7-use-it) (use it) give every command.
