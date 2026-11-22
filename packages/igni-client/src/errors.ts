// What igni-client raises on purpose.
//
// One root, `IgniClientError`, and a type per thing a caller decides differently
// about: try again later (`Unavailable`), fix the credential (`AuthError`;
// `SignInRequired` when a Fleet VM's own one was refused), stop (`NotAllowed`;
// `GroupIsLocalOnly` when the person's group runs igni only on the desktop), or
// look at what the agent did (`RunFailed`, `RunInterrupted`, `ApprovalRequired`).

import type { Requirement } from "./models.generated.js";

/** Anything this SDK raises on purpose. */
export class IgniClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** igni could not be reached, went away, or is busy — trying again later may work. */
export class Unavailable extends IgniClientError {}

/** The run ended with an error, or `ask()`'s prompt got an `error` and no run. */
export class RunFailed extends IgniClientError {}

/** The credential was refused: an expired or wrong token, or an app key igni does not know. */
export class AuthError extends IgniClientError {}

/**
 * The igni on a Fleet VM lost its own credential: igni server refused it.
 *
 * It is a `RunFailed` (the run did fail): code that catches `RunFailed` keeps
 * catching it, and code that wants to say how to recover catches this first.
 * (Python also makes it an `AuthError`; TypeScript has single inheritance, and
 * the `RunFailed` relationship is the one `ask()` callers rely on.)
 */
export class CredentialRefused extends RunFailed {
  readonly state: string;
  readonly detail: string;
  constructor(message: string, state: string, detail = "") {
    super(message);
    this.state = state;
    this.detail = detail;
  }
  /** The error a VM credential's `state` means, or `null` for one that works. */
  static of(state: string, detail = "", where = "igni"): CredentialRefused | null {
    const reason = detail ? ` (${detail})` : "";
    if (state === "needs_sign_in") {
      return new SignInRequired(
        `${where}: the VM's own credential was refused${reason}; sign the person in again ` +
          "at the gateway (POST /v1/sign-in), then ask again",
        state,
        detail,
      );
    }
    if (state === "needs_reissue") {
      return new ReissueRequired(
        `${where}: the app's VM credential was refused${reason}; an organisation admin ` +
          "re-issues it, and the VM takes it at its next start",
        state,
        detail,
      );
    }
    return null;
  }
}

/** A person's VM credential was refused: they sign in again at the gateway. */
export class SignInRequired extends CredentialRefused {}

/** An app's VM credential was refused: an organisation admin re-issues it. */
export class ReissueRequired extends CredentialRefused {}

/** igni answered and said no, and asking again will not change it. */
export class NotAllowed extends IgniClientError {}

/** The person's group runs igni only on the desktop: there is no cloud igni to reach. */
export class GroupIsLocalOnly extends NotAllowed {}

/** The target cannot do this: commands and identity exist only through Fleet's gateway. */
export class NotSupported extends IgniClientError {}

/** A call igni answered with an error, or whose answer could not be read. */
export class RpcError extends IgniClientError {
  readonly method: string;
  readonly detail: string;
  constructor(method: string, detail: string) {
    super(`${method}: ${detail}`);
    this.method = method;
    this.detail = detail;
  }
  /** The kind of error igni's `message` for `method` is, from its `code` or its words. */
  static of(method: string, message: string, code?: string | null): RpcError {
    if (code && code in BY_CODE) {
      return new BY_CODE[code](method, message);
    }
    if (code == null) {
      return RpcError.ofSentence(method, message);
    }
    return new MethodFailed(method, message);
  }
  private static ofSentence(method: string, message: string): RpcError {
    if (REFUSALS.some((marker) => message.includes(marker))) {
      return new AccessRefused(method, message);
    }
    if (message.startsWith("Unknown RPC method")) {
      return new UnknownMethod(method, message);
    }
    if (message.endsWith("is a required argument") || message.startsWith(`${method}: '`)) {
      return new InvalidArguments(method, message);
    }
    return new MethodFailed(method, message);
  }
}

/** igni refused the call from this connection: it is igni's window's, or an approver's. */
export class AccessRefused extends RpcError {}

/** igni does not have the method: it is older than this igni-client. */
export class UnknownMethod extends RpcError {}

/** The arguments are not what the method takes — refused before sending, or by igni. */
export class InvalidArguments extends RpcError {}

/** igni's answer is not what the method returns: igni and this igni-client disagree. */
export class UnexpectedAnswer extends RpcError {}

/** The method ran and failed; `message` is igni's reason. */
export class MethodFailed extends RpcError {}

/** The connection to igni moved or dropped while the run was going. */
export class RunInterrupted extends IgniClientError {}

/** `ask()` reached an approval and was given no policy to answer it with. */
export class ApprovalRequired extends IgniClientError {
  readonly requirements: Requirement[];
  constructor(requirements: Requirement[]) {
    const names =
      requirements.map((r) => r.friendly_name || r.tool_name).join(", ") || "a tool";
    super(`the run is waiting for approval of ${names}`);
    this.requirements = requirements;
  }
}

/** The gateway's reason when a person's group runs igni only on the desktop. */
export const GROUP_LOCAL_ONLY = "group_local_only";
/** The gateway's reason when it closes a connection whose token expired. */
export const TOKEN_EXPIRED = "token_expired";

const REASON_TOKEN = /^[a-z][a-z0-9_]*(?![A-Za-z0-9_])/;

/** The stable word a gateway's reason leads with, or `""` when it leads with none. */
export function reasonToken(reason: string): string {
  const found = REASON_TOKEN.exec(reason.trim());
  return found ? found[0] : "";
}

const BY_CODE: Record<string, new (method: string, detail: string) => RpcError> = {
  forbidden: AccessRefused,
  unknown_method: UnknownMethod,
  invalid: InvalidArguments,
};

const REFUSALS = [
  "only igni's window",
  "a program answers approval requests only with an approver token",
  "only on the platform's control connection",
  "an approver answers once",
];
