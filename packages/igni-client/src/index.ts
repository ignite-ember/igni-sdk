// @ignite-ember/igni-client: drive an igni from your own TypeScript or JavaScript.
//
// Connect headlessly to a person's, an app's or a space's igni — in Fleet,
// through its gateway, or on this machine — and run work there:
//
//   import { Fleet, IgniClient, Person } from "@ignite-ember/igni-client";
//
//   await using igni = await new IgniClient(
//     new Fleet("https://gw.acme.internal", { auth: new Person(token) }),
//   ).connect();
//   const session = await igni.sessions.create();
//   const reply = await session.ask("Summarise the open pull requests", { approve: false });
//   console.log(reply.text);

// Connecting
export { IgniClient } from "./client.js";
export { Local, Fleet, requireFleet } from "./targets.js";
export type { Target, LocalOptions, FleetOptions } from "./targets.js";
export { Backoff } from "./backoff.js";

// Finding the cloud igni, and signing in to it
export {
  discover,
  setEventsOwner,
  checkedGateway,
  insecureGatewayAllowed,
  CloudIgni,
  REASONS,
  CLOUD_PATH,
  EVENTS_OWNER_PATH,
  INSECURE_GATEWAY_ENV,
} from "./cloud.js";
export type { CloudGroup, CloudState, Mode, EventsOwner } from "./cloud.js";
export { signIn, SignedIn, SIGN_IN_PATH } from "./signIn.js";

// Who (auth / token sources)
export { Person, ApiKey } from "./auth/person.js";
export { App } from "./auth/app.js";
export { Space, Spaces } from "./auth/spaces.js";
export type { SpaceRecord } from "./auth/spaces.js";
export type { TokenSource } from "./auth/tokens.js";
export { AppKey, ALGORITHM } from "./auth/keys.js";
export type { Jwk, JwkSet } from "./auth/keys.js";

// Sessions and runs
export { Session, Sessions } from "./sessions.js";
export { Call, Caller } from "./calls.js";
export { ApprovalRequested, Approver, Decision } from "./approvals.js";
export type { Policy, Answer, Choice, Scope } from "./approvals.js";
export { Reply } from "./replies.js";
export { Run } from "./runs.js";
export type { RunItem } from "./runs.js";

// Commands (Fleet only)
export { Commands, CommandRun } from "./commands.js";
export type { CommandOutput, CommandFinished, Me, VmState } from "./commands.js";

// Events, parsing and the wire
export { parseEvent, isKnownEvent, isTypedPush } from "./events.js";
export type { Event, Unknown, ServerEvent, RunEvent } from "./events.js";
export type { WireMessage, Frame } from "./wire.js";
export type { MethodSpec, Correlation } from "./methodSpec.js";
export { METHODS, NOT_FOR_CLIENTS } from "./api.generated.js";
export type { Socket, SocketFactory } from "./socket.js";
export { nodeSocketFactory } from "./socket.js";

// The generated per-namespace API classes and every model type
export * from "./api.generated.js";
export * from "./models.generated.js";

// Errors
export {
  IgniClientError,
  Unavailable,
  AuthError,
  CredentialRefused,
  SignInRequired,
  ReissueRequired,
  NotAllowed,
  GroupIsLocalOnly,
  NotSupported,
  RpcError,
  AccessRefused,
  UnknownMethod,
  InvalidArguments,
  UnexpectedAnswer,
  MethodFailed,
  RunFailed,
  RunInterrupted,
  ApprovalRequired,
} from "./errors.js";
