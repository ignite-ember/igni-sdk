"""Who the client connects as: a person, an app, or one of an app's spaces.

Each is a token source — `await auth.token()` — that a target asks for a
bearer token every time it opens a connection. Fleet's gateway checks the
token only when the socket opens, so a short-lived token is fetched again
for each connection, never refreshed under one that is open.

* **A person** (`person.py`) brings a session pinned to their organisation:
  the one `igni login` keeps, or one handed over explicitly. It lasts 30
  days. There is no headless sign-in for a person; an API key (`ApiKey`)
  buys short sessions as them instead.
* **An app** (`app.py`) signs in as itself — `client_credentials` with a
  `private_key_jwt` assertion signed with its own key (`keys.py`), whose
  public half an org admin registered on igni server. Its tokens last ten
  minutes and are renewed a minute before they run out.
* **A space** (`spaces.py`) is one end user of an app. The app declares it,
  then exchanges its own token for the space's.

Each name is defined in the module that owns it; 0.1.0's `igni_client.auth`
names are kept here too, so `from igni_client.auth import App` still works.
"""

from igni_client.auth.app import App
from igni_client.auth.grants import ACCESS_TOKEN_TYPE, ASSERTION_TYPE, TOKEN_EXCHANGE
from igni_client.auth.keys import ALGORITHM
from igni_client.auth.person import ApiKey, Person
from igni_client.auth.spaces import Space, SpaceRecord, Spaces
from igni_client.auth.tokens import TokenSource

__all__ = [
    "ACCESS_TOKEN_TYPE",
    "ALGORITHM",
    "ASSERTION_TYPE",
    "TOKEN_EXCHANGE",
    "ApiKey",
    "App",
    "Person",
    "Space",
    "SpaceRecord",
    "Spaces",
    "TokenSource",
]
