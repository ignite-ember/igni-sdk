// @vitest-environment jsdom
/**
 * What an icon means, on hover and on focus.
 *
 * A toolbar of glyphs is quicker to scan and slower to learn. The
 * browser's own ``title`` does technically say the word — after a
 * second and a half, in the operating system's font, at the pointer
 * rather than at the control, and never at all for somebody on a
 * keyboard.
 *
 * The dwell is the part worth pinning: a pointer crossing a row of
 * buttons on its way somewhere else must not leave a trail of
 * popups, while a keyboard user arriving at a control has asked for
 * the word by arriving.
 */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Tooltip } from "./Tooltip.js";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function iconButton(text = "Show archived documents") {
  return render(
    <Tooltip text={text}>
      <button type="button" aria-label="Show archived documents">
        ▣
      </button>
    </Tooltip>,
  );
}

/**
 * The control, not the wrapper.
 *
 * The wrapper is ``display: contents`` and so has no box, which
 * means a real browser never hits it with a pointer. Firing at it
 * here passed for exactly that reason — jsdom does no hit-testing —
 * while the tooltip never once appeared on screen. Hovering what a
 * person hovers is the only version of this test worth having.
 */
const control = () => screen.getByRole("button");
const tip = () => document.querySelector(".tip");
const anchor = () => document.querySelector(".tip-anchor") as HTMLElement;

describe("hovering an icon", () => {
  it("says nothing at first", () => {
    iconButton();
    fireEvent.pointerEnter(control());

    // Still within the dwell: a pointer on its way past has not
    // asked for anything.
    expect(tip()).toBeNull();
  });

  it("says the word once the pointer rests", () => {
    vi.useFakeTimers();
    iconButton();

    fireEvent.pointerEnter(control());
    act(() => void vi.advanceTimersByTime(400));

    expect(tip()?.textContent).toBe("Show archived documents");
  });

  it("takes it away again on the way out", () => {
    vi.useFakeTimers();
    iconButton();
    fireEvent.pointerEnter(control());
    act(() => void vi.advanceTimersByTime(400));

    fireEvent.pointerLeave(control());

    expect(tip()).toBeNull();
  });

  it("does not appear at all if the pointer leaves before it settles", () => {
    vi.useFakeTimers();
    iconButton();

    fireEvent.pointerEnter(control());
    act(() => void vi.advanceTimersByTime(200));
    fireEvent.pointerLeave(control());
    act(() => void vi.advanceTimersByTime(400));

    expect(tip()).toBeNull();
  });

  it("gets out of the way when the control is pressed", () => {
    // The word has been read by then, and the thing it explains is
    // about to happen.
    vi.useFakeTimers();
    iconButton();
    fireEvent.pointerEnter(control());
    act(() => void vi.advanceTimersByTime(400));

    fireEvent.pointerDown(control());

    expect(tip()).toBeNull();
  });
});

describe("arriving by keyboard", () => {
  it("says the word straight away", () => {
    // No dwell. Somebody who tabbed to a control has asked for it by
    // arriving, and there is no pointer to rest.
    iconButton();

    fireEvent.focus(screen.getByRole("button"));

    expect(tip()?.textContent).toBe("Show archived documents");
  });

  it("takes it away on the way to the next control", () => {
    iconButton();
    fireEvent.focus(screen.getByRole("button"));

    fireEvent.blur(screen.getByRole("button"));

    expect(tip()).toBeNull();
  });

  it("closes on Escape without leaving the control", () => {
    iconButton();
    fireEvent.focus(screen.getByRole("button"));

    fireEvent.keyDown(window, { key: "Escape" });

    expect(tip()).toBeNull();
  });
});

describe("what it is, to a screen reader", () => {
  it("describes the control rather than announcing itself", () => {
    iconButton();
    fireEvent.focus(screen.getByRole("button"));

    expect(tip()?.getAttribute("role")).toBe("tooltip");
    expect(anchor().getAttribute("aria-describedby")).toBe(tip()?.id);
  });

  it("leaves the control's own label alone", () => {
    // The tooltip is the explanation, not the name. A screen reader
    // must still hear "Show archived documents" as the button.
    iconButton();

    expect(
      screen.getByRole("button", { name: "Show archived documents" }),
    ).toBeTruthy();
  });
});

