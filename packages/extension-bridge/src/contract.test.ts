/**
 * The types an extension author writes against. These are checked by
 * `tsc` (make npm-typecheck), not at run time: a line marked
 * `@ts-expect-error` that starts compiling fails the type-check.
 */
import { describe, expectTypeOf, it } from "vitest";

import { connect, type Bridge, type HostError } from "./index.js";
import type {
  CallMessage,
  ExtensionSettings,
  HelloMessage,
  LaunchParams,
  LocationMessage,
  LocationState,
  ParamsMessage,
  RpcArgs,
} from "./protocol.js";

type Params = { readonly doc: string };
type Settings = { readonly region: "eu" | "us" };

describe("the bridge's types", () => {
  it("names the extension's own params and settings through connect", () => {
    expectTypeOf(connect<Params, Settings>).returns.toEqualTypeOf<
      Promise<Bridge<Params, Settings>>
    >();
    expectTypeOf<Bridge<Params, Settings>["params"]>().toEqualTypeOf<Params>();
    expectTypeOf<
      Bridge<Params, Settings>["settings"]
    >().toEqualTypeOf<Settings>();
    expectTypeOf<
      Parameters<Bridge<Params, Settings>["onParams"]>[0]
    >().toEqualTypeOf<(params: Params) => void>();
  });

  it("defaults to readonly records, so the old call shape still compiles", () => {
    expectTypeOf(connect).returns.toEqualTypeOf<Promise<Bridge>>();
    expectTypeOf<Bridge["params"]>().toEqualTypeOf<LaunchParams>();
    expectTypeOf<Bridge["settings"]>().toEqualTypeOf<ExtensionSettings>();
    expectTypeOf<LaunchParams>().toEqualTypeOf<{
      readonly [key: string]: unknown;
    }>();
    expectTypeOf<RpcArgs>().toEqualTypeOf<{
      readonly [name: string]: unknown;
    }>();
    expectTypeOf<LocationState>().toEqualTypeOf<{
      readonly [key: string]: string;
    }>();
  });

  it("does not let a page write into what the host sent", () => {
    const write = (bridge: Bridge) => {
      // @ts-expect-error params are the host's, read-only
      bridge.params.tab = "x";
      // @ts-expect-error settings are the host's, read-only
      bridge.settings.region = "eu";
    };
    expectTypeOf(write).toBeFunction();
  });

  it("takes a readonly args object and a readonly location", () => {
    const args: Readonly<{ id: number }> = { id: 1 };
    const state: Readonly<{ tab: string }> = { tab: "browse" };
    const use = (bridge: Bridge) => {
      void bridge.rpc("acme_status", args);
      bridge.setLocation(state);
    };
    expectTypeOf(use).toBeFunction();
    expectTypeOf<Parameters<Bridge["rpc"]>[1]>().toEqualTypeOf<
      RpcArgs | undefined
    >();
  });

  it("hears a refused subscription through on's third argument", () => {
    expectTypeOf<Parameters<Bridge["on"]>[2]>().toEqualTypeOf<
      ((error: HostError) => void) | undefined
    >();
  });

  it("gives the wire's own messages the same readonly records", () => {
    expectTypeOf<HelloMessage["params"]>().toEqualTypeOf<LaunchParams>();
    expectTypeOf<ParamsMessage["params"]>().toEqualTypeOf<LaunchParams>();
    expectTypeOf<CallMessage["args"]>().toEqualTypeOf<RpcArgs>();
    expectTypeOf<LocationMessage["state"]>().toEqualTypeOf<LocationState>();
    expectTypeOf<HelloMessage["settings"]>().toEqualTypeOf<
      ExtensionSettings | undefined
    >();
  });
});
