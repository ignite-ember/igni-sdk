"""The TypeScript ``App``'s client assertion is one a Python verifier accepts.

``App`` signs a ``private_key_jwt`` with Node's crypto; igni server verifies it
with Python. A mismatch — the wrong algorithm, a wrong ``kid``, a claim igni
server will not read — is a silent ``401``. This signs an assertion with the
built TypeScript ``AppKey`` and verifies it the way the server does (PyJWT,
RS256, the public JWK), so the two sides are held together across languages.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jwt
import pytest
from jwt.algorithms import RSAAlgorithm

ROOT = Path(__file__).resolve().parent.parent
KEYS_JS = ROOT / "packages" / "igni-client" / "dist" / "auth" / "keys.js"

_SCRIPT = """
import {{ AppKey }} from {keys!r};
import {{ generateKeyPairSync }} from "node:crypto";
const {{ privateKey }} = generateKeyPairSync("rsa", {{ modulusLength: 2048 }});
const pem = privateKey.export({{ type: "pkcs8", format: "pem" }}).toString();
const key = AppKey.fromPem(pem);
const now = Math.floor(Date.now() / 1000);
const token = key.sign({{
  iss: "app-1", sub: "app-1", aud: "https://issuer.example",
  iat: now, exp: now + 60, jti: "jti-1",
}});
console.log(JSON.stringify({{ token, jwks: key.jwks() }}));
"""


@pytest.mark.skipif(
    shutil.which("node") is None or not KEYS_JS.exists(),
    reason="needs node and the built igni-client (npm run build)",
)
def test_a_typescript_signed_assertion_verifies_with_pyjwt() -> None:
    done = subprocess.run(  # noqa: S603 — our own script, on our own build
        ["node", "--input-type=module", "-e", _SCRIPT.format(keys=str(KEYS_JS))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    signed = json.loads(done.stdout)
    public_key = RSAAlgorithm.from_jwk(json.dumps(signed["jwks"]["keys"][0]))

    header = jwt.get_unverified_header(signed["token"])
    assert header["alg"] == "RS256"
    assert header["kid"] == signed["jwks"]["keys"][0]["kid"]  # the RFC 7638 thumbprint

    claims = jwt.decode(
        signed["token"],
        public_key,  # type: ignore[arg-type]
        algorithms=["RS256"],
        audience="https://issuer.example",
    )
    assert claims["iss"] == "app-1"
    assert claims["sub"] == "app-1"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
