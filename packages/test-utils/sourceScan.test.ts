/**
 * `withoutComments` is the scanner the floor's guards read source
 * through. Its promise is that comments vanish and nothing else moves:
 * the same length, the same lines, strings untouched.
 */
import { describe, expect, it } from "vitest";

import { withoutComments } from "./sourceScan";

describe("withoutComments: offsets and lines", () => {
  it("keeps the length when a block comment holds an astral character", () => {
    const src = "a /* 😀 */ b";
    const out = withoutComments(src);
    expect(out.length).toBe(src.length);
    expect(out).toBe("a " + " ".repeat(src.length - 4) + " b");
    expect(out.indexOf("b")).toBe(src.indexOf("b"));
  });
});

describe("withoutComments: comments", () => {
  it("blanks a line comment up to its newline and keeps the newline", () => {
    expect(withoutComments("a // hi\nb")).toBe("a      \nb");
  });

  it("blanks a line comment on the last line that has no newline", () => {
    expect(withoutComments("a // hi")).toBe("a      ");
  });

  it("blanks a block comment across lines, keeping every newline", () => {
    const src = "a /* x\ny\nz */ b";
    const out = withoutComments(src);
    expect(out.length).toBe(src.length);
    expect(out.split("\n").length).toBe(3);
    expect(out).toBe("a     \n \n     b");
  });

  it("turns a carriage return inside a block comment into a space", () => {
    expect(withoutComments("/* a\r\nb */x")).toBe("     \n    x");
  });

  it("blanks the carriage return that ends a line comment's text, keeping the newline", () => {
    expect(withoutComments("// a\r\nb")).toBe("     \nb");
  });

  it("blanks an empty block comment to four spaces", () => {
    expect(withoutComments("a/**/b")).toBe("a    b");
  });

  it("blanks an unterminated block comment through to the end without throwing", () => {
    expect(withoutComments("a /* never closed\nb")).toBe("a " + " ".repeat(15) + "\n ");
  });

  it("returns the empty string for empty input", () => {
    expect(withoutComments("")).toBe("");
  });

  it("is not fooled by an apostrophe in a comment", () => {
    const out = withoutComments("// don't\nx /* it's */ y // z");
    expect(out).toBe(" ".repeat(8) + "\nx " + " ".repeat(10) + " y " + " ".repeat(4));
  });

  it("leaves code with no comment as it was", () => {
    const src = "const a = b / c * d;\n";
    expect(withoutComments(src)).toBe(src);
  });
});

describe("withoutComments: string literals", () => {
  it("keeps // inside a string, as in a URL", () => {
    const src = 'const u = "https://example.test"; // note';
    expect(withoutComments(src)).toBe('const u = "https://example.test";        ');
  });

  it("keeps /* inside a string, as in the tsconfig key react/*", () => {
    const src = '{"paths": {"react/*": ["x"]}} /* c */';
    expect(withoutComments(src)).toBe('{"paths": {"react/*": ["x"]}}        ');
  });

  it("treats single-quoted and template strings the same way", () => {
    expect(withoutComments("'//a' `/*b` // c")).toBe("'//a' `/*b`     ");
  });

  it("honours a backslash escape, so an escaped quote does not end the string", () => {
    const src = String.raw`"a\" // still in" // out`;
    expect(withoutComments(src)).toBe(String.raw`"a\" // still in"       `);
  });

  it("honours an escaped backslash right before the closing quote", () => {
    const src = String.raw`"a\\" // out`;
    expect(withoutComments(src)).toBe(String.raw`"a\\"       `);
  });

  it("copies an unterminated string to the end, swallowing later comment markers", () => {
    const src = 'x = "open // not a comment\n/* nor this */';
    expect(withoutComments(src)).toBe(src);
  });

  it("ends cleanly when a backslash is the last character of the input", () => {
    expect(withoutComments('"abc\\')).toBe('"abc\\');
  });
});

describe("withoutComments: tsconfig", () => {
  it("yields JSON that parses, with the paths keys intact", () => {
    const src = `{
  // the compiler
  "compilerOptions": {
    /* aliases */
    "paths": { "react/*": ["./node_modules/@types/react/*"], "u": ["https://x"] }
  }
}`;
    const parsed = JSON.parse(withoutComments(src));
    expect(Object.keys(parsed.compilerOptions.paths)).toEqual(["react/*", "u"]);
    expect(parsed.compilerOptions.paths.u).toEqual(["https://x"]);
  });
});
