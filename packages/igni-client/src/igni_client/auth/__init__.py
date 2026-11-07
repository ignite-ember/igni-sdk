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
"""
