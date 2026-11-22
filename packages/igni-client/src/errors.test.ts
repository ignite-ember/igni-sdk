import { describe, expect, it } from "vitest";

import {
  AccessRefused,
  ApprovalRequired,
  AuthError,
  CredentialRefused,
  GroupIsLocalOnly,
  IgniClientError,
  InvalidArguments,
  MethodFailed,
  NotAllowed,
  ReissueRequired,
  RpcError,
  RunFailed,
  SignInRequired,
  UnknownMethod,
  reasonToken,
} from "./errors.js";

describe("RpcError.of", () => {
  it("picks the kind from the code word", () => {
    expect(RpcError.of("m", "no", "forbidden")).toBeInstanceOf(AccessRefused);
    expect(RpcError.of("m", "no", "unknown_method")).toBeInstanceOf(UnknownMethod);
    expect(RpcError.of("m", "no", "invalid")).toBeInstanceOf(InvalidArguments);
    expect(RpcError.of("m", "no", "weird")).toBeInstanceOf(MethodFailed);
  });

  it("reads the kind from the sentence when there is no code", () => {
    expect(RpcError.of("m", "only igni's window may do this")).toBeInstanceOf(AccessRefused);
    expect(RpcError.of("m", "Unknown RPC method foo")).toBeInstanceOf(UnknownMethod);
    expect(RpcError.of("m", "path is a required argument")).toBeInstanceOf(InvalidArguments);
    expect(RpcError.of("m", "m: 'path' missing")).toBeInstanceOf(InvalidArguments);
    expect(RpcError.of("m", "it just broke")).toBeInstanceOf(MethodFailed);
  });

  it("keeps method and detail", () => {
    const err = RpcError.of("do_it", "nope");
    expect(err.method).toBe("do_it");
    expect(err.detail).toBe("nope");
    expect(err.message).toBe("do_it: nope");
  });
});

describe("the error tree", () => {
  it("nests so a caller can catch broadly or narrowly", () => {
    // AccessRefused is in the RpcError tree (Python also makes it a NotAllowed;
    // TS single inheritance keeps the RpcError relationship).
    expect(new AccessRefused("m", "x")).toBeInstanceOf(RpcError);
    expect(new AccessRefused("m", "x")).toBeInstanceOf(IgniClientError);
    expect(new GroupIsLocalOnly("x")).toBeInstanceOf(NotAllowed);
    // A refused VM credential is a RunFailed, so an ask() handler catches it.
    expect(new SignInRequired("x", "needs_sign_in")).toBeInstanceOf(RunFailed);
    expect(new SignInRequired("x", "needs_sign_in")).toBeInstanceOf(CredentialRefused);
  });
});

describe("CredentialRefused.of", () => {
  it("maps a credential state to the error that says how to recover", () => {
    expect(CredentialRefused.of("needs_sign_in", "why")).toBeInstanceOf(SignInRequired);
    expect(CredentialRefused.of("needs_reissue")).toBeInstanceOf(ReissueRequired);
    expect(CredentialRefused.of("ready")).toBeNull();
    const err = CredentialRefused.of("needs_sign_in", "token revoked", "igni X");
    expect(err?.state).toBe("needs_sign_in");
    expect(err?.detail).toBe("token revoked");
    expect(err?.message).toContain("igni X");
  });
});

describe("reasonToken", () => {
  it("reads the stable word a gateway reason leads with", () => {
    expect(reasonToken("group_local_only: your org runs local")).toBe("group_local_only");
    expect(reasonToken("token_expired")).toBe("token_expired");
    expect(reasonToken("  inactive — gone")).toBe("inactive");
    expect(reasonToken("Nope")).toBe("");
    expect(reasonToken("")).toBe("");
  });
});

describe("ApprovalRequired", () => {
  it("names the tools it is waiting on", () => {
    const err = new ApprovalRequired([
      { requirement_id: "r1", tool_name: "bash", friendly_name: "Run" },
      { requirement_id: "r2", tool_name: "write" },
    ]);
    expect(err.message).toContain("Run");
    expect(err.message).toContain("write");
    expect(err.requirements).toHaveLength(2);
    expect(new ApprovalRequired([]).message).toContain("a tool");
  });
});
