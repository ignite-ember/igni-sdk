"""igni-client: drive an igni from your own code.

Connect headlessly to a person's, an app's or a space's igni — in Fleet,
through its gateway, or on this machine — and run work there:

    from igni_client import Fleet, IgniClient, Person

    async with IgniClient(Fleet("https://gw.acme.internal", auth=Person.from_cli())) as igni:
        session = await igni.sessions.create()
        reply = await session.ask("Summarise the open pull requests", approve=False)
        print(reply)

`Session.send()` follows a run event by event, approvals included; every
one of igni's methods is a typed method on `IgniClient` or `Session`
(`igni_client.api`), its arguments and result generated from igni-core's
contract (`igni_client.models`); a method that streams returns a `Call`
that follows this call's events; `igni.commands.run()` runs a shell
command in the VM.
"""

from igni_client.approvals import ApprovalRequested, Decision
from igni_client.auth.app import App
from igni_client.auth.person import ApiKey, Person
from igni_client.auth.spaces import Space, SpaceRecord, Spaces
from igni_client.auth.tokens import TokenSource
from igni_client.backoff import Backoff
from igni_client.calls import Call
from igni_client.client import IgniClient
from igni_client.commands import CommandFinished, CommandOutput, CommandRun, Commands, Me
from igni_client.errors import (
    AccessRefused,
    ApprovalRequired,
    AuthError,
    IgniClientError,
    InvalidArguments,
    MethodFailed,
    NotAllowed,
    NotSupported,
    RpcError,
    RunFailed,
    RunInterrupted,
    Unavailable,
    UnexpectedAnswer,
    UnknownMethod,
)
from igni_client.events import (
    CommandResult,
    ContentDelta,
    ErrorMessage,
    Event,
    InfoMessage,
    ModelCompleted,
    PushNotification,
    ReasoningStarted,
    Requirement,
    RequirementDetails,
    RequirementResolved,
    RunCompleted,
    RunError,
    RunEvent,
    RunPaused,
    RunStarted,
    StatusUpdate,
    StreamingDone,
    TaskCreated,
    TaskStateUpdated,
    TaskUpdated,
    ToolCompleted,
    ToolError,
    ToolStarted,
    Unknown,
    UserMessageReceived,
)
from igni_client.models import ChatTurn, SessionListEntry
from igni_client.replies import Reply
from igni_client.sessions import Session, Sessions
from igni_client.targets import Fleet, Local, Target

__all__ = [
    # Connecting
    "IgniClient",
    "Fleet",
    "Local",
    "Target",
    "Backoff",
    # Who
    "Person",
    "ApiKey",
    "App",
    "Space",
    "Spaces",
    "SpaceRecord",
    "TokenSource",
    # Sessions and runs
    "Session",
    "Sessions",
    "SessionListEntry",
    "ChatTurn",
    "Call",
    "ApprovalRequested",
    "Decision",
    "Reply",
    # Commands
    "Commands",
    "CommandRun",
    "CommandOutput",
    "CommandFinished",
    "Me",
    # Events
    "Event",
    "RunEvent",
    "ContentDelta",
    "RunStarted",
    "ReasoningStarted",
    "ToolStarted",
    "ToolCompleted",
    "ToolError",
    "ModelCompleted",
    "StreamingDone",
    "RunCompleted",
    "RunError",
    "RunPaused",
    "Requirement",
    "RequirementDetails",
    "RequirementResolved",
    "TaskCreated",
    "TaskUpdated",
    "TaskStateUpdated",
    "StatusUpdate",
    "CommandResult",
    "InfoMessage",
    "ErrorMessage",
    "UserMessageReceived",
    "PushNotification",
    "Unknown",
    # Errors
    "IgniClientError",
    "Unavailable",
    "AuthError",
    "NotAllowed",
    "NotSupported",
    "RpcError",
    "AccessRefused",
    "UnknownMethod",
    "InvalidArguments",
    "UnexpectedAnswer",
    "MethodFailed",
    "RunFailed",
    "RunInterrupted",
    "ApprovalRequired",
]
