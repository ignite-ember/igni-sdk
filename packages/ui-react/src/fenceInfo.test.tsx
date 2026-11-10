/**
 * Spotting a fenced block's language from what ReactMarkdown hands a
 * `<pre>`, whatever shape a plugin left it in.
 */
import { describe, expect, it } from "vitest";

import { fenceInfo } from "./fenceInfo";

describe("fenceInfo", () => {
  it("reads the language and the source off the code child", () => {
    expect(
      fenceInfo(<code className="language-mermaid">{"graph TD; A-->B\n"}</code>),
    ).toEqual({ lang: "mermaid", source: "graph TD; A-->B" });
  });

  it("lowercases the language", () => {
    expect(fenceInfo(<code className="language-Mermaid">x</code>)?.lang).toBe(
      "mermaid",
    );
  });

  it("finds the language among other classes", () => {
    expect(
      fenceInfo(<code className="hljs language-objective-c wide">x</code>)
        ?.lang,
    ).toBe("objective-c");
  });

  it("strips one trailing newline and no more", () => {
    expect(
      fenceInfo(<code className="language-txt">{"a\n\n"}</code>)?.source,
    ).toBe("a\n");
  });

  it("looks only at the first child of several", () => {
    expect(
      fenceInfo([
        <code key="a" className="language-mermaid">
          x
        </code>,
        <code key="b" className="language-python">
          y
        </code>,
      ]),
    ).toEqual({ lang: "mermaid", source: "x" });
    expect(
      fenceInfo([
        "text",
        <code key="b" className="language-python">
          y
        </code>,
      ]),
    ).toBeNull();
  });

  it("is null for a child that is not an element", () => {
    expect(fenceInfo("graph TD; A-->B")).toBeNull();
    expect(fenceInfo(null)).toBeNull();
    expect(fenceInfo(undefined)).toBeNull();
  });

  it("is null for a block with no language", () => {
    expect(fenceInfo(<code>x</code>)).toBeNull();
    expect(fenceInfo(<code className="hljs">x</code>)).toBeNull();
  });

  it("gives an empty source when the code is not plain text", () => {
    expect(
      fenceInfo(
        <code className="language-js">
          <span>let</span> x
        </code>,
      ),
    ).toEqual({ lang: "js", source: "" });
  });
});
