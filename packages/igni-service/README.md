# igni-service

**Full documentation:** [ignite-ember.sh/docs/sdk/igni-service](https://ignite-ember.sh/docs/sdk/igni-service) — guides and the complete API reference, a page per topic.

**The Python SDK for an extension's backend service.**

An igni extension usually comes in two parts:

- **The extension itself** runs inside igni, on each person's device or in
  their Fleet VM: a page in the igni app, and a process that gives the
  agent tools. It is built with `igni-extension`, and its page with
  `@ignite-ember/extension-bridge`.
- **Its backend service** is your web service. It runs once, in the
  organisation's cloud or data centre, and keeps what is shared between
  people: comments, tickets, documents. It is built with this package.

The extension's process and its page call the backend service **as the
person signed in to igni**. The service never signs anyone in itself: one
line (`Depends(igni.person)`) tells it who is calling.

What this package does for the service:

- **Joins it to igni.** It creates the service's key and registers it with
  igni server. An igni super admin approves it once, in igni's portal.
- **Ships the extension.** It uploads the extension bundle. Once an org
  admin switches the extension on for a group, every igni in that group
  installs it.
- **Talks to igni for an organisation.** It looks people up in the
  directory, sends notifications, and sends a message or an event to a
  person's or an app's agent, which igni wakes when it needs to.
- **Answers igni's privacy requests.** It erases or exports what the
  service holds about a person.

None of this needs an igni address, token request or signature in the
service's code.

| Package | For |
|---|---|
| `igni-service` | an extension's backend service (this one) |
| `igni-extension` | the extension's process, inside igni |
| `igni-client` | your own program driving an igni from outside: sessions, prompts, commands |

Building a service and its extension for the first time? Follow
[Your first extension](https://github.com/ignite-ember/igni-sdk/blob/main/docs/YOUR_FIRST_EXTENSION.md) from an empty
directory to a working extension and service; this README is the
reference.

Everything here runs in the organisation's own cloud or data centre: igni
server, Fleet, and your service. Ignite Ember hosts none of it.

## Contents

- [Installing](#installing)
- [Quick start](#quick-start)
- [Concepts](#concepts)
  - [Who runs where](#who-runs-where)
  - [Registration and approval](#registration-and-approval)
  - [The extension bundle](#the-extension-bundle)
  - [People's tokens, and other callers](#peoples-tokens-and-other-callers)
  - [Organisations](#organisations)
  - [Producers and their agents](#producers-and-their-agents)
  - [Messages and events](#messages-and-events)
  - [Somebody removed](#somebody-removed)
  - [Privacy requests](#privacy-requests)
  - [What happens on its own](#what-happens-on-its-own)
- [API reference](#api-reference)
  - [IgniService](#igniservice)
  - [IgniSettings](#ignisettings)
  - [Callers: Person, App, Space](#callers-person-app-space)
  - [WebSignIn: sign-in to the service's own pages](#websignin-sign-in-to-the-services-own-pages)
  - [BearerCors: calls from the extension's page](#bearercors-calls-from-the-extensions-page)
  - [Host: igni for one organisation](#host-igni-for-one-organisation)
  - [Directory, Member, Organisation](#directory-member-organisation)
  - [Notification, Target, Delivered](#notification-target-delivered)
  - [Producer, Agent, Chat, Attachment](#producer-agent-chat-attachment)
  - [EventAccepted, ItemStatus](#eventaccepted-itemstatus)
  - [Subject, ExportSection](#subject-exportsection)
  - [VM profiles and IgniApp](#vm-profiles-and-igniapp)
  - [Key and session storage](#key-and-session-storage)
  - [Errors](#errors)
  - [The igni-service-bundle command](#the-igni-service-bundle-command)
  - [igni_service.testing](#igni_servicetesting)
- [Guides](#guides)
  - [Deploying](#deploying)
  - [Building and shipping the extension bundle](#building-and-shipping-the-extension-bundle)
  - [Who is calling: routes, WebSockets and the extension's page](#who-is-calling-routes-websockets-and-the-extensions-page)
  - [Apps and their spaces as callers](#apps-and-their-spaces-as-callers)
  - [Telling people: notifications and the directory](#telling-people-notifications-and-the-directory)
  - [Reaching a producer's agent](#reaching-a-producers-agent)
  - [Erasure, export and a deleted organisation](#erasure-export-and-a-deleted-organisation)
  - [What a VM needs: VM profile requests](#what-a-vm-needs-vm-profile-requests)
  - [Handling errors](#handling-errors)
  - [Testing a service](#testing-a-service)
- [Troubleshooting and FAQ](#troubleshooting-and-faq)
- [Changes since 0.1.0](#changes-since-010)

## Installing

```bash
pip install igni-service        # or: uv add igni-service
```

It needs Python 3.12 or later. It brings FastAPI, httpx, Pydantic,
pydantic-settings, PyJWT with `cryptography`, and SQLAlchemy (async). Add
the async database driver your deployment uses, for example `asyncpg`
for PostgreSQL or `aiosqlite` for SQLite. To run the service, add an ASGI
server such as `uvicorn`.

Each release's wheels and sdists are also attached to igni-sdk's GitHub
release (`sdk-v<version>`), for a build machine that cannot reach PyPI.
The versions, and working from an igni-sdk checkout, are in
[PUBLISHING_THE_SDKS.md](https://github.com/ignite-ember/igni-sdk/blob/main/docs/PUBLISHING_THE_SDKS.md).

## Quick start

A complete service. It takes comments from the extension, notifies the
people watching a document, searches the directory, serves three pages
of its own, and answers igni's erasure and export calls:

```python
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from igni_service import (
    ExportSection, IgniService, IgniSettings, Notification, Person, Subject, Target,
)


class NewComment(BaseModel):
    doc: str
    text: str
    watchers: list[str] = []


def create_app(igni: IgniService | None = None) -> FastAPI:
    """The service. In a test `igni` is `FakeIgni().service()`; in production it is
    read from the environment (see Deploying)."""
    igni = igni or IgniService.from_settings(IgniSettings())
    app = FastAPI(lifespan=igni.lifespan)
    igni.install(app)  # igni's calls, sign-in to this service's pages, calls from the extension's page

    # What this service keeps about people: their comments, by organisation and person.
    comments: dict[tuple[str, str], list[NewComment]] = {}

    @igni.on_erase
    async def erase(subject: Subject) -> None:
        comments.pop((subject.org_id, subject.user_id), None)

    @igni.on_export
    async def export(subject: Subject) -> list[ExportSection]:
        mine = comments.get((subject.org_id, subject.user_id), [])
        return [ExportSection(name="Comments", rows=[{"doc": c.doc, "text": c.text} for c in mine])]

    @app.post("/comments")
    async def comment(body: NewComment, person: Person = Depends(igni.person)) -> NewComment:
        mine = comments.setdefault((person.org_id, person.user_id), [])
        mine.append(body)
        await igni.host(person.org_id).notify(
            Notification(
                kind="comment",
                title=body.doc,
                body=f"{person.display_name}: {body.text}",
                actor=person.user_id,
                target=Target(page="acme.example", params={"doc": body.doc}),
                event_key=f"comment:{person.user_id}:{len(mine)}",
                recipients=body.watchers,
            )
        )
        return body

    @app.get("/mentions")
    async def mentions(query: str, person: Person = Depends(igni.person)) -> list[str]:
        people = await igni.host(person.org_id).directory.members(query=query)
        return [p.email for p in people if p.is_active]

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(person: Person = Depends(igni.web.person)) -> str:
        return f"<h1>Settings for {person.display_name}</h1>"

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(person: Person = Depends(igni.web.super_admin)) -> str:
        return "<h1>Every organisation</h1>"

    @app.get("/organisation/settings", response_class=HTMLResponse)
    async def org_settings(person: Person = Depends(igni.web.org_admin)) -> str:
        return f"<h1>{person.org_name}</h1>"

    return app
```

Run it with `uvicorn --factory service:create_app`, with the environment
variables in [Deploying](#deploying). It is a factory, not a module-level
`igni = IgniService.from_settings(...)`, so a test can hand it igni
in-process instead. This is that test. It runs as it is, with no igni
server:

<!-- continues -->
```python
import httpx

from igni_service import Member
from igni_service.testing import FakeIgni

fake = FakeIgni()
fake.directory.add_member("org-1", Member(user_id="u-ada", email="ada@acme.test", name="Ada"))
fake.directory.add_member("org-1", Member(user_id="u-max", email="max@acme.test", name="Max"))
app = create_app(fake.service())

ada = {"Authorization": f"Bearer {fake.signer.person_token('u-ada', org_id='org-1')}"}
igni_itself = {"Authorization": f"Bearer {fake.signer.igni_token('org-1')}"}
transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url=fake.addresses.service_url) as http:
    sent = await http.post(
        "/comments", json={"doc": "runbook", "text": "Looks good", "watchers": ["u-max"]}, headers=ada
    )
    assert sent.status_code == 200, sent.text
    assert [d.user_id for d in fake.notifications.deliveries] == ["u-max"]

    exported = await http.get("/v1/igni/subjects/u-ada/export", headers=igni_itself)
    assert exported.json()["sections"][0]["rows"] == [{"doc": "runbook", "text": "Looks good"}]
    assert (await http.delete("/v1/igni/subjects/u-ada", headers=igni_itself)).status_code == 204
```

## Concepts

Each idea is explained once here. The [API reference](#api-reference)
and the [Guides](#guides) build on these words.

### Who runs where

| Part | Runs | Built with |
|---|---|---|
| **The igni app** | on each person's device: the window they work in | (igni) |
| **The igni backend** | on each person's device, or in their Fleet VM: the agent, and the extensions it starts | (igni) |
| **The extension's page** | in the igni app, in a sandboxed frame | `@ignite-ember/extension-bridge` |
| **The extension's process** | started by the igni backend in an OS sandbox; gives the agent tools and hooks | `igni-extension` |
| **The extension's backend service** | once per deployment, in the organisation's cloud or data centre | `igni-service` (this package) |
| **igni server** | once per deployment, in the organisation's cloud or data centre: people, organisations, tokens, extensions | (igni) |
| **Fleet** | in the organisation's cloud or data centre: a microVM per person or app, for agents that run there instead of on a device | (igni) |

Your service talks to **igni server** only. It never talks to a person's
device directly. igni server stores what the service sends and the
person's igni fetches it.

### Registration and approval

A service has its **own key**, an RSA key pair made on its first start.
The key is the service's identity. Its public half is registered with
igni server; its private half never leaves the service.

On every start the service **registers**: it sends its name, its public
URL and its public key to igni server. The same key always finds the
same registration, so a restart is not a new service. igni server
answers with a **client id** and a **state**:

| State | Meaning | What comes next |
|---|---|---|
| `pending` | registered, not yet trusted | A super admin opens igni's portal (*Services*), compares the **thumbprint** the service logged with the one shown there, and approves it. |
| `approved` | trusted | The service may get **service tokens**, and its extension may be installed. |
| `revoked` | a super admin withdrew trust | Nothing the service asks igni for works. |

A **thumbprint** is a short fingerprint of the public key (RFC 7638). The
super admin compares it so they know they approve *your* deployment and
not an impostor with the same name.

A **service token** is the token the service gets for itself, for one
organisation at a time, to call igni server's directory, notifications
and agents. The SDK gets and renews these for you. Until approval every
call that needs one raises `ServiceNotApproved`; after a revoke,
`ServiceRevoked`.

igni refuses such a token with `invalid_client`, and the SDK tells the
two apart by the registration's **state**, a field, never by the words
of igni's message: the `client_state` igni sends beside `invalid_client`
(`pending` or `revoked`; every igni server since 0.7.0 sends it). Any
other refusal, and an `invalid_client` that names no state, is a plain
`IgniUnavailable`.

### The extension bundle

The **extension bundle** is one `.tar.gz` file: the extension's
`manifest.json`, its `README.md`, its `plugin/` and `ui/` directories,
and a **wheelhouse** — the extension's own wheel and every dependency's,
for each platform igni runs on. A device with no internet installs from
it. You build it with the [`igni-service-bundle`](#the-igni-service-bundle-command)
command.

The service **uploads** the bundle to igni server, signed with its key,
whenever igni server holds different bytes. Two separate decisions then
put it on a person's device, and **both** are needed:

1. a **super admin approves the service** (portal, *Services*), and
2. an **org admin switches the extension on for a group** (portal, the
   group's *Extensions* tab). Each person is in exactly one group.

Every signed-in igni of a person in that group installs the extension the
next time it syncs with igni server. Approval alone installs it nowhere.
An org admin can only switch on an approved service's extension.

A **new version** that asks for more than the approved one (a new tool, a
wider grant) is **held** for a super admin. Devices keep the approved
version until a super admin approves the new one.

**Assets** are files the extension runs that are not Python: a database,
a JVM, a model. They travel beside the bundle, not inside it, each pinned
by size and SHA-256 in the manifest.

### People's tokens, and other callers

A person signed in to igni can get a token **for your service**: a JWT
that igni server signs, whose audience (`aud`) is your service's public
URL. The extension's process and page attach it to every call. The
service checks it against igni server's published keys, with no call to
igni per request, and reads who the person is from it.

The token is good for ten minutes. The extension renews it on its own.

Three kinds of caller can bring such a token:

| Caller | Who | Token's `token_use` |
|---|---|---|
| `Person` | a person in one organisation | `user` |
| `App` | an app of one organisation, acting as itself | `app` |
| `Space` | one end user of an app | `space` |

A service accepts **people only** unless it says otherwise.

igni itself also calls the service, for privacy requests. Its token has
`token_use` `igni` and names one organisation. `IgniCall` is that caller.

The service's **own pages** (settings, an admin page) are a different
door: a person opens them in a browser, signs in through igni's portal,
and gets a session cookie. That is [`igni.web`](#websignin-sign-in-to-the-services-own-pages).

### Organisations

igni is multi-tenant. One deployment holds many **organisations**. A
person's token names exactly one organisation (`org_id`), and so does
every service token. A service token for one organisation can never see
another's people.

So everything a service asks of igni is asked **for one organisation**:
`igni.host(org_id)`. Usually that is the organisation of the person
calling: `igni.host(person.org_id)`.

### Producers and their agents

A **producer** is somebody igni runs an agent for: a **person**, or an
**app**. Each producer's igni runs on their device, or in their own Fleet
VM.

Your service can reach a producer's agent through igni server. igni
server stores what the service sends; the producer's igni takes it when
it is running (a Fleet VM is woken for it). igni keeps it at most 14
days.

### Messages and events

There are two ways to reach an agent:

- **A message is for the agent.** igni posts it exactly as sent, labelled
  as your extension's message. It starts a run, or waits for the run
  already going. No extension code is involved.
- **An event is for your extension.** igni hands it to the extension's
  `@ext.on_service_event(type)` handler and posts nothing. The handler
  decides what to do; the agent runs only if the handler posts.

Send a message when you know what the agent should read. Send an event
when the extension should decide: look something up on the producer's
device, choose a chat, post or not.

A **thread** is your own key for a conversation, such as
`"claim:CL-20431"`. The first item of a thread opens a chat for it in the
producer's igni; every later item goes there. Without a thread, a message
goes to your extension's own chat. Nothing a service sends lands in the
chat a person has open.

### Somebody removed

When a person is removed from an organisation (or deactivated, erased,
or their sessions withdrawn), or an app or a space is deleted, igni
server publishes a **revocation**. While the service runs it follows
these revocations and refuses a token issued before the revocation at
once, not when the token would expire. Someone added back signs in again
afterwards.

### Privacy requests

An org admin can ask igni to **erase** or **export** everything held
about a person. igni server asks every approved service. Your service
answers through two handlers you write: `@igni.on_erase` and
`@igni.on_export`. igni also tells the service when an **organisation is
deleted** (`@igni.on_organisation_deleted`).

### What happens on its own

`igni.lifespan` (the FastAPI lifespan) does the following in the
background. It retries with backoff while igni server is unreachable, so
the service starts and serves either way.

- **Its key.** Generated on first start (RSA, RS256), sealed with the key
  encryption key, kept in the key store. Every replica signs with the same
  key; replicas starting together agree on one.
- **Registration.** On every start, with the key's public half. A restart
  finds the same registration.
- **The banner.** The client id, state, URL and thumbprint are logged,
  with the next step for that state:

  ```text
    ============================================================
    igni service identity
      client id:   09075090-00ee-446b-bc17-67ddb2b30023
      state:       pending
      URL:         https://notes.bank.internal
      thumbprint:  mYhl4fFoNkMKUZLRePT1ppX00Eq7Q12RGPPak-4_OAo
    A super admin approves this service in igni's portal under
    Services, after checking the thumbprint there is this one.
    ============================================================
  ```

- **The extension bundle** (`IGNI_EXTENSION_BUNDLE`) is uploaded, signed,
  whenever igni server holds different bytes. Its assets go first, read
  from `extension-bundle.assets/` beside it, each one igni does not hold
  yet. A held version is logged as a warning, with igni's reason.
- **Revocations.** It follows igni's revocations for every organisation
  it serves (see [Somebody removed](#somebody-removed)).
- **Log lines show under uvicorn.** uvicorn configures only its own
  loggers, so `igni.lifespan` gives the `igni_service` logger a stderr
  handler at INFO when neither it nor the root logger has one. Configure
  logging yourself and it is left as you configured it.

A bundle igni refuses, or one that cannot be read, is logged as an error
and not retried: the same bytes would be refused again. The service keeps
running.

## API reference

Everything below is importable from `igni_service` unless it says
otherwise. Signatures are shown as Python stubs.

### IgniService

A service's place in an igni deployment. Make one per process.

```py
class IgniService:
    def __init__(
        self,
        settings: IgniSettings,
        *,
        key_store: KeyStore,
        web_store: WebSessionStore | None = None,
        http: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
        retry_min: float | None = None,
        accepted_callers: Collection[CallerKind] = PEOPLE_ONLY,
    ) -> None: ...
```

| Parameter | Meaning |
|---|---|
| `settings` | the [`IgniSettings`](#ignisettings): igni server's URL, this service's URL and name, and the rest |
| `key_store` | where the service's key is kept: a [`KeyStore`](#key-and-session-storage) such as `SqlKeyStore` |
| `web_store` | where sign-in sessions for the service's own pages are kept; default `MemoryWebSessionStore` (one process only) |
| `http` | the `httpx.AsyncClient` to reach igni server with; default, one of its own |
| `clock` | a clock, for tests that move time |
| `retry_min` | the first pause, in seconds, between registration attempts (default 5, doubling to 300) |
| `accepted_callers` | which [callers](#callers-person-app-space) `igni.caller` accepts; default people only |

Raises `ConfigurationError` when `IGNI_SERVER_URL`, `PUBLIC_BASE_URL` or
`SERVICE_NAME` is empty, or `PUBLIC_BASE_URL` is not an absolute
`http(s)` URL without a query or fragment.

Construct it directly when you hand over your own stores
([Deploying](#deploying)). Otherwise use `from_settings`.

#### IgniService.from_settings

```py
@classmethod
def from_settings(
    cls,
    settings: IgniSettings,
    *,
    key_store: KeyStore | None = None,
    http: httpx.AsyncClient | None = None,
    clock: Clock | None = None,
) -> IgniService: ...
```

A service from its settings. With no `key_store`, it keeps both the key
and the sign-in sessions in `IGNI_KEY_DATABASE_URL` (`SqlKeyStore` and
`SqlWebSessionStore`, sealed with `IGNI_KEY_ENCRYPTION_KEY`), on an engine
it opens and closes itself. Pass `key_store` to keep the key elsewhere;
sessions then stay in memory, so to keep both elsewhere construct
`IgniService` directly with a `web_store` too.

Raises `ConfigurationError` when there is no `key_store` and no
`IGNI_KEY_DATABASE_URL`, and everything the constructor raises.

#### IgniService.lifespan

```py
@contextlib.asynccontextmanager
async def lifespan(self, app: Any = None) -> AsyncIterator[None]: ...
```

Runs [what happens on its own](#what-happens-on-its-own) for as long as
the app runs, then closes what the service opened. Use it as
`FastAPI(lifespan=igni.lifespan)`, or inside your own lifespan:

```py
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with igni.lifespan(app):
        yield
```

A service that never enters `lifespan` does not register, does not
upload its bundle, and does not check revocations.

#### IgniService.install

```py
def install(self, app: FastAPI) -> None: ...
```

Puts igni's part of the service on `app`: igni's calls (`igni.router`),
sign-in to the service's own pages (`igni.web.router`), and the
[`BearerCors`](#bearercors-calls-from-the-extensions-page) middleware for
calls from the extension's page. Call it once, right after creating the
app.

#### IgniService.router

```py
@property
def router(self) -> APIRouter: ...
```

The routes igni server calls. `install` mounts it; mount it yourself only
when you do not call `install`.

| Route | Handler | Answer |
|---|---|---|
| `DELETE /v1/igni/subjects/{user_id}` | `@igni.on_erase` | 204; 501 with no handler |
| `GET /v1/igni/subjects/{user_id}/export` | `@igni.on_export` | 200 `{"sections": [...]}`; 501 with no handler |
| `DELETE /v1/igni/organisations/{org_id}` | `@igni.on_organisation_deleted` | 204; 403 when the token is for another organisation; 501 with no handler |

Each takes only igni's own token for this service (`token_use` `igni`).

#### IgniService.on_erase, on_export, on_organisation_deleted

```py
def on_erase(self, handler: Callable[[Subject], Awaitable[None]]) -> ...: ...
def on_export(self, handler: Callable[[Subject], Awaitable[list[ExportSection]]]) -> ...: ...
def on_organisation_deleted(self, handler: Callable[[str], Awaitable[None]]) -> ...: ...
```

Decorators. Each registers one `async` handler and returns it unchanged.
Registering again replaces the previous handler.

- `on_erase` — erase one person's data in one organisation. Receives a
  [`Subject`](#subject-exportsection). Must be idempotent: igni repeats it
  until every service confirms.
- `on_export` — list one person's data in one organisation. Receives a
  `Subject`; returns a list of [`ExportSection`](#subject-exportsection).
- `on_organisation_deleted` — receives the deleted organisation's id.
  Stop routing to its data; keeping or dropping the data is your
  decision. Must be idempotent.

See [Erasure, export and a deleted organisation](#erasure-export-and-a-deleted-organisation).

#### FastAPI dependencies for callers

Use each as `Depends(igni.<name>)`. Every one reads the
`Authorization: Bearer <token>` header.

| Dependency | Returns | Refuses with |
|---|---|---|
| `igni.person` | `Person` | 401 for a missing or refused token; 503 when the token cannot be checked |
| `igni.org_admin` | `Person` whose `org_role` is `admin` | as `person`, and 403 for anybody else (a super admin included) |
| `igni.optional_person` | `Person`, or `None` when no token was sent | 401 for a token that was sent and refused; 503 |
| `igni.caller` | `Person`, `App` or `Space`, among `accepted_callers` | 401 for any other kind; 503 |
| `igni.token` | the bearer token, **not checked** | 401 when none was sent |
| `igni.optional_token` | the bearer token, not checked, or `None` | never |
| `igni.igni_call` | `IgniCall` (igni server itself) | 401; 503 |

A refused token is answered **401**, body `{"detail": "Not authenticated"}`
always. The reason is in the `WWW-Authenticate` header, as RFC 6750 has
it, and in the service's log at INFO:

- no token: `Bearer`
- a refused token: `Bearer error="invalid_token", error_description="<reason>"`

The reasons, word for word: *the token is not a JWT*, *the token is not
signed by igni server's keys*, *the token is for another audience; this
service's is …*, *the token was issued by somebody other than igni
server*, *the token has no '…' claim*, *the wrong kind of token:
token_use '…', and this takes …*, *the token's exp or iat is not a
number*, *the token has expired*, *the token was issued in the future;
check this machine's clock*, *the token names no person, or no
organisation*, and *the token was revoked: its holder was removed or signed out*
for a person removed since.

A token that cannot be checked, because igni server's keys cannot be
fetched or the revocations are not fresh, is answered **503**: nothing is
wrong with the token, and signing in again would not help.

`igni.person` stays **people only** whatever `accepted_callers` says, so
a route meant for people never takes an app for one. Being a super admin
does not make somebody an organisation's admin.

#### IgniService.person_of, caller_of

```py
async def person_of(self, token: str) -> Person: ...
async def caller_of(self, token: str) -> Caller: ...
```

The same checks for a token held outside a request header: a WebSocket
greeting, a queued job. They raise exceptions instead of HTTP errors, so
you answer in your own protocol:

- `TokenRefused` — the token is not acceptable; `.reason` says why.
- `IgniUnavailable` — it cannot be checked now.

A leading `Bearer ` is stripped if present.

#### IgniService.host

```py
def host(self, org_id: str) -> Host: ...
```

igni server for one organisation: [`Host`](#host-igni-for-one-organisation).
Cheap: make one per request. Raises `ValueError` for an empty `org_id`.

#### IgniService.thumbprint

```py
async def thumbprint(self) -> str: ...
```

The key's RFC 7638 thumbprint, as the banner logs it and a super admin
compares it. Makes the key if there is none yet.

#### IgniService.challenge

```py
@staticmethod
def challenge(refused: TokenRefused | None = None) -> str: ...
```

The `WWW-Authenticate` value for a 401, as the dependencies send it. For a
route that checks tokens itself with `person_of` and wants to answer the
same way.

#### IgniService.aclose

```py
async def aclose(self) -> None: ...
```

Closes the service's HTTP client and the database engine
`from_settings` opened. `lifespan` calls it on the way out.

#### Attributes

| Attribute | What |
|---|---|
| `igni.settings` | the `IgniSettings` it was made with |
| `igni.web` | the [`WebSignIn`](#websignin-sign-in-to-the-services-own-pages) for the service's own pages |
| `igni.accepted_callers` | the `frozenset[CallerKind]` `igni.caller` accepts |
| `igni.connection` | its standing at igni server: `server`, `clock`, `key`, `registration` and the `revocation_feed` |
| `igni.outbound` | the calls it makes to igni for any organisation; `igni.host(org_id)` is one organisation's |

### IgniSettings

```py
class IgniSettings(pydantic_settings.BaseSettings):
    igni_server_url: str = ""
    public_base_url: str = ""
    service_name: str = ""
    client_kind: str = "service"
    redirect_uris: list[str] = []
    key_encryption_key: str = ""
    key_database_url: str = ""
    extension_bundle_path: str = ""
    revocations_max_staleness: float = 30.0
    timeout: float = 10.0
```

What a service is deployed with, read from the environment by
`IgniSettings()`. Every field can also be passed by name:
`IgniSettings(igni_server_url="https://igni.bank.internal", ...)`.

| Field | Environment variable | Meaning |
|---|---|---|
| `igni_server_url` | `IGNI_SERVER_URL` (or `IGNI_SERVER_BASE_URL`) | Where this service reaches igni server. Often an in-cluster address, not igni's public URL; the two need not match. **Required.** |
| `public_base_url` | `PUBLIC_BASE_URL` | This service's own public URL, on a hostname of its own. The audience of every token people bring, and where igni calls it. **Required.** |
| `service_name` | `SERVICE_NAME` | What the service is called in igni's portal. **Required.** |
| `client_kind` | `IGNI_CLIENT_KIND` | `service` (default), or `app` for something acting only for signed-in people. |
| `redirect_uris` | `IGNI_REDIRECT_URIS` | Extra places a browser may return to after sign-in, as a JSON list. `<PUBLIC_BASE_URL>/auth/callback` is always registered. |
| `key_encryption_key` | `IGNI_KEY_ENCRYPTION_KEY` | The Fernet key the service's private key and sessions are sealed with. |
| `key_database_url` | `IGNI_KEY_DATABASE_URL` | An async SQLAlchemy URL for the key and sessions, e.g. `postgresql+asyncpg://…`. Used by `from_settings`. |
| `extension_bundle_path` | `IGNI_EXTENSION_BUNDLE` (or `EXTENSION_BUNDLE_PATH`) | The extension bundle to upload. Empty: nothing is uploaded. |
| `revocations_max_staleness` | `IGNI_REVOCATIONS_MAX_STALENESS` | Seconds the revocation list may go unrefreshed before every token is refused. Default 30. |
| `timeout` | `IGNI_SERVER_TIMEOUT` | Seconds before a call to igni server gives up. Default 10. |

Unknown environment variables are ignored.

### Callers: Person, App, Space

```py
class Person(BaseModel):       # frozen
    user_id: str
    org_id: str
    org_name: str = ""
    org_role: str = "member"   # "admin" or "member" in org_id
    email: str = ""
    name: str = ""
    super_admin: bool = False

    kind: CallerKind           # property: CallerKind.PERSON
    is_org_admin: bool         # property: org_role == "admin"
    display_name: str          # property: name, else email
    is_named: bool             # property: the token named the person and the organisation

class App(BaseModel):          # frozen
    app_id: str
    org_id: str
    name: str = ""
    kind: CallerKind           # property: CallerKind.APP
    is_named: bool             # property: the token named the app and its organisation

class Space(BaseModel):        # frozen
    space_id: str
    org_id: str
    app_id: str                # the app the space belongs to
    external_id: str = ""      # the app's own name for its end user
    kind: CallerKind           # property: CallerKind.SPACE
    is_named: bool             # property: the token named the space, its app and organisation

Caller = Person | App | Space

class CallerKind(StrEnum):
    PERSON = "person"
    APP = "app"
    SPACE = "space"

PEOPLE_ONLY: frozenset[CallerKind]   # {CallerKind.PERSON}: the default

class IgniCall(BaseModel):     # frozen: igni server itself, for one organisation
    org_id: str

class TokenRefused(IgniError):
    reason: str
```

Each model has a `from_claims(claims: VerifiedClaims) -> Self` class
method that reads a verified token's claims (`sub`, `org`, `org_name`,
`org_role`, `email`, `name`, `super_admin`; `app` and `external_id` for a
space). `VerifiedClaims` is the typed model of a checked token: a claim
that is text is read as text (a missing or null one is empty), `exp` and
`iat` are finite numbers, and `super_admin` is only ever the JSON `true`.
The dependencies call both for you.

`TokenRefused(reason)` is what `person_of` and `caller_of` raise. Its
`reason` is said only in terms anybody holding the token could read from
it (expired, another audience, the wrong kind), or as "not signed by igni
server's keys" for everything about its signature.

### WebSignIn: sign-in to the service's own pages

`igni.web` signs people in to pages the service serves itself, through
igni's portal (OAuth 2 authorization code with PKCE, all on the server).
The browser holds only an opaque session id in an `HttpOnly`,
`SameSite=Lax` cookie (`Secure` on https). The person's tokens stay on the
server and are renewed a minute before they expire.

Routes (on `igni.web.router`, mounted by `igni.install`):

| Route | What |
|---|---|
| `GET /auth/login?return_to=/path` | Sends the browser to igni's portal; comes back to `return_to` (a path on this service only; anything else becomes `/`). 503 when igni cannot be reached. |
| `GET /auth/callback` | igni sends the browser back here. Opens the session and redirects to `return_to`. 400 for a sign-in that was not started here, expired (10 minutes), or that igni refused. |
| `GET` or `POST /auth/logout?return_to=/path` | Ends the session here, then revokes its refresh token at igni so the sign-in is over there too. Works even if igni cannot be reached. The person stays signed in to igni's own portal. |

Dependencies:

| Dependency | Returns | Otherwise |
|---|---|---|
| `igni.web.person` | the signed-in `Person` | a page (a request that accepts `text/html`) is sent to sign in and back (303); anything else gets 401 `Not signed in` |
| `igni.web.signed_in` | the signed-in `Person`, or `None` | never sends anybody to sign in; a session igni cannot renew counts as nobody |
| `igni.web.super_admin` | a signed-in super admin | 403 `Super admins only` |
| `igni.web.org_admin` | a signed-in admin of the organisation they signed in to | 403 `Organisation admins only`, super admins included |

When igni refuses to renew a session (the person was removed or
deactivated), they are signed out here. When igni cannot be reached and
the access token has already expired, the request is answered 503.

Properties and constants:

| Name | Value |
|---|---|
| `login_path` | `"/auth/login"`: what a page links to |
| `logout_path` | `"/auth/logout"`: what a page posts (or links) to |
| `redirect_uri` | `"<PUBLIC_BASE_URL>/auth/callback"` |
| `store` | the `WebSessionStore` in use |
| `router` | the three routes |
| `WebSignIn.COOKIE` | `"igni_session"` |
| `WebSignIn.LOGIN_TTL` | 600 s for a sign-in at the portal |
| `WebSignIn.SESSION_TTL` | 30 days from the sign-in or its last renewal: a session not renewed within it is dead |
| `WebSignIn.RENEW_BEFORE` | 60 s |

These sessions use cookies, so they are **not** reachable from the
extension's page, which calls with a bearer token instead.

### BearerCors: calls from the extension's page

```py
class BearerCors:   # ASGI middleware
    def __init__(self, app: ASGIApp, *, igni: IgniService) -> None: ...
```

The extension's page runs in the igni app, on igni's origin, and calls
the service with `bridge.service.fetch`: a bearer token, no cookies. That
is a cross-origin call, so the browser needs the service's yes.
`igni.install(app)` adds this middleware; there is nothing to configure.

- A **bearer route** answers any origin (`Access-Control-Allow-Origin: *`)
  when the call carries `Authorization: Bearer`. A bearer route is one
  that depends on `igni.person`, `igni.optional_person`, `igni.org_admin`,
  `igni.caller`, `igni.token` or `igni.optional_token` — directly, through
  a router's `dependencies`, or through your own dependency built on them,
  however deeply nested. The token is the whole of the authority. A
  refused token's 401 is readable too, so the page can fetch a new token.
- **Credentials are never allowed.** A browser sends no cookies on such a
  call, so the service's own sessions (`igni.web.*`) stay out of reach.
- A route on `igni.web.*` (even one that also takes a token), igni's own
  calls (`igni.igni_call`), and a route that takes no token get no
  cross-origin yes.
- A preflight is answered with `GET, HEAD, POST, PUT, PATCH, DELETE` and
  the headers `Authorization` and `Content-Type` (kept 600 s), only when
  the call will carry `Authorization`, and never for `/auth/` or
  `/v1/igni/`.

WebSockets are not CORS: a page's socket proves itself with its token in
the first frame (see [`person_of`](#igniserviceperson_of-caller_of)).

### Host: igni for one organisation

```py
host = igni.host(org_id)
```

| Member | What |
|---|---|
| `host.org_id` | the organisation |
| `host.directory` | the organisation's [`Directory`](#directory-member-organisation) |
| `await host.notify(*notifications)` | tell people something; returns `Delivered` |
| `host.agent(producer)` | a producer's [`Agent`](#producer-agent-chat-attachment) |
| `await host.send_event(producer, type, payload=None, *, event_key=None, expires_at=None)` | `host.agent(producer).send_event(...)`, kept for older code; returns `EventAccepted` |
| `await host.extension_vm_profile()` | what became of this service's extension's VM profile request here; returns `ServiceVmProfile` |
| `await host.vm_profile()` | deprecated: emits `DeprecationWarning`, then does `extension_vm_profile()` |

#### Host.notify

```py
async def notify(self, *notifications: Notification) -> Delivered: ...
```

Tells people in this organisation that something happened. Any number of
notifications go in as few calls as igni accepts: at most 100 per call,
and at most 1000 recipients per notification (a longer list is split,
keeping the same `event_key`). A notification with no recipients is not
sent.

igni keeps only the **active members** of the organisation among the
recipients, never tells the `actor`, and tells each person about an
`event_key` once. So `Delivered.delivered` can be smaller than the
number of recipients; that is normal.

A call igni could not take (a network error, 429 or 5xx) is tried three
times, pausing 0.5 s then 1 s. With an `event_key` a retry is exact;
without one, a retry after a lost reply can tell somebody twice.

Raises:

- `IgniUnavailable` — igni could not take them after retrying (including
  `ServiceNotApproved` and `ServiceRevoked`).
- `NotificationRefused` — igni read them and said no (a 4xx other than
  429). Sending them again will not help.

Catch `IgniError` if notifying is best effort for you.

#### Host.extension_vm_profile

```py
async def extension_vm_profile(self) -> ServiceVmProfile: ...
```

What became of this service's extension's `vm` request in this
organisation. See [VM profiles](#vm-profiles-and-igniapp). Raises
`IgniUnavailable`.

### Directory, Member, Organisation

```py
class Directory:            # host.directory
    org_id: str
    async def organisation(self) -> Organisation: ...
    async def members(
        self, *, query: str = "", limit: int = 100, include_former: bool = False
    ) -> list[Member]: ...
    async def person(self, user_id: str) -> Member | None: ...
    async def resolve(self, identities: list[str]) -> dict[str, Member]: ...
```

A service keeps no user table. The caller arrives in their token; anybody
else — a colleague to mention, a document's owner — is asked of igni
server's directory, for one organisation.

- `organisation()` — the organisation itself.
- `members(query=, limit=, include_former=)` — a prefix search on address
  or name. `limit` is clamped to 1–500. Former members (who have left)
  are included only with `include_former=True`.
- `person(user_id)` — one person, present or former; `None` if they were
  never a member.
- `resolve(identities)` — user ids or email addresses to members, present
  and former. The answer is keyed by **every** spelling a member answers
  to, casefolded: their user id and their address. An identity that is
  nobody is simply absent. Answers are cached for 30 seconds per
  organisation (a convenience, not an authorisation cache).

Every method raises `IgniUnavailable` (including `ServiceNotApproved` and
`ServiceRevoked`) when igni cannot answer.

```py
class Member(BaseModel):        # frozen
    user_id: str
    email: str = ""
    name: str = ""
    role: str = "member"        # "admin" or "member"
    status: str = "active"      # "active", or "deactivated" for somebody who left
    super_admin: bool = False
    is_active: bool             # property: status == "active"
    display_name: str           # property: name, else email

class Organisation(BaseModel):  # frozen
    org_id: str
    name: str = ""
    slug: str = ""
    tenant_number: int = 0      # derive per-organisation databases and index names from this
    domains: list[str] = []
```

### Notification, Target, Delivered

```py
class Notification(BaseModel):   # frozen; unknown fields refused
    kind: str                    # 1–64 chars: your word for what happened, e.g. "comment"
    title: str                   # 1–200 chars: what it is about
    body: str = ""               # one line; whitespace collapsed; igni cuts a long one
    actor: str = ""              # who did it (user id or address), never told; ≤ 320 chars
    target: Target | None = None # where to go when it is clicked
    event_key: str = ""          # ≤ 200 chars: delivered once per person, however often sent
    recipients: list[str] = []   # user ids or addresses in this organisation; each ≤ 320 chars

    def split(self, size: int) -> list[Notification]: ...

class Target(BaseModel):         # frozen; unknown fields refused
    page: str                    # 1–200 chars: one of your extension's pages
    params: dict[str, str | int | float | bool | None] = {}  # ≤ 32 entries, ≤ 2048 bytes as JSON

class Delivered(BaseModel):
    delivered: int = 0           # deliveries igni wrote
```

Recipients are trimmed and de-duplicated. A value over a limit raises
Pydantic's `ValidationError` when the model is made, before anything is
sent. `split(size)` returns the notification with its recipients in
groups of at most `size`; `notify` uses it for you.

### Producer, Agent, Chat, Attachment

```py
class Producer(BaseModel):            # frozen
    kind: Literal["person", "app"]
    id: str

    @classmethod
    def person(cls, user_id: str) -> Producer: ...
    @classmethod
    def app(cls, app_id: str) -> Producer: ...
```

#### Agent

`agent = igni.host(org_id).agent(Producer.person(user_id))`

```py
class Agent:
    producer: Producer

    async def send_message(
        self, text: str, *,
        attachments: list[Attachment] | None = None,
        thread: str | None = None,
        title: str | None = None,
        start_run: bool = True,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventAccepted: ...

    async def send_event(
        self, type: str, payload: dict[str, object] | None = None, *,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> EventAccepted: ...

    async def new_chat(
        self, title: str, *,
        thread: str | None = None,
        text: str | None = None,
        attachments: list[Attachment] | None = None,
        event_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> Chat: ...

    def chat(self, thread: str) -> Chat: ...

    async def status(self, event_id: str) -> ItemStatus: ...

    async def send_item(self, kind, *, text=None, attachments=None, thread=None, title=None,
                        start_run=True, action=None, event_key=None, expires_at=None
                        ) -> EventAccepted: ...
```

- `send_message(text, ...)` — post `text` as your extension's message. It
  starts a run, or waits for the run going. `start_run=False` waits for
  the chat's next run instead. `thread` puts it in that thread's chat;
  `title` names the chat when this message opens it. `text` is 1–65 536
  characters, `thread` and `title` at most 200.
- `send_event(type, payload)` — hand your extension an event. igni posts
  nothing for it. `type` is 1–100 characters, `payload` at most 64 KiB as
  JSON. Needs no grant.
- `new_chat(title, thread=None, text=None, ...)` — open a chat titled
  `title` for `thread` (or a new thread of its own, `chat:<uuid>`),
  optionally with a first message. Returns its `Chat`.
- `chat(thread)` — a handle on a thread's chat. Sends nothing by itself.
- `status(event_id)` — what became of any item sent: an `ItemStatus` whose `state` is `pending`, `delivered`, `not_handled`, `expired`, `dropped` or `failed` ([the states](#eventaccepted-itemstatus)).
- `send_item(kind, ...)` — the low-level call all the others use. `kind`
  is `"event"`, `"message"`, `"chat"` or `"action"`.

For every send: `event_key` (1–200 characters) makes retries exact — igni
stores one item per key and producer, and answers a repeat with the item
already stored (`duplicate=True`). `expires_at` stops delivery after that
time; igni keeps an item at most 14 days (igni server's default,
`service_event_max_wait_seconds`; an operator may change it).
Attachments are uploaded first.

Each send raises `IgniUnavailable` when igni cannot take it after three
tries, and `EventRefused` when igni reads it and says no (a 4xx other
than 429): the producer is not in the organisation, does not have the
extension, the extension does not declare the grant, or the item is
invalid. A value over a limit raises `ValidationError` before anything
is sent.

**Grants.** Beyond a plain event, your extension declares what its
service may send, in its manifest:
`"permissions": {"service": ["messages", "attachments", "chats"]}`. The
super admin approves them with the service. igni refuses the rest with
`EventRefused` (403): `service.messages` for a message,
`service.attachments` for files, `service.chats` for a thread,
`new_chat` and a chat's actions.

#### Chat

```py
class Chat:
    thread: str

    async def send_message(self, text: str, *, attachments=None, event_key=None,
                           expires_at=None) -> EventAccepted: ...
    async def queue(self, text: str, *, attachments=None, event_key=None,
                    expires_at=None) -> EventAccepted: ...
    async def show(self, view: dict[str, Any], *, title: str | None = None,
                   event_key: str | None = None) -> EventAccepted: ...
    async def rename(self, title: str, *, event_key: str | None = None) -> EventAccepted: ...
    async def cancel(self, *, event_key: str | None = None) -> EventAccepted: ...
```

- `send_message` — post in this chat; a run starts, or it waits for the
  run going.
- `queue` — for the chat's next run; starts nothing.
- `show(view)` — show a json-render view (`{"root": ..., "elements": {...}}`)
  in the chat. It is shown to the person and never sent to the model.
- `rename(title)` — rename the chat. Only chats your service opened.
- `cancel()` — stop the chat's working run. A run waiting on a person's
  approval is left alone.

#### Attachment

```py
class Attachment(BaseModel):     # frozen
    filename: str                # 1–200 chars
    content_type: str = "application/octet-stream"
    data: bytes                  # 1 byte to 5 MiB

    @classmethod
    def from_bytes(cls, filename: str, data: bytes, content_type: str | None = None) -> Attachment: ...
    @classmethod
    def from_path(cls, path: str | Path, content_type: str | None = None) -> Attachment: ...
```

Any type igni's composer takes, at most 5 MiB each, at most 10 per item.
The content type is guessed from the file name when not given. Files are
uploaded before the item and kept by igni server only as long as the
item. The producer's igni imports them into the chat as a person's upload
would be. A message with files that arrives during a run waits for the
run to end. An upload igni refuses raises `EventRefused`; one it cannot
take raises `IgniUnavailable`.

### EventAccepted, ItemStatus

```py
class EventAccepted(BaseModel):
    event_id: str
    expires_at: datetime | None = None   # the time igni kept
    duplicate: bool = False              # True when event_key matched an item already stored

class ItemStatus(BaseModel):
    event_id: str
    producer: Producer
    kind: Literal["event", "message", "chat", "action"] = "event"
    type: str
    thread: str | None = None
    event_key: str | None = None
    state: Literal["pending", "delivered", "not_handled", "expired", "dropped", "failed"]
    dropped_reason: str | None = None
    failed_reason: str | None = None
    not_handled_reason: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    delivered_at: datetime | None = None
    updated_at: datetime
```

| `state` | Meaning |
|---|---|
| `pending` | stored; the producer's igni has not taken it yet |
| `delivered` | a message posted, or an event a handler took |
| `not_handled` | an event no handler took (no handler for its type, no running extension, or the handler raised); `not_handled_reason` says which |
| `expired` | not taken before `expires_at` (14 days at most) |
| `dropped` | the producer no longer has the extension; `dropped_reason` |
| `failed` | the platform gave up; `failed_reason` |

`agent.status(event_id)` raises `EventRefused` for a 4xx (an unknown
`event_id`, say) and `IgniUnavailable` otherwise.

### Subject, ExportSection

```py
class Subject(BaseModel):          # frozen
    user_id: str
    org_id: str
    email: str = ""
    name: str = ""
    member: Member | None = None

class ExportSection(BaseModel):
    name: str
    rows: list[dict[str, str | int | float | bool | None]] = []
```

A `Subject` is the person a privacy request is about, in the one
organisation it is about. `email`, `name` and `member` come from igni's
directory (present or former member) and are empty when the directory
cannot be asked; then erase by id. igni files each `ExportSection` under
your service's name.

### VM profiles and IgniApp

In Fleet every producer runs in a microVM of its own, built from a
**VM profile**: memory, vCPUs, idle time before a pause, its volume, and
the packages and setup script baked into its read-only layer. Those run
**as root** when the layer is built, so a VM runs nothing as root that an
org admin has not approved. An app or an extension that needs more asks,
and the request stays **pending** until an org admin of that organisation
approves it on the portal's *VM profiles* page.

```py
class VmPackages(BaseModel):             # unknown fields refused
    apt: list[str] = []                  # ≤ 200 each; one package name per entry
    pip: list[str] = []
    npm: list[str] = []

class VmProfileRequest(BaseModel):       # unknown fields refused; every field optional
    memory_mib: int | None = None            # 128 … 1 048 576: the most, its size at boot
    normal_memory_mib: int | None = None     # 128 … 1 048 576: what it normally has
    expected_memory_mib: int | None = None   # 128 … 1 048 576: for placing it
    vcpus: int | None = None                 # 1 … 256
    idle_before_pause_s: int | None = None   # ≥ 0; None set explicitly: never pause
    packages: VmPackages | None = None
    setup_script: str | None = None          # ≤ 65 536 chars; runs as root after the packages
    volume_gib: int | None = None            # ≥ 1
    volume_max_gib: int | None = None        # ≥ 1
    erase_after_idle_days: int | None = None # 1 … 3650
    internet: bool | None = None             # True asks for internet egress

    def body(self) -> dict[str, object]: ...  # the JSON sent: only the fields set
```

A package name is one word as its manager names it (`chromium`,
`requests==2.32.3`, `@playwright/mcp@0.0.84`), matching
`^[A-Za-z0-9@][A-Za-z0-9@/._+:=<>~^*!,-]{0,199}$`. A field left out takes
the deployment's Standard value. A nullable field set to `None` asks for
that explicitly.

```py
class VmProfileRequestRecord(BaseModel):
    id: str
    org_id: str
    subject: RequestSubject          # kind "app" or "extension", id, name
    state: Literal["pending", "approved", "rejected"]
    requested: RequestedVmProfile    # every value, Standard ones filled in: what would run
    version: str                     # changes whenever anything requested does
    packages_version: str            # changes whenever the packages or script do
    within_caps: bool                # False when it asks for more than the caps allow now
    requested_by: Requester
    requested_at: datetime
    decided_by: Decider | None       # kind, id, acting_as ("org_admin" or "super_admin")
    decided_at: datetime | None
    reason: str | None               # why it was rejected
    profile_id: str | None           # the profile an approval made
    is_pending: bool                 # properties
    is_approved: bool
    is_rejected: bool

class EffectiveVmProfile(BaseModel):  # what a VM gets: values clamped to the caps
    profile_id: str
    profile_name: str
    memory_mib: int
    normal_memory_mib: int
    expected_memory_mib: int | None
    vcpus: int
    idle_before_pause_s: int | None
    packages: VmPackages
    setup_script: str | None
    volume_max_gib: int
    erase_after_idle_days: int | None
    internet: bool

class AppVmProfile(EffectiveVmProfile):
    volume_gib: int                  # the app's volume

class ServiceVmProfile(BaseModel):   # host.extension_vm_profile()
    org_id: str
    extension_id: str | None         # None: no extension, or its manifest has no vm
    request: VmProfileRequestRecord | None
    profile: EffectiveVmProfile | None   # None until approved
    assigned: Assigned               # groups: int, apps: int
```

The same request sent again changes nothing and keeps its state. A
**changed** request is pending again, and the VM keeps the profile it has
until the admin approves the change. A request over the platform's caps,
or malformed, is refused with `VmProfileRefused` in igni's own words.

#### IgniApp

An **app** — a review bot, an integration — belongs to one organisation.
Its org admin registers it on the portal (*Apps*) by pasting its
**public** key. It is not a service: a service is the deployment's,
approved by a super admin, and serves every organisation.

```py
class IgniApp:
    def __init__(
        self,
        app_id: str,
        *,
        igni_server_url: str,
        key_store: KeyStore,
        http: httpx.AsyncClient | None = None,
        clock: Clock | None = None,
        timeout: float = 10.0,
    ) -> None: ...

    app_id: str
    vm_profile: AppVmProfiles

    async def public_jwks(self) -> JwkSet: ...
    async def thumbprint(self) -> str: ...
    async def token(self) -> str: ...
    async def request(self, method: str, path: str, *, json: object | None = None) -> httpx.Response: ...
    async def aclose(self) -> None: ...
    # also an async context manager: `async with IgniApp(...) as app:`
```

- The constructor raises `ConfigurationError` for an empty `app_id` or
  `igni_server_url`. The key is made on first use and kept in
  `key_store`, as a service's is.
- `public_jwks()` — the public key as a JWK set. Print
  `model_dump_json()` once for the org admin to paste.
- `thumbprint()` — the key's thumbprint, as the portal shows it.
- `token()` — the app's own token for igni (`token_use` `app`), renewed a
  minute before it expires. Raises `IgniUnavailable`, including while no
  org admin has registered this key.
- `request(method, path, json=)` — one call to igni server as the app; a
  401 is retried once with a new token, then raises `IgniUnavailable`.
- `vm_profile.request(wanted: VmProfileRequest) -> VmProfileRequestRecord`
  — ask for what the app's VM needs.
- `vm_profile.status() -> VmProfileRequestRecord | None` — the request
  and its state; `None` if the app never asked.
- `vm_profile.effective() -> AppVmProfile` — what the app's VM gets now:
  the approved profile, or the organisation's default.

The three `vm_profile` calls raise `VmProfileRefused` for a 4xx other than
429 and `IgniUnavailable` otherwise.

Nothing in this SDK can approve, reject, define or assign profiles: those
take an org admin's portal session, which no service or app token is.
Automation that holds an admin's credentials calls the portal API
directly.

### Key and session storage

The key is the deployment's identity, so every replica must use the same
one. Sessions for the service's own pages must be visible to every
replica, because igni's callback may land on any of them.

```py
class StoredKey(BaseModel):           # frozen
    kid: str                          # the thumbprint
    private_pem: str                  # unsealed

class KeyStore(Protocol):
    async def get(self) -> StoredKey | None: ...
    async def claim(self, key: StoredKey) -> StoredKey: ...

class KeyCipher:
    def __init__(self, key: str) -> None: ...
    @staticmethod
    def generate() -> str: ...
    def seal(self, plaintext: str) -> str: ...
    def open(self, sealed: str) -> str: ...

class MemoryKeyStore: ...             # KeyStore in this process; a restart is a new identity

class SqlKeyStore:                    # KeyStore in one row of igni_service_key
    def __init__(self, engine: AsyncEngine, cipher: KeyCipher, *, create_table: bool = True) -> None: ...
    engine: AsyncEngine
    metadata: MetaData                # IgniTables.metadata
    table: Table                      # IgniTables.service_key

class WebSession(BaseModel):          # frozen
    person: Person
    access_token: str
    refresh_token: str
    access_expires_at: float          # wall-clock seconds
    expires_at: float

class WebSessionStore(Protocol):
    async def get(self, session_id: str) -> WebSession | None: ...
    async def put(self, session_id: str, session: WebSession) -> None: ...
    async def delete(self, session_id: str) -> None: ...
    async def put_login(self, attempt: LoginAttempt) -> None: ...
    async def take_login(self, state: str) -> LoginAttempt | None: ...   # once only

class MemoryWebSessionStore:
    def __init__(self, *, clock: Clock | None = None) -> None: ...

class SqlWebSessionStore:
    def __init__(self, engine: AsyncEngine, cipher: KeyCipher, *,
                 create_table: bool = True, clock: Clock | None = None) -> None: ...

class IgniTables:
    metadata: MetaData                # the SDK's own MetaData
    service_key: Table                # "igni_service_key"
    web_session: Table                # "igni_web_session"
    web_login: Table                  # "igni_web_login"
```

- **`KeyStore`** is the whole contract for keeping a key: `get()` returns
  the kept key or `None`; `claim(key)` keeps `key` unless one is already
  kept, and returns whichever is kept. Two replicas that each made a key
  both call `claim`; one wins, and both sign with the winner's.
- **`KeyCipher(key)`** seals with Fernet under the key encryption key.
  `KeyCipher.generate()` makes a new key encryption key for an operator
  to keep. `seal` and `open` raise `KeyStoreError` when the key is not
  set, is not a Fernet key, or (for `open`) is not the key the data was
  sealed with.
- **`SqlKeyStore`** and **`SqlWebSessionStore`** keep rows sealed with the
  cipher. A session row is found by a SHA-256 of its cookie, so a copy of
  the table signs nobody in. Each creates its tables on first use, unless
  `create_table=False` because you own them in migrations.
- **`MemoryWebSessionStore`** is for tests and a single process.
- **`IgniTables`** holds the SDK's three tables on a `MetaData` of their
  own, so they never mix into your models.

### Errors

Every error the SDK raises on purpose is an `IgniError`. Below it, the
split is about what to do next.

| Exception | Parent | Raised when | What to do |
|---|---|---|---|
| `IgniError` | `Exception` | the root of everything below | one `except` for all |
| `IgniUnavailable` | `IgniError` | igni server could not be reached, refused, or answered with something else | try again later; nothing about the request was wrong |
| `ServiceNotApproved` | `IgniUnavailable` | a service token was refused because no super admin has approved the service yet | a super admin approves it in the portal (*Services*) after checking the thumbprint |
| `ServiceRevoked` | `IgniUnavailable` | a super admin revoked the service | ask a super admin |
| `NotificationRefused` | `IgniError` | igni read the notifications and said no; `.status`, `.detail` | fix the notifications; resending will not help |
| `EventRefused` | `IgniError` | igni read an event, message, upload or status request and said no; `.status`, `.detail` | check membership, the extension's grants, the item |
| `VmProfileRefused` | `IgniError` | igni read a VM profile request and said no (over the caps, malformed, not the caller's app); `.status`, `.detail` | change the request |
| `KeyStoreError` | `IgniError` | the service's key cannot be stored or read | an operator fixes the configuration |
| `BundleError` | `IgniError` | the extension bundle is unreadable, or cannot be built | fix the extension or the build |
| `ConfigurationError` | `IgniError` | the service was started without what it needs | set the environment |
| `TokenRefused` | `IgniError` | `person_of` / `caller_of`: the token is not acceptable; `.reason` | ask the caller for a new token |

`ServiceNotApproved` and `ServiceRevoked` are `IgniUnavailable`, so code
written for that still catches them. Which one is raised comes from the
registration's state, not from igni's wording
([how](#registration-and-approval)). `IgniUnavailable` is also what a
failed revocation check raises inside `person_of` when the revocations
are not fresh.

### The igni-service-bundle command

```text
igni-service-bundle [--extension DIR] [--out FILE] [--platform PLATFORM]...
                    [--allow-sdist NAME]... [--find-links DIR]... [--no-index]
                    [--no-build-isolation]
```

Builds the extension bundle the service uploads. `python -m
igni_service.bundle` is the same command. It needs `uv` and `pip` on the
machine that builds.

| Option | Default | Meaning |
|---|---|---|
| `--extension DIR` | `extension` | the extension's directory: `manifest.json`, `pyproject.toml`, and optionally `README.md`, `plugin/`, `ui/` |
| `--out FILE` | `extension-bundle.tar.gz` | the bundle to write; assets go to `<name>.assets/` beside it |
| `--platform P` | every platform | build wheels for `macos-arm64`, `linux-x86_64` or `windows-x86_64` only (repeatable) |
| `--allow-sdist NAME` | none | a dependency with no wheel that may be built from its sdist (repeatable) |
| `--find-links DIR` | none | another place to find packages (repeatable) |
| `--no-index` | off | use only `--find-links`, no package index |
| `--no-build-isolation` | off | build with this interpreter's packages instead of fetching build backends |

It exits 0 and prints what it wrote: the extension id and version, the
number of wheels, the size and SHA-256, and each asset. It prints any
notes (a tool the manifest does not list, a dependency built from its
sdist). On failure it prints `extension bundle: <reason>` to stderr and
exits 1. The same inputs give the same bytes.

What it checks and refuses is in
[Building and shipping the extension bundle](#building-and-shipping-the-extension-bundle).

### igni_service.testing

`igni_service.testing` plays igni server in-process, so a service can be
tested with no igni server and no network.

#### FakeIgni

```py
class FakeIgni:
    def __init__(
        self,
        *,
        clock: Clock | None = None,
        addresses: IgniAddresses | None = None,
        require_approval: bool = False,
    ) -> None: ...

    def service(self, settings: IgniSettings | None = None, *, key_store: KeyStore | None = None,
                clock: Clock | None = None,
                accepted_callers: Collection[CallerKind] = PEOPLE_ONLY) -> IgniService: ...
    def app(self, app_id: str, *, org_id: str, name: str = "") -> IgniApp: ...
    def settings(self, overrides: SettingsOverrides | None = None) -> IgniSettings: ...
    async def upload(self, bundle: str | Path | ExtensionBundle,
                     service: IgniService) -> HeldExtension: ...
    def transport(self) -> httpx.MockTransport: ...
    def http_client(self) -> httpx.AsyncClient: ...
    def reset(self) -> None: ...
    router: FakeRouter          # property
```

It is a real issuer in every way a service can observe: it holds an RSA
key and publishes the public half; it signs RS256 tokens with a `kid`;
its issuer (`https://igni.example.test`) is not the address it is reached
at (`http://igni.test`), as in a real deployment. It checks what igni
checks — client assertions, bundle signatures and digests, notification
limits — and records what it was sent.

- `FakeIgni(require_approval=False)` — by default the fake approves
  nothing and needs nothing approved: a registered service gets service
  tokens at once. With `require_approval=True`, service tokens raise
  `ServiceNotApproved` until the test calls `fake.clients.approve()`.
- `service(settings=None, ...)` — an `IgniService` wired to the fake:
  key in memory, registration and notification retries without waiting.
  Its `PUBLIC_BASE_URL` is `http://service.test` unless `settings` says
  otherwise.
- `app(app_id, org_id=..., name="")` — an `IgniApp` an org admin
  registered in `org_id`, approved by that act.
- `settings(SettingsOverrides(...))` — `IgniSettings` that reach the
  fake, with what you override (any `IgniSettings` field).
- `await upload(bundle, service)` — uploads an extension as the service
  does at start-up, signed, over the fake's wire, without a lifespan or a
  build. `bundle` is a built `extension-bundle.tar.gz`, or an extension's
  directory (its `manifest.json`, `README.md`, `plugin/` and `ui/` are
  archived as they are, with no wheelhouse). Returns the `HeldExtension`
  the fake now holds.
- `transport()` / `http_client()` — an `httpx` transport or client that
  reaches the fake.
- `reset()` — forget what happened and keep who exists, for a fake shared
  across a session. Requests, failures, grants, sign-ins, notifications,
  revocations, agent items and held uploads go; organisations, members,
  clients, keys and uploaded extensions stay.
- `router` — the pipeline every request the service sends goes through,
  as igni's router. `fake.router.handle(request)` answers one
  `httpx.Request`. It is made from the collaborators the fake holds when
  a request arrives, so a test that replaces one
  (`fake.traffic = RecordedTraffic()`) is heard on the wire.

`FakeIgni.BASE`, `FakeIgni.ISSUER` and `FakeIgni.SERVICE_URL` are the
three addresses; `fake.addresses` holds them for this fake
(`base_url`, `issuer`, `service_url`).

#### The fake's collaborators

Each part of igni server is an attribute a test talks to directly.

| Attribute | Use it to |
|---|---|
| `fake.directory` | `add_member(org_id, Member(...))`, `add_organisation(Organisation(...))`, `ensure(org_id)`, `member(org_id, identity)`, `is_member(org_id, user_id)`, `delete_organisation(org_id, igni_token)` (returns an `OrganisationDeletion`; `await deletion.send(http)` delivers it) |
| `fake.clients` | `approve(client_id=None)` and `revoke(client_id=None)` play a super admin (every client when no id); `registration` is the one registered client; `clients` all of them |
| `fake.signer` | `person_token(user_id, *, org_id, overrides=None)`, `app_token(app_id, *, org_id, name="", overrides=None)`, `space_token(space_id, SpaceClaims(org=..., app=..., external_id=...), overrides=None)`, `igni_token(org_id, overrides=None)`; `keys.rotate()` |
| `fake.oauth` | `grants` (each grant type asked for), `revoked` (refresh tokens revoked at sign-out), `sign_ins.authorize(location, *, user_id, org_id)` plays the portal signing somebody in (raises `PortalRefused` for what the portal would refuse); `verifier.names_client_state = False` plays an igni server that refuses a pending or revoked service without `client_state` |
| `fake.extensions` | `hold(reason)` holds every new version from an approved service; `release()`; `shipped(client_id)` is what devices receive; `latest(client_id)` the last upload, held or not; `held`, `assets` |
| `fake.notifications` | `calls` (each `NotifyCall` as sent), `deliveries` (each `Delivery`: `org_id`, `user_id`, `source`, `notification`) |
| `fake.revocations` | `publish(subject_id, *, org_id, kind=RevokedKind.PERSON, reason="removed")`: `org_id=None` is every organisation; `RevokedKind` is in `igni_service.revocations` |
| `fake.traffic` | `seen` (every request), `requests_to(path)`, `fail(path_prefix, status)` and `heal()` play igni failing |
| `fake.agents` | `items` (every `SentEvent`: events, messages, chats, actions), `uploads`, `settle(event_id, state)` plays the producer's igni, `grants = {"messages"}` plays an extension that declares less |
| `fake.vm_profiles` | `approve(org_id, VmProfileSubject.app(app_id), by="u-admin")`, `reject(org_id, subject, reason=None)`, `request(org_id, subject)`, `assign(org_id, profile_id, groups=0, apps=0)`, `caps` (a `FakeCaps`) |

`TokenOverrides` bends a token a test signs: `aud`, `iss`, `use`, `sub`,
`org`, `kid`, `key` and `lifetime` (seconds or a `timedelta`). For
example `fake.signer.person_token("u-ada", org_id="org-1",
overrides=TokenOverrides(lifetime=-1))` is an expired token.

`fake.vm_profiles.approve` and `reject` raise `NoVmProfileRequest` (a
`LookupError`) when the request does not exist yet. An app's exists once
it asked (`app.vm_profile.request`); an extension's once its bundle is on
the fake (`await fake.upload(bundle, igni)`) and the service asked after
it (`await igni.host(org_id).extension_vm_profile()`).

#### Other names in igni_service.testing

| Name | What |
|---|---|
| `ManualClock(start=1_800_000_000.0)` | a clock that moves only with `advance(seconds)`; pass it as `FakeIgni(clock=...)` |
| `SettingsOverrides` | the fields of `IgniSettings`, for `fake.settings(...)` |
| `IgniAddresses` | the fake's three addresses |
| `IgniPaths` | igni server's paths, e.g. `IgniPaths.NOTIFICATIONS`, for `fake.traffic.fail` |
| `PersonClaims`, `SpaceClaims`, `TokenOverrides` | claims and overrides for `fake.signer` |
| `VmProfileSubject` | `VmProfileSubject.app(app_id)` or `VmProfileSubject.extension(extension_id)` |
| `NoVmProfileRequest` | see above |
| `PortalRefused` | raised by `fake.oauth.sign_ins.authorize` |
| `OrganisationDeletion` | the call igni owes after `delete_organisation` |
| `HeldExtension` | what the fake holds for a client: `extension_id`, `version`, `sha256`, `manifest`, `pages` |
| `BundleArchive` | `BundleArchive.write(staging, out)` writes a stand-in bundle archive |
| `FakeAgents`, `SentEvent` | the agent channel and one item in it |
| `FakeVmProfiles`, `FakeCaps` | VM profiles, and the platform's caps (`max_memory_mib=8192`, `max_vcpus=4`, …) |
| `Delivery`, `NotifyCall` | what `fake.notifications` records |
| `SeenRequest` | one request the fake saw: `method`, `path`, `headers`, `body`, `query` |

## Guides

### Deploying

#### Environment

```bash
export IGNI_SERVER_URL=https://igni.bank.internal         # where the service reaches igni server
export PUBLIC_BASE_URL=https://notes.bank.internal        # this service, on a hostname of its own
export SERVICE_NAME="Notes"                               # its name in igni's portal
export IGNI_KEY_DATABASE_URL=postgresql+asyncpg://notes@db/notes
export IGNI_EXTENSION_BUNDLE=/app/extension-bundle.tar.gz
# Once, and keep it safe: a new key encryption key is a new identity, approved again.
export IGNI_KEY_ENCRYPTION_KEY=$(python -c "from igni_service import KeyCipher; print(KeyCipher.generate())")
uvicorn --factory service:create_app --host 0.0.0.0 --port 8000
```

Every variable is in [IgniSettings](#ignisettings).

- **`PUBLIC_BASE_URL` is the service's identity.** It is the audience of
  every token people bring. Give the service a hostname of its own, and
  do not change it: a token for another URL is refused.
- **`IGNI_KEY_ENCRYPTION_KEY` must not change.** The key and sessions are
  sealed with it. Changing it means the stored key cannot be read; a new
  key is a new identity that a super admin must approve again.
- **The image carries the bundle.** Copy `extension-bundle.tar.gz` and
  `extension-bundle.assets/` into the image together, and point
  `IGNI_EXTENSION_BUNDLE` at the archive.
- **Several replicas** need a shared database in `IGNI_KEY_DATABASE_URL`.
  They agree on one key, and every replica sees every sign-in session.

#### Where the key and sessions are kept

`IgniService.from_settings` keeps both in `IGNI_KEY_DATABASE_URL`, in the
SDK's own tables (`igni_service_key`, `igni_web_session`,
`igni_web_login`), created on first use. Rows are sealed with the key
encryption key.

To keep them in the service's own database instead, hand the stores over:

```python
from sqlalchemy.ext.asyncio import create_async_engine

from igni_service import IgniService, IgniSettings, KeyCipher, SqlKeyStore, SqlWebSessionStore

engine = create_async_engine("sqlite+aiosqlite:///service.db")  # the service's own database
cipher = KeyCipher(KeyCipher.generate())  # in production: KeyCipher(IGNI_KEY_ENCRYPTION_KEY)
igni = IgniService(
    IgniSettings(
        igni_server_url="https://igni.bank.internal",
        public_base_url="https://notes.bank.internal",
        service_name="Notes",
    ),
    key_store=SqlKeyStore(engine, cipher),
    web_store=SqlWebSessionStore(engine, cipher),
)
```

A service that owns its schema in Alembic adds `IgniTables.metadata` to
`target_metadata` (`[Base.metadata, IgniTables.metadata]`) and passes
`create_table=False` to both stores. Any other place to keep them is a
`KeyStore` or `WebSessionStore`: small protocols in this package.

#### Logging

The SDK logs under the `igni_service` logger. Under uvicorn,
`igni.lifespan` makes its lines visible (INFO and up, on stderr) unless
you configure logging yourself. Lines worth watching: the identity
banner, `uploaded extension …`, `… is held for a super admin …`,
`refused a token: …` (INFO), `cannot check a token: …` (ERROR) and
`registration failed (…); retrying in …s` (ERROR).

### Building and shipping the extension bundle

#### The extension's directory

```text
extension/
  manifest.json      # id, version, python packaging, permissions, pages
  pyproject.toml     # the extension's Python package
  README.md          # optional
  plugin/            # optional: agents, skills
  ui/                # optional: the page
  src/...            # the package's code; travels inside its wheel
```

The manifest must name an `id`, a `version` and the `python` packaging:
`package` is the name `pyproject.toml` builds, and `entry` a console
script it declares under `[project.scripts]`. For example:

```json
{
  "id": "acme.tickets",
  "version": "0.2.0",
  "name": "Ticket lookup",
  "python": { "package": "acme-tickets-extension", "entry": "acme-tickets-extension" },
  "permissions": {
    "service": ["messages"],
    "hooks": ["PostToolUse"]
  },
  "contributes": { "pages": [{ "kind": "acme.tickets", "label": "Tickets", "sidebar": true }] }
}
```

The full manifest is described in
[Your first extension](https://github.com/ignite-ember/igni-sdk/blob/main/docs/YOUR_FIRST_EXTENSION.md).

#### Build it

```bash
igni-service-bundle --extension extension --out extension-bundle.tar.gz
```

The bundle holds `manifest.json`, `README.md`, `plugin/`, `ui/`, and a
wheelhouse (`wheels/` unless the manifest's `python.wheels` says
otherwise) with the extension's wheel and every dependency's, for CPython
3.12 on macOS 26 and later (arm64), Linux x86_64 and Windows x86_64.
Every dependency is pinned by hash, so a same-named package published
elsewhere cannot slip in. A wheel a `--find-links` directory already holds
is taken from there, when its bytes are the ones the resolution pinned: an
index serving another build of the same version is then not consulted for
it, and the build does not stop on the two not matching. Tests and caches
are left out.

The build stops (exit 1) when:

- `manifest.json` or `pyproject.toml` is missing or unreadable;
- the manifest's `python.package` is not what `pyproject.toml` builds, or
  its `python.entry` is not one of `[project.scripts]`;
- a tool in `permissions.tools` leaves out one of the four hints;
- a dependency has no usable wheel for a platform (by name and platform);
- an asset cannot be fetched, or its bytes do not match the pinned size
  and SHA-256;
- the manifest declares `permissions.hooks` and an `endpoint` (only a
  process igni starts is asked about hooks).

#### Tools and their hints

Every tool in the manifest's `permissions.tools` states MCP's four hints
(`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`).
igni's permission modes decide on them, and igni server refuses a bundle
that leaves one out, so the builder refuses it first.

**State the hints once, in the code.** An extension written with
`igni-extension` already states them on every `@ext.tool(hints=...)`.
Leave `permissions.tools` out of `manifest.json` and the builder writes it
into the bundle's manifest from the code (it runs `python -m
igni_extension.manifest` on the extension, offline, from the wheelhouse
it just built); your own file is left as it is. A manifest that does list
them is checked against the code instead: a listed tool the code does not
register, or a hint that differs, stops the build. A tool the code
registers and the manifest does not list is said in a note: it is not
offered to the agent, which is what you want for a tool only the
extension's page calls.

#### Assets

An extension that runs a database, a JVM or a model ships it as an
**asset**, declared in the manifest:

```json
"assets": [
  {"name": "neo4j", "platform": "any",
   "file": "neo4j-community-5.26.0-unix.tar.gz",
   "size": 158822080, "sha256": "<64 hex digits>",
   "source": "https://dist.neo4j.org/neo4j-community-5.26.0-unix.tar.gz",
   "unpack": true}
]
```

- `name`: lower-case letters, digits and `-`, up to 64 characters.
- `platform`: `any`, or one entry per platform — `macos-arm64`,
  `linux-x86_64` **and** `windows-x86_64`, all three.
- `file`: a plain file name. `size`: at most 1 GiB. `sha256`: the pinned
  digest. `source`: an `https://` URL the builder fetches from.
- `unpack`: `true` to have igni unpack a `.tar.gz`, `.tgz` or `.zip`.

The builder fetches each into `extension-bundle.assets/<sha256>` beside
the archive, refuses bytes that are not the pinned ones, and keeps one
already there. The service uploads each asset igni does not hold yet,
signed, before the bundle. A device downloads only its own platform's.
igni lays them out read-only for the extension's process (`ext.assets` in
`igni-extension`).

#### Size

The wheelhouse carries every dependency for all three platforms. For an
extension on `igni-extension` that is about 30 MB, nearly all of it the
MCP SDK's own dependencies three times over (`cryptography`,
`pydantic-core`, `pywin32`). `--platform linux-x86_64` (repeatable)
builds for some platforms only — about 10 MB for Linux alone. A device on
any other platform then cannot install it, so use this only when every
device in the deployment is on those platforms.

#### Dependencies with no wheel

A dependency with no usable wheel stops the build, naming it and the
platform. One that is pure Python and publishes only an sdist can be
declared in the extension's `pyproject.toml` and is then built from its
sdist (the result must be a pure-Python wheel):

```toml
[tool.igni.bundle]
sdist-only = ["wikipedia"]
```

`--allow-sdist wikipedia` on the command line does the same.

#### A build machine with no internet

Point the builder at a local mirror or a directory of wheels:
`--find-links ./wheels --no-index`. The igni SDK wheels are attached to
each GitHub release (`sdk-v<version>`) for this.

#### Shipping a new version

Bump `version` in `manifest.json` and `pyproject.toml`, build again, and
restart the service with the new bundle. It uploads it because igni
server holds different bytes. Devices install it at their next sync. A
version that asks for more than the approved one (a new tool, a wider
grant) is **held**: the service logs a warning with igni's reason, and
devices keep the approved version until a super admin approves the new
one in the portal (*Services*).

### Who is calling: routes, WebSockets and the extension's page

A route that serves the extension takes the person from their token:

```python
import json

from fastapi import Depends, FastAPI, WebSocket

from igni_service import IgniError, Person, TokenRefused
from igni_service.testing import FakeIgni

igni = FakeIgni().service()     # in production: IgniService.from_settings(IgniSettings())
app = FastAPI(lifespan=igni.lifespan)
igni.install(app)


@app.get("/v1/me")
async def me(person: Person = Depends(igni.person)) -> dict[str, str]:
    return {"id": person.user_id, "org": person.org_id, "name": person.display_name}


@app.get("/v1/public/{slug}")
async def public(slug: str, reader: Person | None = Depends(igni.optional_person)) -> dict[str, str]:
    # Everybody may read it; somebody signed in also sees their own notes.
    return {"slug": slug, "reader": reader.user_id if reader else ""}


@app.delete("/v1/org/data")
async def wipe(admin: Person = Depends(igni.org_admin)) -> None:
    ...  # only an admin of the organisation the token is for gets here


@app.websocket("/v1/rooms/{room}")
async def room(socket: WebSocket, room: str) -> None:
    """A socket from the extension's page proves itself with its token in the first frame."""
    await socket.accept()
    # `bridge.service.websocket` sends {"type": "auth", "token": …} first, unless
    # the page passes its own `authFrame`.
    first = json.loads(await socket.receive_text())
    try:
        person = await igni.person_of(str(first.get("token", "")))
    except TokenRefused as refused:
        await socket.close(code=4401, reason=refused.reason)
        return
    except IgniError:
        await socket.close(code=1013)  # try again later
        return
    await socket.send_text(f"hello {person.display_name}")
```

The extension's process sends `Authorization: Bearer` on its own
(`ext.service` in `igni-extension`). The page does too, through
`bridge.service.fetch`. Because the page calls from igni's origin, every
route above that depends on `igni.person`, `igni.optional_person`,
`igni.org_admin` or `igni.caller` answers it cross-origin
([BearerCors](#bearercors-calls-from-the-extensions-page)). A route that
needs a token but should treat an unusable one as anonymous takes
`Depends(igni.token)` and calls `person_of` itself.

#### Sign-in to the service's own pages

For pages people open in a browser (settings, an admin console), use
`igni.web`. A page links to `igni.web.login_path` and posts to
`igni.web.logout_path`; the quick start's `/settings`, `/admin` and
`/organisation/settings` routes show the three dependencies. The
[testing guide](#testing-sign-in-to-the-services-own-pages) signs somebody
in end to end.

### Apps and their spaces as callers

An app — and each of its end users, a **space** — can call a service too,
with a token igni exchanged for the service's URL (`token_use` `app` or
`space`). A service takes people only unless it says more:

```python
from fastapi import Depends, FastAPI

from igni_service import (
    App, Caller, CallerKind, IgniService, IgniSettings, MemoryKeyStore, Person, Space,
)

igni = IgniService(
    IgniSettings(
        igni_server_url="https://igni.bank.internal",
        public_base_url="https://notes.bank.internal",
        service_name="Notes",
    ),
    key_store=MemoryKeyStore(),
    accepted_callers={CallerKind.PERSON, CallerKind.APP, CallerKind.SPACE},
)
app = FastAPI(lifespan=igni.lifespan)


@app.get("/v1/notes")
async def notes(caller: Caller = Depends(igni.caller)) -> list[str]:
    match caller:
        case Person(user_id=user_id):
            return [f"notes of {user_id}"]
        case App(app_id=app_id):
            return [f"notes the app {app_id} keeps"]
        case Space(app_id=app_id, external_id=user):
            return [f"notes of {user} in {app_id}"]
    return []
```

`Depends(igni.caller)` answers a typed `Person`, `App` or `Space` for the
kinds the service accepts, and a 401 for any other. `igni.person` stays
people only whatever the service accepts. A route on `igni.caller` is a
bearer route, so the extension's page calls it with
`bridge.service.fetch` like any other
([BearerCors](#bearercors-calls-from-the-extensions-page)).
`igni.caller_of(token)` is the same outside a request. In a test:

```python
import httpx
from fastapi import Depends, FastAPI

from igni_service import Caller, CallerKind
from igni_service.testing import FakeIgni, SpaceClaims

fake = FakeIgni()
igni = fake.service(accepted_callers={CallerKind.PERSON, CallerKind.APP, CallerKind.SPACE})
app = FastAPI()
igni.install(app)


@app.get("/v1/whoami")
async def whoami(caller: Caller = Depends(igni.caller)) -> dict[str, str]:
    return {"kind": caller.kind.value, "org": caller.org_id}


tokens = {
    "person": fake.signer.person_token("u-ada", org_id="org-1"),
    "app": fake.signer.app_token("app-bot", org_id="org-1"),
    "space": fake.signer.space_token(
        "sp-42", SpaceClaims(org="org-1", app="app-bot", external_id="customer-42")
    ),
}
transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url=fake.addresses.service_url) as http:
    for kind, token in tokens.items():
        answer = await http.get("/v1/whoami", headers={"Authorization": f"Bearer {token}"})
        assert answer.json() == {"kind": kind, "org": "org-1"}
```

### Telling people: notifications and the directory

```python
from igni_service import IgniError, Member, Notification, Target
from igni_service.testing import FakeIgni

fake = FakeIgni()
for user_id, email in [("u-ada", "ada@acme.test"), ("u-max", "max@acme.test")]:
    fake.directory.add_member("org-1", Member(user_id=user_id, email=email, name=user_id[2:].title()))
igni = fake.service()
host = igni.host("org-1")

# Who is "max@acme.test"? Keyed by user id and address, casefolded.
found = await host.directory.resolve(["MAX@acme.test", "nobody@acme.test"])
max_ = found["max@acme.test"]
assert max_.user_id == "u-max" and "nobody@acme.test" not in found

people = await host.directory.members(query="ad")      # prefix search on address or name
assert [p.user_id for p in people] == ["u-ada"]
assert await host.directory.person("u-never") is None  # never a member

# Tell Max (and Ada, who did it, is never told about her own act).
notice = Notification(
    kind="access_requested",
    title="Runbook",
    body="Ada asked for access",
    actor="u-ada",
    target=Target(page="acme.example", params={"doc": "runbook"}),
    event_key="access:runbook:u-ada",
    recipients=["u-ada", max_.user_id],
)
assert (await host.notify(notice)).delivered == 1
assert (await host.notify(notice)).delivered == 0       # the same event_key: told once

# Best effort: a notification must never fail the request that caused it.
try:
    await host.notify(notice)
except IgniError as exc:
    print("could not notify:", exc)
```

The `target` names one of your extension's pages; igni opens it, with its
`params`, when the person clicks the notification. To tell only the
person at one device, from the extension itself, use
`ext.host.notifications.notify` in `igni-extension`.

`host.directory.organisation()` returns the organisation, with
`tenant_number` to derive per-organisation database or index names from.

### Reaching a producer's agent

A service reaches a producer's igni — on their device, or in their Fleet
VM, woken for it — through igni server. See
[Messages and events](#messages-and-events) for which to use.

```python
from igni_service import Attachment, Member, Producer
from igni_service.testing import FakeIgni

fake = FakeIgni()  # igni, in-process: what a service holds in production is its IgniService
fake.directory.add_member("org-1", Member(user_id="u-marieke", email="marieke@acme.test"))
igni, org_id = fake.service(), "org-1"
pdf = b"%PDF-1.7 the claim form"
with open("damage.jpg", "wb") as photo:
    photo.write(b"\xff\xd8\xff a photo")

agent = igni.host(org_id).agent(Producer.person("u-marieke"))

# A message: posted as sent, in the chat of its thread.
await agent.send_message(
    "Claim CL-20431 arrived; assess the damage.",
    attachments=[Attachment.from_path("damage.jpg"), Attachment.from_bytes("form.pdf", pdf)],
    thread="claim:CL-20431",
    event_key="claim:CL-20431:new",
)

# A chat of its own, and what can be done in it.
chat = await agent.new_chat("Claim CL-20431", thread="claim:CL-20431")
await chat.send_message("The adjuster replied: see the report.")
await chat.queue("When you get to it, check the invoice.")     # the next run; starts nothing
await chat.show(                                                 # json-render; never sent to the model
    {"root": "r", "elements": {"r": {"type": "Text", "props": {"text": "Paid."}}}}
)
await chat.rename("Claim CL-20431 (paid)")
await chat.cancel()                                              # a working run; never one waiting on an approval

# An event: the extension's to act on.
accepted = await agent.send_event("index.ready", {"repo": "acme/api"})
status = await agent.status(accepted.event_id)   # pending, delivered, not_handled, expired, dropped, failed
assert status.state == "pending"
```

On the extension's side, the event arrives at its handler:

```py
@ext.on_service_event("index.ready")          # igni-extension
async def index_ready(event: ServiceEvent) -> None: ...
```

- **Threads.** The first item of a thread opens a chat for it in the
  producer's igni (titled by `title`, else `"<extension>: <thread>"`), and
  every later one goes there. A message without a thread goes to your
  extension's own chat.
- **Retries.** Every send returns an `EventAccepted` with its `event_id`.
  The same `event_key` for one producer is stored once, so a retry with
  one is exact.
- **Events not handled.** An event with no handler for its type, one that
  reaches no running extension, or one whose handler raises reads
  `not_handled`, with the reason, when you poll its status.

What a service can do in a chat, against what igni can:

| In igni | From a service | Why not, where not |
|---|---|---|
| Post a message that starts or resumes a run | yes, `send_message` | |
| Queue a message for the next turn | yes, `chat.queue` | |
| Attach files | yes, any type, 5 MiB each | |
| Open a new chat, with a title | yes, `new_chat` | one per thread |
| Rename a chat | its own chats only | a person's chats are theirs to name |
| Show a view in the chat | yes, `chat.show`, its own chats | |
| Replace a view | not yet | show a new one |
| Cancel the run | its own chats, and not a run waiting on an approval | stopping that run would decide the approval |
| Cancel a sub-agent | no | its run ids never leave igni |
| Answer an approval, approve or dismiss a plan | **never** | a decision that is a person's |
| Read the chat, search it, its status or context | no | a service gets an item's status, not the chat's content |
| Truncate, compact, discard an interrupted run, extract learnings | no | they rewrite a person's history or memory |
| Open a chat on screen, move the UI | no | a service never moves what a person sees; it notifies |
| Switch model or permission mode, run a slash command | no | each changes what the agent may do |
| Post into a chat it did not open | no | its extension may, through its own host calls |

### Erasure, export and a deleted organisation

igni server calls the service about one person, or one organisation, with
a token it signs for this service (`token_use` `igni`, the organisation
in `org`). `igni.router`, mounted by `igni.install(app)`, answers:

| igni calls | Your handler | Answer |
|---|---|---|
| `DELETE /v1/igni/subjects/{user_id}` | `@igni.on_erase` | 204, whether or not anything was there |
| `GET /v1/igni/subjects/{user_id}/export` | `@igni.on_export` | 200, `{"sections": [{"name": …, "rows": [{…}]}]}` |
| `DELETE /v1/igni/organisations/{org_id}` | `@igni.on_organisation_deleted` | 204 |

Without a handler the route answers 501, which igni reports as
unconfirmed under the service's name and keeps asking. A service that
holds nothing about anybody says so with a handler that does nothing,
rather than by forgetting.

Rules for the handlers:

- **Erasure is idempotent.** igni repeats it until every service
  confirms. Erase by `user_id` even when `email` is empty.
- **Export is per organisation.** Return only what you hold about the
  person in `subject.org_id`.
- **A deleted organisation** is told until the service confirms, so a
  service that was down hears about it when it is back. A token for one
  organisation is refused (403) for another's path.

The quick start shows erasure and export. A deleted organisation:

```python
import httpx
from fastapi import FastAPI

from igni_service.testing import FakeIgni

fake = FakeIgni()
fake.directory.ensure("org-1")
igni = fake.service()
app = FastAPI()
igni.install(app)

routed: dict[str, str] = {"org-1": "db-1"}


@igni.on_organisation_deleted
async def organisation_deleted(org_id: str) -> None:
    routed.pop(org_id, None)  # stop routing to its data; idempotent


deletion = fake.directory.delete_organisation("org-1", fake.signer.igni_token("org-1"))
transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url=fake.addresses.service_url) as http:
    assert (await deletion.send(http)).status_code == 204
    assert (await deletion.send(http)).status_code == 204   # again: still fine
assert routed == {}
```

### What a VM needs: VM profile requests

> **Which call answers what.** An app: `app.vm_profile.request(wanted)`
> asks, `app.vm_profile.status()` says what became of the request
> (`pending`, `approved`, `rejected` with a reason), and
> `app.vm_profile.effective()` is what its VM gets now. A service:
> `igni.host(org_id).extension_vm_profile()` is what became of its
> extension's request in that organisation. The older
> `host.vm_profile()` still works and raises a `DeprecationWarning`
> naming the new call.

| Who asks | How | What approval does |
|---|---|---|
| an **app**, as itself | `app.vm_profile.request(...)`, with the app's own token | makes a profile from the request and assigns it to the app (its spaces' VMs get it too) |
| an **extension** | its manifest's `vm` section | makes a profile from the request, which the admin gives to the groups and apps that use the extension |

A service is not an app: a service token names a service and an
organisation, never an app, so a service cannot ask for an app's VM.

#### An extension asking

The extension's manifest asks, in camelCase:

```json
"vm": { "memoryMib": 2048, "packages": { "apt": ["jq"] } }
```

The service reads what became of it in each organisation:

```python
import json
from pathlib import Path

from igni_service.testing import FakeIgni, VmProfileSubject

fake = FakeIgni()
igni = fake.service()

extension = Path("extension")
extension.mkdir()
(extension / "manifest.json").write_text(
    json.dumps({"id": "acme.example", "version": "1.0.0", "vm": {"memoryMib": 2048, "packages": {"apt": ["jq"]}}})
)
await fake.upload(extension, igni)   # what the lifespan does at start-up

answer = await igni.host("org-1").extension_vm_profile()
assert answer.request is not None and answer.request.is_pending

fake.vm_profiles.approve("org-1", VmProfileSubject.extension("acme.example"))   # the org admin
answer = await igni.host("org-1").extension_vm_profile()
assert answer.request is not None and answer.request.is_approved
assert answer.profile is not None and answer.profile.packages.apt == ["jq"]
```

#### An app asking

An org admin registers the app on the portal (*Apps*) by pasting the
app's **public** key; the private half never leaves the app.

```python
from igni_service import IgniApp, MemoryKeyStore, VmPackages, VmProfileRequest
from igni_service.testing import FakeIgni, VmProfileSubject

fake = FakeIgni()  # igni, in-process, for this example; below, what production writes
APP_ID = "app-review-bot"
app = fake.app(APP_ID, org_id="org-1")
# In production:
#   app = IgniApp(APP_ID, igni_server_url="https://igni.bank.internal", key_store=store)

async with app:
    print((await app.public_jwks()).model_dump_json())  # once, for the admin to paste
    record = await app.vm_profile.request(VmProfileRequest(packages=VmPackages(apt=["jq"])))
    assert record.state == "pending"
    assert (await app.vm_profile.effective()).profile_name == "Standard"  # until approved

    fake.vm_profiles.approve("org-1", VmProfileSubject.app(APP_ID))  # the org admin
    status = await app.vm_profile.status()
    assert status is not None and status.state == "approved"
    assert (await app.vm_profile.effective()).packages.apt == ["jq"]
```

`store` is any `KeyStore` — `SqlKeyStore` on the app's own database, as a
service's.

#### Worked example: a headless browser (Chromium + Playwright MCP)

Playwright normally **downloads Chromium from the internet** (`npx
playwright install chromium`, or when a launch finds none). An
air-gapped installation cannot: the browser must come from **inside the
network**. Installing the npm packages downloads no browser (neither
`@playwright/mcp` nor `playwright` has an install script), so the
request below brings Chromium itself and never runs `playwright install`.

Where Chromium comes from is the part to get right. Fleet's VMs run
Ubuntu 24.04 (noble), and there `apt` `chromium` and `chromium-browser`
are only transitional packages for the **snap**, which does not work in
the chroot the layer is built in, nor in a Firecracker VM; Ubuntu's
archive has no real Chromium `.deb`. So either the organisation's mirror
carries a real Chromium `.deb` (then name it under `apt`), or — as below
— the setup script places a Playwright Chromium build
(`chrome-linux.zip`) from inside the network.

How Fleet builds the layer: the `apt` packages from the customer's
mirror, with `--no-install-recommends` (and `nodejs npm` added when there
are npm packages); pip and npm through the mirror or offline caches; then
the setup script as root in the chroot, with only `APT_MIRROR` in its
environment. A strict air-gapped build (`OFFLINE=1`) runs all of it with
no network at all, so the script can only read files — such as a
`file://` mirror directory, which is mounted at the same path.

```python
from igni_service import VmPackages, VmProfileRequest

# Runs as root in the layer's chroot, after the packages. Chromium comes
# from inside the network — never from Playwright's CDN.
SETUP = r"""#!/bin/sh
set -eu
case "${APT_MIRROR:-}" in
  file://*)  # an offline mirror directory: the only way under OFFLINE=1
    archive="${APT_MIRROR#file://}/playwright/chrome-linux.zip" ;;
  *)         # the bank's own artefact store
    archive=/tmp/chrome-linux.zip
    curl -fsSL -o "$archive" https://artifacts.bank.internal/playwright/chrome-linux.zip ;;
esac
mkdir -p /opt/chromium
unzip -q -o "$archive" -d /opt/chromium
# Where Playwright MCP's default channel, chrome, looks for the browser.
mkdir -p /opt/google/chrome
ln -sf /opt/chromium/chrome-linux/chrome /opt/google/chrome/chrome
"""

BROWSER = VmProfileRequest(
    memory_mib=4096,           # Chromium peaks well above igni's own needs
    normal_memory_mib=2048,
    vcpus=2,
    packages=VmPackages(
        # From the bank's Ubuntu mirror: what Chromium needs to run, and
        # what the setup script needs to place it.
        apt=[
            "fonts-liberation", "libnss3", "libatk-bridge2.0-0t64", "libgbm1",
            "libasound2t64", "libxkbcommon0", "libxcomposite1", "libxdamage1",
            "libxrandr2", "libpango-1.0-0", "libcups2t64",
            "ca-certificates", "curl", "unzip",
        ],
        # From the bank's npm mirror. Pinned: the admin approves this version.
        npm=["@playwright/mcp@0.0.84"],
    ),
    setup_script=SETUP,
)
```

An app sends it with `await app.vm_profile.request(BROWSER)`.

The agent then runs Playwright MCP as `playwright-mcp --headless
--isolated` (stdio). The flags are Playwright MCP's own: `--headless` is
required — it runs headed by default and the VM has no display;
`--isolated` keeps the browser profile in memory; add `--no-sandbox` if
the agent runs as root. Instead of the symlink, `--executable-path
/opt/chromium/chrome-linux/chrome` (or `PLAYWRIGHT_MCP_EXECUTABLE_PATH`)
names the browser directly. Replace `artifacts.bank.internal` with the
organisation's own store; the admin reviewing the request sees that URL.
An extension asks for the same in its manifest:

```json
"vm": {
  "packages": {"apt": ["fonts-liberation", "libnss3", "…", "unzip"], "npm": ["@playwright/mcp@0.0.84"]},
  "setupScript": "#!/bin/sh\nset -eu\n…",
  "memoryMib": 4096,
  "normalMemoryMib": 2048,
  "vcpus": 2
}
```

#### No admin calls here

This SDK cannot approve, reject, define or assign profiles, and has no
helper for those portal calls: they take an org admin's portal session
(`/v1/portal/...`), and neither a service token nor an app token is one —
nor is a person's token for a service, whose audience is the service's
URL, not igni's.

### Handling errors

Decide by the exception's class, not its message:

```python
from igni_service import (
    EventRefused, IgniError, IgniUnavailable, Member, Notification, NotificationRefused,
    Producer, ServiceNotApproved, ServiceRevoked,
)
from igni_service.testing import FakeIgni, IgniPaths

# A deployment whose super admin has not approved this service yet.
fake = FakeIgni(require_approval=True)
fake.directory.add_member("org-1", Member(user_id="u-ada", email="ada@acme.test"))
igni = fake.service()
host = igni.host("org-1")

try:
    await host.directory.members()
except ServiceNotApproved as exc:
    print(exc)          # says what to do: approve in igni's portal, under Services
except ServiceRevoked:
    print("a super admin revoked this service")
except IgniUnavailable:
    print("igni server is away; try later")

fake.clients.approve()  # the super admin approves
assert [m.user_id for m in await host.directory.members()] == ["u-ada"]

# igni failing: retried three times, then IgniUnavailable.
fake.traffic.fail(IgniPaths.NOTIFICATIONS, 503)
notice = Notification(kind="comment", title="Runbook", recipients=["u-ada"])
try:
    await host.notify(notice)
except IgniUnavailable:
    print("try again later")
fake.traffic.heal()

# igni refusing: not retried, and resending will not help.
fake.traffic.fail(IgniPaths.NOTIFICATIONS, 400)
try:
    await host.notify(notice)
except NotificationRefused as refused:
    print(refused.status, refused.detail)
fake.traffic.heal()

# An extension that does not declare service.chats cannot be sent a thread.
fake.agents.grants = {"messages"}
try:
    await host.agent(Producer.person("u-ada")).send_message("Hello", thread="t-1")
except EventRefused as refused:
    assert refused.status == 403

# Everything at once, when it is best effort for you:
try:
    await host.notify(notice)
except IgniError as exc:
    print("not notified:", exc)
```

In routes, the caller dependencies turn token problems into 401, 403 and
503 for you. Calls you make to igni (`notify`, `directory`, `agent`) raise
exceptions; turn them into whatever answer suits your API. A common
choice: `IgniUnavailable` → 503, `EventRefused` and `NotificationRefused`
→ log and carry on, or 502.

### Testing a service

`FakeIgni` plays igni server in-process; `fake.service()` is an
`IgniService` wired to it. Test the app with `httpx.ASGITransport`, and
sign tokens with `fake.signer`:

| What the test plays | Call |
|---|---|
| the extension calling as a person | `fake.signer.person_token(user_id, org_id=...)` |
| an app or a space calling | `fake.signer.app_token(...)`, `fake.signer.space_token(...)` |
| igni calling for erasure, export, a deleted organisation | `fake.signer.igni_token(org_id)` |
| an expired or foreign token | `overrides=TokenOverrides(lifetime=-1)`, `TokenOverrides(aud="https://other.test")` |
| a super admin approving or revoking | `FakeIgni(require_approval=True)`, `fake.clients.approve()`, `fake.clients.revoke()` |
| a new version held | `fake.clients.approve()` then `fake.extensions.hold("reason")` |
| igni failing | `fake.traffic.fail(IgniPaths.X, status)`, `fake.traffic.heal()` |
| a person removed | `fake.revocations.publish(user_id, org_id=...)` (needs `igni.lifespan` running) |
| the producer's igni taking an item | `fake.agents.settle(event_id, "delivered")` |
| an org admin deciding a VM request | `fake.vm_profiles.approve(...)`, `reject(...)` |

The [quick start](#quick-start) test is the usual shape. More examples
follow.

#### Testing sign-in to the service's own pages

```python
import httpx
from fastapi import Depends, FastAPI

from igni_service import Member, Notification, Person
from igni_service.testing import FakeIgni, SettingsOverrides

fake = FakeIgni()
fake.directory.add_member("org-1", Member(user_id="u-ada", email="ada@acme.test", name="Ada"))
igni = fake.service(fake.settings(SettingsOverrides(public_base_url="https://service.test")))
app = FastAPI()
igni.install(app)


@app.get("/settings")
async def settings(person: Person = Depends(igni.web.person)) -> dict[str, str]:
    return {"hello": person.name}


transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url="https://service.test") as browser:
    login = await browser.get(igni.web.login_path)   # a person opening the service's pages
    location = login.headers["location"]             # the portal signs Ada in
    back = fake.oauth.sign_ins.authorize(location, user_id="u-ada", org_id="org-1")
    await browser.get(back)                          # the service keeps a session
    assert (await browser.get("/settings")).json() == {"hello": "Ada"}
    await browser.post(igni.web.logout_path)

assert len(fake.oauth.revoked) == 1                  # the refresh token /auth/logout revoked

await igni.host("org-1").notify(Notification(kind="comment", title="Runbook", recipients=["u-ada"]))
assert [d.user_id for d in fake.notifications.deliveries] == ["u-ada"]
```

#### Testing a held version

```python
import json
from pathlib import Path

from igni_service.testing import FakeIgni

fake = FakeIgni()
igni = fake.service()
extension = Path("extension")
extension.mkdir()
manifest = extension / "manifest.json"

manifest.write_text(json.dumps({"id": "acme.example", "version": "1.0.0"}))
await fake.upload(extension, igni)
fake.clients.approve()                       # a super admin approves the service
fake.extensions.hold("it adds chat.post")    # igni will hold a version that asks for more

manifest.write_text(json.dumps({"id": "acme.example", "version": "1.1.0"}))
latest = await fake.upload(extension, igni)  # the service logs a warning with the reason
client_id = (await igni.connection.registration.client_id())
assert latest.version == "1.1.0"
assert fake.extensions.shipped(client_id).version == "1.0.0"   # devices keep the approved one
```

#### Testing what the service sent an agent

What a service sent producers' agents is `fake.agents.items` (every kind)
and `fake.agents.uploads`. `fake.agents.settle(event_id, "delivered")`
plays the producer's igni taking one, so `agent.status` reads it:

```python
from igni_service import Member, Producer
from igni_service.testing import FakeIgni

fake = FakeIgni()
fake.directory.add_member("org-1", Member(user_id="u-ada", email="ada@acme.test"))
agent = fake.service().host("org-1").agent(Producer.person("u-ada"))

accepted = await agent.send_event("index.ready", {"repo": "acme/api"}, event_key="index:acme/api")
again = await agent.send_event("index.ready", {"repo": "acme/api"}, event_key="index:acme/api")
assert again.duplicate and again.event_id == accepted.event_id

[sent] = fake.agents.items
assert (sent.type, sent.payload) == ("index.ready", {"repo": "acme/api"})

fake.agents.settle(accepted.event_id, "delivered")
assert (await agent.status(accepted.event_id)).state == "delivered"
```

#### Sharing one fake across a session

A fake can be shared across tests: `fake.reset()` between tests forgets
requests, failures, sign-ins, notifications, revocations, agent items and
held uploads, and keeps organisations, members, clients, keys and
uploaded extensions. Issued service tokens stay too, so a service shared
across the session may keep its cached token.

## Troubleshooting and FAQ

**The banner says `state: pending` and every directory or notify call
raises `ServiceNotApproved`.** No super admin has approved the service
yet. In igni's portal, *Services*, they compare the thumbprint shown with
the one in your service's banner and approve it. Restart is not needed:
the next call gets a service token.

**Calls raise `ServiceRevoked`.** A super admin revoked the service. igni
refuses its tokens and stops distributing its extension. Ask a super
admin.

**The service was approved, but nobody has the extension.** Approval
installs it nowhere. An org admin must switch the extension on for a
group (portal, the group's *Extensions* tab). Each person's igni installs
it at its next sync.

**A new version does not reach anybody, and the log says it is held for
a super admin.** The new version asks for more than the approved one: a
new tool, a wider grant (the warning names what it adds). Devices keep
the approved version until a super admin approves the new one in the
portal (*Services*).

**Every request from the extension is a 401.** Read the
`WWW-Authenticate` header or the service's log line `igni: refused a
token: …`:

- *the token is for another audience; this service's is …* —
  `PUBLIC_BASE_URL` differs from the URL the token was issued for. It
  must be exactly the service's public URL (scheme, host, port, path).
- *the token has expired* — the extension should renew it; check the
  clocks of both machines.
- *the token was issued in the future* — this machine's clock is behind.
- *the wrong kind of token* — an app's or a space's token on a route
  that takes people (`igni.person`), or a person's on `igni.igni_call`.
  Use `igni.caller` and `accepted_callers` to take apps.
- *was revoked* — the person was removed from the organisation.

**Every request is a 503 `igni server cannot be reached to check this
token`.** The service cannot fetch igni server's keys, or the revocation
list has not been refreshed for `IGNI_REVOCATIONS_MAX_STALENESS` seconds
(it fails closed). Check that `IGNI_SERVER_URL` is reachable from the
service. The log says `igni: cannot check a token: …`.

**`ConfigurationError: igni: IGNI_SERVER_URL, PUBLIC_BASE_URL must be set`
at start.** Set the three required variables. `PUBLIC_BASE_URL` must be
an absolute `http(s)` URL with no query or fragment.

**`ConfigurationError: igni: set IGNI_KEY_DATABASE_URL, or pass a
key_store`.** `IgniService.from_settings` needs somewhere to keep the key.

**`KeyStoreError: This service's key cannot be read with this
IGNI_KEY_ENCRYPTION_KEY`.** The key encryption key changed. Restore the
old one. Or delete the stored key (the `igni_service_key` row) to make a
new identity, which a super admin must approve again.

**`KeyStoreError: IGNI_KEY_ENCRYPTION_KEY is not set` / `is not a Fernet
key`.** Generate one with `python -c "from igni_service import KeyCipher;
print(KeyCipher.generate())"` and keep it.

**Erasure or export is reported as unconfirmed under the service's
name.** The route answered 501: the service registered no
`@igni.on_erase` or `@igni.on_export` handler. Register one, even one
that does nothing when the service holds nothing about people.

**The extension's page cannot read the service's answer (a CORS error in
the console).** The route must depend on `igni.person`,
`igni.optional_person`, `igni.org_admin`, `igni.caller`, `igni.token` or
`igni.optional_token`, and the call must carry `Authorization: Bearer`.
Routes on `igni.web.*`, igni's own calls, or with no token get no
cross-origin yes. Call `igni.install(app)`.

**`EventRefused` 403 when sending a message.** The extension's manifest
does not declare the grant: `"permissions": {"service": ["messages",
"attachments", "chats"]}`. The super admin approves grants with the
service.

**An event reads `not_handled`.** No handler for its type in the
extension (`@ext.on_service_event("type")`), the extension was not
running, or the handler raised. `not_handled_reason` says which.

**`igni-service-bundle` says `dependencies with no usable wheel`.** A
dependency publishes no wheel for a platform. If it is pure Python,
declare it under `[tool.igni.bundle] sdist-only`. Otherwise build only for
the platforms your devices use (`--platform`), or replace it.

**The bundle has no tools for the agent (a note says `could not read the
tools from the code`).** The builder could not run
`python -m igni_extension.manifest` on the wheelhouse, often because the
build machine's platform is not in the bundle. Build on a platform the
bundle includes, or list `permissions.tools` in the manifest.

**Nothing from `igni_service` appears in the logs.** Log lines are made
visible by `igni.lifespan` only when neither the root logger nor
`igni_service` has a handler. If you configured logging, set the
`igni_service` logger to INFO.

**Do I need a database?** In production, yes: the key must survive
restarts and be shared by every replica. A restart with `MemoryKeyStore`
is a new identity that must be approved again.

**Can the service sign people in with its own login?** It does not need
to. People arrive with igni's token (`igni.person`), or sign in through
igni's portal for the service's own pages (`igni.web`).

## Changes since 0.1.0

Changed on purpose, in `igni_service.testing`.

**The fake is one object of collaborators now.** Each part of igni is
separate, and a test talks to the one it means: `fake.directory`
(organisations and members), `fake.clients` (registrations),
`fake.signer` (the tokens igni signs, and its keys), `fake.oauth` (the
token endpoint, and the portal's sign-in), `fake.extensions` (bundles
and assets), `fake.notifications`, `fake.revocations`, `fake.agents`,
`fake.vm_profiles`, `fake.traffic` (every request) and `fake.router`
(what answers them). In 0.1.0 all of that was on `FakeIgni` itself, and
the names below are where each one went.

- `FakeIgni(base_url=…, issuer=…, service_url=…)` is gone: the three
  addresses are one model now,
  `FakeIgni(addresses=IgniAddresses(base_url=…, issuer=…,
  service_url=…))`. `FakeIgni()` still means the same three defaults,
  and `clock=` and `require_approval=` are unchanged.
- The directory is `fake.directory`, and its methods take models:
  `fake.add_organisation(org_id, name=…)` is
  `fake.directory.add_organisation(Organisation(org_id=…, name=…))`;
  `fake.add_member(org_id, user_id, email=…)` is
  `fake.directory.add_member(org_id, Member(user_id=…, email=…))`;
  `fake.delete_organisation(org_id)` is
  `fake.directory.delete_organisation(org_id, igni_token)` — it needs
  the token the call now carries.
- The tokens igni signs are `fake.signer`'s: `fake.person_token(…)`,
  `fake.app_token(…)`, `fake.space_token(…)` and `fake.igni_token(…)`
  are the same four calls on `fake.signer`, and `fake.rotate()` is
  `fake.signer.keys.rotate()`. The general
  `fake.token(sub, **claims)` is
  `fake.signer.sign(sub, claims, overrides=TokenOverrides(…))`: what a
  test bent the token with is one model now, and the claims are a model
  too (`PersonClaims`, `SpaceClaims`).
- `fake.approve(client_id)` and `fake.revoke(client_id)` are
  `fake.clients.approve(…)` and `fake.clients.revoke(…)`, and
  `fake.registration` is `fake.clients.registration`. `fake.clients`
  is the registry now, not the dict it was; the dict is
  `fake.clients.clients`.
- The portal's sign-in is `fake.oauth.sign_ins.authorize(…)`, and the
  token endpoint's own records are `fake.oauth.grants` and
  `fake.oauth.revoked`.
- `fake.expire_service_tokens()` is
  `fake.oauth.bearers.expire_service()`.
- `fake.publish_revocation(…)` is
  `fake.revocations.publish(subject_id, *, org_id=…)`. `fake.revocations`
  is that publisher now; what it published is
  `fake.revocations.revocations`.
- `fake.failing[prefix] = status` is `fake.traffic.fail(prefix, status)`
  (`fake.traffic.heal()` stops it); `fake.seen` is `fake.traffic.seen`,
  and `fake.requests_to(path)` is `fake.traffic.requests_to(path)`.
- `fake.notify_calls` and `fake.deliveries` are
  `fake.notifications.calls` and `fake.notifications.deliveries`;
  `fake.events` is `fake.agents.items`.
- `fake.extensions` is the store of bundles and assets, not a dict:
  `fake.extensions.shipped(client_id)` is the bundle machines get and
  `fake.extensions.latest(client_id)` the last one uploaded;
  `fake.hold_uploads = "reason"` is `fake.extensions.hold("reason")`
  (`fake.extensions.release()` stops it).
- `fake.pair`, `fake.kid` and `fake.published` are `fake.signer.keys`'s.
- `fake.deactivate(org_id, user_id)` is
  `fake.directory.organisations[org_id].deactivate(user_id)`.
- `fake.settings(**overrides)` takes a `SettingsOverrides` model now:
  `fake.settings(SettingsOverrides(service_name="…"))`. Only the fields
  it sets are applied; the rest are the fake's own addresses and
  `IgniSettings`' defaults.
- `FakeIgni.handle(request)` is gone. Call `fake.router.handle(request)`
  instead; `fake.transport()` and `fake.http_client()` route through it.
- `FakeIgni.approve_vm_profile(org_id, app=..., extension=...)` and
  `reject_vm_profile(...)` are gone, and with them the `ValueError` for
  naming both or neither. Use `fake.vm_profiles.approve(org_id,
  VmProfileSubject.app(app_id))` or `VmProfileSubject.extension(extension_id)`.
- `FakeVmProfiles.request`, `approve` and `reject` take
  `(org_id, subject: VmProfileSubject, ...)`. The 0.1.0 form
  `(org_id, kind, subject_id, ...)` raises `TypeError`.

New and worth knowing: `IgniAddresses`, `TokenOverrides`,
`SettingsOverrides`, `PersonClaims` and `SpaceClaims` are all exported
from `igni_service.testing`, and the collaborators are named in
[The fake's collaborators](#the-fakes-collaborators) above.

---

Licensed under Apache-2.0. Source, issues and the other SDKs:
[github.com/ignite-ember/igni-sdk](https://github.com/ignite-ember/igni-sdk).
