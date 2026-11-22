// Signing a person in to the igni in their Fleet VM: the gateway's POST /v1/sign-in.
//
// A Fleet VM keeps a credential of its own, which igni exchanges for the tokens
// its model calls use. When igni server later refuses the credential, igni says
// `needs_sign_in` and the person signs in again here. The gateway wakes the VM,
// passes igni the session, and answers the credential's new state. igni-client
// never does this on its own: the program decides.

import { gatewayError } from "./commands.js";
import { Unavailable } from "./errors.js";
import type { VmCredentialState } from "./models.generated.js";
import type { Fleet } from "./targets.js";

export const SIGN_IN_PATH = "/v1/sign-in";

/** What the gateway answers a sign-in: the VM it woke and its credential's state. */
export class SignedIn {
  constructor(
    readonly producer: string,
    readonly node: string,
    readonly how: string,
    readonly credential: VmCredentialState | null,
    readonly extra: Record<string, unknown> = {},
  ) {}

  static read(raw: Record<string, unknown>): SignedIn {
    const { producer, node, how, credential, ...extra } = raw;
    const cred =
      credential && typeof credential === "object"
        ? (credential as unknown as VmCredentialState)
        : null;
    return new SignedIn(
      typeof producer === "string" ? producer : "",
      typeof node === "string" ? node : "",
      typeof how === "string" ? how : "",
      cred,
      extra,
    );
  }

  /** Whether igni in the VM now holds a working credential. */
  get ready(): boolean {
    return this.credential !== null && this.credential.state === "ready";
  }
}

/** Sign the person `fleet` connects as in to the igni in their VM. */
export async function signIn(fleet: Fleet): Promise<SignedIn> {
  const response = await fleet.request("POST", SIGN_IN_PATH);
  if (response.status !== 200) {
    throw await gatewayError(response);
  }
  try {
    return SignedIn.read((await response.json()) as Record<string, unknown>);
  } catch {
    throw new Unavailable(`the gateway at ${fleet.base} answered the sign-in with something else`);
  }
}