describe("where it goes", () => {
  it("is rendered on the page, not inside the toolbar", () => {
    // Portalled: a toolbar is a fixed-width row, often inside a
    // column with its own clipping, and a tooltip trapped in one is
    // a tooltip nobody can read.
    const { container } = iconButton();
    fireEvent.focus(screen.getByRole("button"));

    expect(container.querySelector(".tip")).toBeNull();
    expect(document.body.querySelector(".tip")).toBeTruthy();
  });

  it("renders nothing when there is no word to say", () => {
    iconButton("");
    fireEvent.focus(screen.getByRole("button"));

    expect(tip()).toBeNull();
  });
});

/**
 * jsdom lays nothing out, so every rectangle is zero. These give the
 * control and the bubble the boxes a browser would, which is the
 * measuring the component does and not something it is being tested
 * against.
 */
function boxes(
  control: Partial<DOMRect>,
  bubble: Partial<DOMRect> = { left: 50, right: 150 },
) {
  const rect = (r: Partial<DOMRect>) => ({
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    width: 0,
    height: 0,
    x: 0,
    y: 0,
    toJSON: () => ({}),
    ...r,
  });
  return vi
    .spyOn(Element.prototype, "getBoundingClientRect")
    .mockImplementation(function (this: Element) {
      return rect(this.classList.contains("tip") ? bubble : control);
    });
}

function tipEl() {
  return document.querySelector(".tip") as HTMLElement;
}

describe("where it sits against the control", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is centred under the control, a gap below it", () => {
    boxes({ left: 100, width: 40, top: 20, bottom: 50 });
    iconButton();

    fireEvent.focus(control());

    expect(tipEl().style.left).toBe("120px");
    expect(tipEl().style.top).toBe("58px");
    expect(tipEl().style.transform).toBe("translate(-50%, 0)");
  });

  it("goes above the control when fewer than 42px remain below it", () => {
    // 34px of bubble and the 8px gap: the fit is judged on both.
    const room = window.innerHeight - 42;
    boxes({ left: 100, width: 40, top: room - 30, bottom: room });
    iconButton();
    fireEvent.focus(control());

    expect(tipEl().style.top).toBe(`${room - 30 - 8}px`);
    expect(tipEl().style.transform).toBe("translate(-50%, -100%)");
  });

  it("stays below when exactly 43px remain", () => {
    const bottom = window.innerHeight - 43;
    boxes({ left: 100, width: 40, top: bottom - 30, bottom });
    iconButton();
    fireEvent.focus(control());

    expect(tipEl().style.top).toBe(`${bottom + 8}px`);
  });

  it("is nudged left when it would run past the right edge", () => {
    boxes(
      { left: 100, width: 40, top: 20, bottom: 50 },
      { left: 900, right: window.innerWidth + 30 },
    );
    iconButton();

    fireEvent.focus(control());

    // 30px beyond the window, and 8px of margin to keep.
    expect(tipEl().style.transform).toBe("translate(calc(-50% - 38px), 0)");
  });

  it("is nudged right when it would run past the left edge", () => {
    boxes({ left: 0, width: 4, top: 20, bottom: 50 }, { left: -20, right: 60 });
    iconButton();

    fireEvent.focus(control());

    expect(tipEl().style.transform).toBe("translate(calc(-50% + 28px), 0)");
  });

  it("keeps the lift above the control when it is nudged sideways", () => {
    const bottom = window.innerHeight;
    boxes(
      { left: 0, width: 4, top: bottom - 30, bottom },
      { left: -20, right: 60 },
    );
    iconButton();

    fireEvent.focus(control());

    expect(tipEl().style.transform).toBe("translate(calc(-50% + 28px), -100%)");
  });

  it("is left where it is when it fits inside the margins", () => {
    boxes(
      { left: 100, width: 40, top: 20, bottom: 50 },
      { left: 8, right: window.innerWidth - 8 },
    );
    iconButton();

    fireEvent.focus(control());

    expect(tipEl().style.transform).toBe("translate(-50%, 0)");
  });
});

