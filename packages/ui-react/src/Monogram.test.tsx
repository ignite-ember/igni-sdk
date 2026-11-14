// @vitest-environment jsdom
/**
 * Two letters standing in for a face.
 *
 * The header used to render the *organisation* and nothing else, so
 * an account with no org claim showed a bare cloud icon: signed in,
 * and unable to say as whom.
 *
 * What is tested here is the reading of a name, because the input is
 * often an email address and treating one as a name is the obvious
 * wrong turn — "maya@acme.test" must read as M, not as MA picked from
 * "maya" and "acme".
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { hexOf, hueOf, initialsOf, Monogram } from "./Monogram.js";

afterEach(cleanup);

describe("hexOf", () => {
  it("answers a six-digit hex, which is all the caret accepts", () => {
    // The collaborative caret validates against this exact shape and
    // renders anything else transparent — so a colour that is merely
    // valid CSS is not enough.
    expect(hexOf("maya@acme.test")).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("gives the same person the same colour every time", () => {
    expect(hexOf("sam@acme.test")).toBe(hexOf("sam@acme.test"));
  });

  it("gives different people different colours", () => {
    expect(hexOf("maya@acme.test")).not.toBe(hexOf("sam@acme.test"));
  });

  it("agrees with the monogram's hue, so a caret matches its initials", () => {
    const hex = hexOf("maya@acme.test").slice(1);
    const [r, g, b] = [0, 2, 4].map(
      (at) => parseInt(hex.slice(at, at + 2), 16) / 255,
    );
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let hue = 0;
    if (max !== min) {
      const d = max - min;
      if (max === r) hue = ((g - b) / d + (g < b ? 6 : 0)) * 60;
      else if (max === g) hue = ((b - r) / d + 2) * 60;
      else hue = ((r - g) / d + 4) * 60;
    }
    expect(Math.round(hue)).toBeCloseTo(hueOf("maya@acme.test"), -1);
  });

  it("stays in range for every hue", () => {
    for (const name of ["a", "zz", "person@example.test", "Ada Byron", ""]) {
      expect(hexOf(name)).toMatch(/^#[0-9a-f]{6}$/);
    }
  });
});

describe("initialsOf", () => {
  it("takes the first and last of a full name", () => {
    expect(initialsOf("Maya Okonkwo")).toBe("MO");
  });

  it("skips middle names rather than cramming them in", () => {
    expect(initialsOf("Ada Grace Lovelace")).toBe("AL");
  });

  it("reads an address as its local part only", () => {
    // The domain is not part of anybody's name.
    expect(initialsOf("maya@acme.test")).toBe("MA");
  });

  it("splits a dotted address into initials", () => {
    expect(initialsOf("maya.okonkwo@acme.test")).toBe("MO");
  });

  it("handles underscores and hyphens the same way", () => {
    expect(initialsOf("maya_okonkwo")).toBe("MO");
    expect(initialsOf("maya-okonkwo")).toBe("MO");
  });

  it("gives a single word two letters rather than one", () => {
    // One letter in a circle reads as an icon, not a person.
    expect(initialsOf("maya")).toBe("MA");
  });

  it("says nothing rather than crashing on nothing", () => {
    expect(initialsOf("")).toBe("?");
    expect(initialsOf("   ")).toBe("?");
  });

  it("upper-cases whatever it found", () => {
    expect(initialsOf("ada lovelace")).toBe("AL");
  });
});

describe("hueOf", () => {
  it("is stable for the same name", () => {
    // The monogram is a recognition aid. One that changed colour per
    // session would be decoration.
    expect(hueOf("Maya Okonkwo")).toBe(hueOf("Maya Okonkwo"));
  });

  it("separates different names", () => {
    expect(hueOf("Maya Okonkwo")).not.toBe(hueOf("Dana Reyes"));
  });

  it("stays inside the colour wheel", () => {
    for (const name of ["", "a", "Maya Okonkwo", "x".repeat(200)]) {
      const hue = hueOf(name);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    }
  });
});

describe("initialsOf at the edges", () => {
  it("reads a name made only of separators, or only an @, as unknown", () => {
    for (const name of ["---", "...", "_ . -", "@", "@acme.test", "  @x"]) {
      expect(initialsOf(name), name).toBe("?");
    }
  });

  it("gives a one-letter name one letter", () => {
    expect(initialsOf("x")).toBe("X");
  });

  it("never cuts an emoji in half", () => {
    // A lone surrogate renders as a replacement box, in the one place
    // that exists to be recognised at a glance.
    expect(initialsOf("a😀")).toBe("A😀");
    expect(initialsOf("😀 maya")).toBe("😀M");
    expect(initialsOf("maya 😀")).toBe("M😀");
    expect(initialsOf("😀")).toBe("😀");
    expect(initialsOf("😀😀😀")).toBe("😀😀");
  });

  it("upper-cases after choosing the letters", () => {
    expect(initialsOf("ßa")).toBe("SSA");
    expect(initialsOf("émile zola")).toBe("ÉZ");
  });
});

describe("hueOf", () => {
  it("is zero for no name, and for a missing one", () => {
    expect(hueOf("")).toBe(0);
    expect(hueOf(undefined as unknown as string)).toBe(0);
    expect(hueOf(null as unknown as string)).toBe(0);
  });

  it("hashes the characters in order, modulo 360", () => {
    expect(hueOf("a")).toBe(97);
    expect(hueOf("ab")).toBe((97 * 31 + 98) % 360);
    expect(hueOf("ba")).not.toBe(hueOf("ab"));
  });
});

describe("hexOf by colour sector", () => {
  // One name per sixth of the wheel: hue 0 is red, 60 yellow, 120
  // green, 180 cyan, 240 blue, 300 magenta; each name is found by its
  // hue below, so a mistaken sector shows as the wrong colour.
  const byHue = (hue: number) => {
    for (let i = 33; i < 127; i++) {
      for (let j = 33; j < 127; j++) {
        const name = String.fromCharCode(i, j);
        if (hueOf(name) === hue) return name;
      }
    }
    throw new Error(`no name with hue ${hue}`);
  };

  it.each([
    [0, "#d03939"],
    [60, "#d0d039"],
    [120, "#39d039"],
    [180, "#39d0d0"],
    [240, "#3939d0"],
    [300, "#d039d0"],
  ])("draws hue %i as %s", (hue, hex) => {
    const name = hue === 0 ? "" : byHue(hue);
    expect(hexOf(name)).toBe(hex);
  });

  it("takes saturation and lightness from the caller", () => {
    expect(hexOf("", 0, 0.5)).toBe("#808080");
    expect(hexOf("", 1, 0.5)).toBe("#ff0000");
    expect(hexOf("", 0.62, 0)).toBe("#000000");
    expect(hexOf("", 0.62, 1)).toBe("#ffffff");
  });

  it("answers a colour for a missing name", () => {
    expect(hexOf(undefined as unknown as string)).toBe(hexOf(""));
  });
});

describe("Monogram", () => {
  const draw = (props: { name: string; size?: number }) => {
    const { container } = render(<Monogram {...props} />);
    return container.firstElementChild as HTMLElement;
  };

  it("is a hidden square of 18 pixels by default, with the initials in it", () => {
    const el = draw({ name: "Maya Okafor" });
    expect(el.tagName).toBe("SPAN");
    expect(el.className).toBe("monogram");
    expect(el.getAttribute("aria-hidden")).toBe("true");
    expect(el.textContent).toBe("MO");
    expect(el.style.width).toBe("18px");
    expect(el.style.height).toBe("18px");
    expect(el.style.fontSize).toBe("8px");
  });

  it("scales its square and its type with size", () => {
    const el = draw({ name: "Maya", size: 40 });
    expect(el.style.width).toBe("40px");
    expect(el.style.height).toBe("40px");
    expect(el.style.fontSize).toBe("18px");
  });

  it("takes its colour from the name, at a fixed saturation and lightness", () => {
    const el = draw({ name: "Maya Okafor" });
    // What the browser makes of the hsl() it was given, read back.
    const probe = document.createElement("i");
    probe.style.background = `hsl(${hueOf("Maya Okafor")} 42% 42%)`;
    expect(probe.style.background).not.toBe("");
    expect(el.style.background).toBe(probe.style.background);
  });

  it("is the same colour for the same name, and says '?' for none", () => {
    expect(draw({ name: "Maya" }).style.background).toBe(
      draw({ name: "Maya" }).style.background,
    );
    expect(draw({ name: "" }).textContent).toBe("?");
  });
});
