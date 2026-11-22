// An app's RSA key: made, loaded, published as a JWK set, and signing assertions.
//
// RS256 only, matching igni server's verifier. The private key is read with
// Node's crypto; nothing here touches the browser.

import {
  createHash,
  createPrivateKey,
  createPublicKey,
  createSign,
  generateKeyPairSync,
  type KeyObject,
} from "node:crypto";
import { chmodSync, writeFileSync } from "node:fs";

/** The only signing algorithm on this wire. */
export const ALGORITHM = "RS256";

export interface Jwk {
  kty: "RSA";
  use: "sig";
  alg: "RS256";
  kid: string;
  n: string;
  e: string;
}

export interface JwkSet {
  keys: Jwk[];
}

/** The claims of a `private_key_jwt` client assertion (RFC 7523). */
export interface ClientAssertion {
  iss: string;
  sub: string;
  aud: string;
  iat: number;
  exp: number;
  jti: string;
}

function base64url(data: Buffer | string): string {
  return Buffer.from(data).toString("base64url");
}

/** An app's RSA private key. */
export class AppKey {
  private constructor(private readonly key: KeyObject) {}

  static fromPem(pem: string): AppKey {
    let key: KeyObject;
    try {
      key = createPrivateKey(pem);
    } catch {
      throw new Error("an app's key must be an RSA private key, as an unencrypted PEM");
    }
    if (key.asymmetricKeyType !== "rsa") {
      throw new Error("an app's key must be an RSA private key, as an unencrypted PEM");
    }
    return new AppKey(key);
  }

  /** Make a new RSA key and write it to `path`, readable by its owner only. */
  static generate(path: string): string {
    const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
    const pem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
    writeFileSync(path, pem, { mode: 0o600 });
    chmodSync(path, 0o600);
    return path;
  }

  private publicJwk(): { n: string; e: string } {
    const jwk = createPublicKey(this.key).export({ format: "jwk" }) as { n: string; e: string };
    return { n: jwk.n, e: jwk.e };
  }

  /** The key's RFC 7638 thumbprint: its `kid`, and what an admin compares. */
  thumbprint(): string {
    const { n, e } = this.publicJwk();
    const canonical = JSON.stringify({ e, kty: "RSA", n });
    return base64url(createHash("sha256").update(canonical).digest());
  }

  /** The public half, as a JWK set: what an org admin registers for this app. */
  jwks(): JwkSet {
    const { n, e } = this.publicJwk();
    return { keys: [{ kty: "RSA", use: "sig", alg: ALGORITHM, kid: this.thumbprint(), n, e }] };
  }

  sign(assertion: ClientAssertion): string {
    const header = base64url(JSON.stringify({ alg: ALGORITHM, typ: "JWT", kid: this.thumbprint() }));
    const payload = base64url(JSON.stringify(assertion));
    const signingInput = `${header}.${payload}`;
    const signature = createSign("RSA-SHA256").update(signingInput).sign(this.key);
    return `${signingInput}.${base64url(signature)}`;
  }
}