describe("what puts it away", () => {
  it("a scroll anywhere, as the control moves out from under it", () => {
    iconButton();
    fireEvent.focus(control());

    fireEvent.scroll(document.body);

    expect(tip()).toBeNull();
  });

  it("a resize of the window", () => {
    iconButton();
    fireEvent.focus(control());

    fireEvent(window, new Event("resize"));

    expect(tip()).toBeNull();
  });

  it("is not put away by a key that is not Escape", () => {
    iconButton();
    fireEvent.focus(control());

    fireEvent.keyDown(window, { key: "a" });

    expect(tip()).toBeTruthy();
  });

  it("an unmount with the dwell still running leaves no timer behind", () => {
    vi.useFakeTimers();
    const { unmount } = iconButton();
    fireEvent.pointerEnter(control());
    expect(vi.getTimerCount()).toBe(1);

    unmount();

    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("the dwell, repeated", () => {
  it("a second enter restarts the wait rather than adding to it", () => {
    vi.useFakeTimers();
    iconButton();

    fireEvent.pointerEnter(control());
    act(() => void vi.advanceTimersByTime(200));
    fireEvent.pointerEnter(control());
    act(() => void vi.advanceTimersByTime(200));
    // 400ms since the first, 200ms since the second.
    expect(tip()).toBeNull();
    act(() => void vi.advanceTimersByTime(200));

    expect(document.querySelectorAll(".tip")).toHaveLength(1);
  });

  it("does not appear a moment before 350ms", () => {
    vi.useFakeTimers();
    iconButton();
    fireEvent.pointerEnter(control());

    act(() => void vi.advanceTimersByTime(349));
    expect(tip()).toBeNull();
    act(() => void vi.advanceTimersByTime(1));

    expect(tip()).toBeTruthy();
  });
});

describe("what it describes", () => {
  it("has no description while it is closed", () => {
    iconButton();

    expect(anchor().hasAttribute("aria-describedby")).toBe(false);
  });

  it("gives two open tooltips two different ids", () => {
    render(
      <>
        <Tooltip text="One">
          <button type="button">a</button>
        </Tooltip>
        <Tooltip text="Two">
          <button type="button">b</button>
        </Tooltip>
      </>,
    );
    for (const b of screen.getAllByRole("button")) fireEvent.focus(b);

    const ids = [...document.querySelectorAll(".tip")].map((t) => t.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
  });
});

describe("a child that is not a control", () => {
  it("text has no listeners and renders without a tooltip", () => {
    render(<Tooltip text="Word">just words</Tooltip>);

    fireEvent.focus(anchor());
    fireEvent.pointerEnter(anchor());

    expect(anchor().textContent).toBe("just words");
    expect(tip()).toBeNull();
  });
});

describe("the browser's own title", () => {
  it("is taken off the control, so the browser shows no second tooltip", () => {
    render(
      <Tooltip text="Show archived documents">
        <button type="button" title="Show archived documents">
          ▣
        </button>
      </Tooltip>,
    );

    expect(control().hasAttribute("title")).toBe(false);
  });

  it("is taken off again when the control's title changes", () => {
    const view = (title: string) => (
      <Tooltip text="Archive">
        <button type="button" title={title}>
          ▣
        </button>
      </Tooltip>
    );
    const { rerender } = render(view("one"));
    rerender(view("two"));

    expect(control().hasAttribute("title")).toBe(false);
  });

  it("is the word when the Tooltip was given none", () => {
    vi.useFakeTimers();
    render(
      <Tooltip text="">
        <button type="button" title="Show archived documents">
          ▣
        </button>
      </Tooltip>,
    );
    fireEvent.focus(control());

    expect(tip()?.textContent).toBe("Show archived documents");
    expect(control().hasAttribute("title")).toBe(false);
  });

  it("does not replace a word the Tooltip was given", () => {
    render(
      <Tooltip text="Archive">
        <button type="button" title="Something else">
          ▣
        </button>
      </Tooltip>,
    );
    fireEvent.focus(control());

    expect(tip()?.textContent).toBe("Archive");
  });
});
