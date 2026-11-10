"""igni, played in-process — and Fleet's gateway in front of it — for testing code built on igni-client.

`FakeIgni` speaks igni's protocol on a real loopback socket: it says
welcome, answers calls, plays a scripted run for every prompt, pauses for
approvals and resumes on the answer, and broadcasts every message to every
client attached, as igni does. Given a `FakeGateway` it also checks bearer
tokens on `/v1/connect` and serves `/v1/me` and `/v1/commands` through an
`httpx.MockTransport`.

    async with FakeIgni(gateway=FakeGateway({"t-ada": "person:u-ada"})) as fake:
        fake.runs.script = lambda text: Steps.answer(f"you said {text}")
        async with IgniClient(fake.fleet(Person("t-ada"))) as igni:
            session = await igni.sessions.create()
            assert str(await session.ask("hi")) == "you said hi"

Each part is a collaborator a test talks to: `fake.runs` (the script, and
every approval answer), `fake.methods` (answers, models, history,
sessions; `unbound_for(n)`), `fake.socket` (everything received,
`broadcast`, and what Fleet does under you: `move()`, `drop(code)`,
`busy_next(n)`, and `push(channel, payload)` for what igni's tools push),
`fake.commands` (how a slash command is answered) and `fake.gateway`
(commands, and every command run). `sample(T)` is a valid value of any of
igni-client's types, for an answer a test does not care to write out.
"""

from igni_client.testing.fake import FakeIgni
from igni_client.testing.gateway import FakeGateway, PlayedCommand
from igni_client.testing.inbound import ClientFrame, Received, UnknownFrame
from igni_client.testing.methods import FakeMethods, RpcAnswer
from igni_client.testing.runs import FakeRuns
from igni_client.testing.samples import sample
from igni_client.testing.server import FakeSocket, LocalHandshake
from igni_client.testing.steps import Delay, Pause, Script, Step, Steps

__all__ = [
    "ClientFrame",
    "Delay",
    "FakeGateway",
    "FakeIgni",
    "FakeMethods",
    "FakeRuns",
    "FakeSocket",
    "LocalHandshake",
    "Pause",
    "PlayedCommand",
    "Received",
    "RpcAnswer",
    "Script",
    "Step",
    "Steps",
    "UnknownFrame",
    "sample",
]
