"""igni-client: drive an igni from your own code.

Connect headlessly to a person's, an app's or a space's igni — in Fleet,
through its gateway, or on this machine — and run work there:

    from igni_client import Fleet, IgniClient, Person

    async with IgniClient(Fleet("https://gw.acme.internal", auth=Person.from_cli())) as igni:
        session = await igni.sessions.create()
        reply = await session.ask("Summarise the open pull requests", approve=False)
        print(reply)

`Session.send()` follows a run event by event, approvals included;
`igni.commands.run()` runs a shell command in the VM; `igni.rpc()` reaches
any of igni's methods.
"""

from igni_client.approvals import ApprovalRequested, Decision
from igni_client.auth.app import App
from igni_client.auth.person import ApiKey, Person
from igni_client.auth.spaces import Space, SpaceRecord, Spaces
from igni_client.auth.tokens import TokenSource
from igni_client.backoff import Backoff
from igni_client.client import IgniClient
from igni_client.commands import CommandFinished, CommandOutput, CommandRun, Commands, Me
from igni_client.errors import (
    ApprovalRequired,
    AuthError,
    IgniClientError,
    NotAllowed,
    NotSupported,
    RpcError,
    RunFailed,
    RunInterrupted,
    Unavailable,
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
    SessionListEntry,
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
from igni_client.replies import Reply
from igni_client.sessions import ModelCatalogue, Models, Session, Sessions
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
    "Models",
    "ModelCatalogue",
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
    "SessionListEntry",
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
    "RunFailed",
    "RunInterrupted",
    "ApprovalRequired",
]
