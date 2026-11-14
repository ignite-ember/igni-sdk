// @vitest-environment jsdom
/**
 * Component tests for ``OverflowMenu``.
 *
 * Collapsing four buttons behind one costs discoverability. What it
 * must not also cost is the keyboard, so most of what is asserted
 * here is that the actions are still reachable and still announce
 * what they are.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverflowMenu, type OverflowAction } from "./OverflowMenu.js";

// This project does not set ``globals: true``, so testing-library's
// automatic afterEach cleanup is never installed and renders would
// otherwise accumulate across cases in one document.
afterEach(cleanup);

const actions = (over: Partial<OverflowAction>[] = []): OverflowAction[] => {
  const base: OverflowAction[] = [
    { key: "export", label: "Export", onSelect: vi.fn() },
    { key: "share", label: "Share", onSelect: vi.fn() },
    { key: "remove", label: "Remove", danger: true, onSelect: vi.fn() },
  ];
  return base.map((a, i) => ({ ...a, ...(over[i] ?? {}) }));
};

const open = () =>
  fireEvent.click(screen.getByRole("button", { name: /actions/i }));

describe("the trigger", () => {
  it("says what it is to someone who cannot see three dots", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    const b = screen.getByRole("button", { name: "Document actions" });
    expect(b.getAttribute("aria-haspopup")).toBe("menu");
    expect(b.getAttribute("aria-expanded")).toBe("false");
  });

  it("renders nothing at all when there is nothing to offer", () => {
    // A dots button that opens an empty box is worse than no button.
    const { container } = render(<OverflowMenu actions={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("the menu", () => {
  it("offers every action once opened", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(screen.getAllByRole("menuitem").map((n) => n.textContent)).toEqual([
      "Export",
      "Share",
      "Remove",
    ]);
  });

  it("runs the action and closes", () => {
    const a = actions();
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Share" }));

    expect(a[1].onSelect).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("keeps the destructive action apart from the rest", () => {
    // One slip of the wrist below "Share" should not be "Remove".
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    expect(screen.getByRole("separator")).toBeTruthy();
  });

  it("will not run a disabled action", () => {
    const a = actions([{ disabled: true }]);
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Export" }));
    expect(a[0].onSelect).not.toHaveBeenCalled();
  });

  it("says which state a toggle is in rather than only colouring it", () => {
    const a = actions([{}, { active: true, label: "Done comparing" }]);
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    expect(
      screen
        .getByRole("menuitem", { name: "Done comparing" })
        .getAttribute("aria-current"),
    ).toBe("true");
  });
});

describe("the keyboard", () => {
  it("puts focus on the first action when it opens", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    expect(document.activeElement?.textContent).toBe("Export");
  });

  it("skips a disabled action when arrowing", () => {
    const a = actions([{ disabled: true }]);
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    expect(document.activeElement?.textContent).toBe("Share");

    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toBe("Remove");
  });

  it("wraps around the ends", () => {
    // Nothing scrolls in a menu this short, so an arrow that stops
    // dead gives no sign of why it stopped.
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowUp" });
    expect(document.activeElement?.textContent).toBe("Remove");
  });

  it("closes on Escape and hands focus back to the trigger", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });

    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Document actions" }),
    );
  });

  it("keeps Escape from reaching the page underneath", () => {
    // ``PageShell`` listens on the capture phase and navigates back.
    // Closing the menu and leaving the page on one keypress is one
    // thing too many.
    const outer = vi.fn();
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();

    document.addEventListener("keydown", outer);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    document.removeEventListener("keydown", outer);

    expect(outer).not.toHaveBeenCalled();
  });
});

describe("submenus", () => {
  const withExport = (): OverflowAction[] => [
    {
      key: "export",
      label: "Export",
      items: [
        { key: "html", label: "HTML", onSelect: vi.fn() },
        { key: "md", label: "Markdown", onSelect: vi.fn() },
      ],
    },
    { key: "share", label: "Share", onSelect: vi.fn() },
  ];

  const openSub = () =>
    fireEvent.click(screen.getByRole("menuitem", { name: "Export" }));

  it("shows the parent, not its contents, until it is opened", () => {
    // The whole point: one Export item instead of three export items.
    render(<OverflowMenu actions={withExport()} label="Document actions" />);
    open();
    expect(screen.getAllByRole("menuitem").map((n) => n.textContent)).toEqual([
      "Export",
      "Share",
    ]);
  });

  it("says it opens another menu", () => {
    render(<OverflowMenu actions={withExport()} label="Document actions" />);
    open();
    const parent = screen.getByRole("menuitem", { name: "Export" });
    expect(parent.getAttribute("aria-haspopup")).toBe("menu");
    expect(parent.getAttribute("aria-expanded")).toBe("false");
  });

  it("reveals the formats once opened", () => {
    render(<OverflowMenu actions={withExport()} label="Document actions" />);
    open();
    openSub();
    expect(screen.getByRole("menuitem", { name: "Export HTML" })).toBeTruthy();
    expect(
      screen.getByRole("menuitem", { name: "Export Markdown" }),
    ).toBeTruthy();
  });

  it("runs the chosen format and closes the whole menu", () => {
    const a = withExport();
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    openSub();
    fireEvent.click(screen.getByRole("menuitem", { name: "Export Markdown" }));

    expect(a[0].items?.[1].onSelect).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("carries the parent name into each item's announced label", () => {
    // "PDF" alone says nothing once the submenu that gave it meaning
    // has been navigated past.
    render(<OverflowMenu actions={withExport()} label="Document actions" />);
    open();
    openSub();
    expect(
      screen.getByRole("menuitem", { name: "Export HTML" }).textContent,
    ).toBe("HTML");
  });
});

describe("the submenu keyboard", () => {
  const actionsWithSub = (): OverflowAction[] => [
    {
      key: "export",
      label: "Export",
      items: [
        { key: "html", label: "HTML", onSelect: vi.fn() },
        { key: "md", label: "Markdown", onSelect: vi.fn() },
      ],
    },
    { key: "share", label: "Share", onSelect: vi.fn() },
  ];

  it("steps in on the right arrow and lands on the first format", () => {
    render(
      <OverflowMenu actions={actionsWithSub()} label="Document actions" />,
    );
    open();
    fireEvent.keyDown(screen.getByRole("menuitem", { name: "Export" }), {
      key: "ArrowRight",
    });
    expect(document.activeElement?.textContent).toBe("HTML");
  });

  it("steps back out on the left arrow, to the item that opened it", () => {
    render(
      <OverflowMenu actions={actionsWithSub()} label="Document actions" />,
    );
    open();
    fireEvent.keyDown(screen.getByRole("menuitem", { name: "Export" }), {
      key: "ArrowRight",
    });
    fireEvent.keyDown(screen.getByRole("menu", { name: "Export" }), {
      key: "ArrowLeft",
    });
    expect(document.activeElement?.textContent).toContain("Export");
  });

  it("closes one level on Escape, not the whole menu", () => {
    // Escape inside a submenu that dropped the entire menu would make
    // backing out of a mis-click cost two reopens.
    render(
      <OverflowMenu actions={actionsWithSub()} label="Document actions" />,
    );
    open();
    fireEvent.keyDown(screen.getByRole("menuitem", { name: "Export" }), {
      key: "ArrowRight",
    });
    fireEvent.keyDown(screen.getByRole("menu", { name: "Export" }), {
      key: "Escape",
    });

    expect(screen.queryByRole("menu", { name: "Export" })).toBeNull();
    expect(screen.getByRole("menu", { name: "Document actions" })).toBeTruthy();
  });

  it("arrows within the submenu, not the parent list", () => {
    render(
      <OverflowMenu actions={actionsWithSub()} label="Document actions" />,
    );
    open();
    fireEvent.keyDown(screen.getByRole("menuitem", { name: "Export" }), {
      key: "ArrowRight",
    });
    fireEvent.keyDown(screen.getByRole("menu", { name: "Export" }), {
      key: "ArrowDown",
    });
    expect(document.activeElement?.textContent).toBe("Markdown");
  });
});

describe("a disabled submenu parent", () => {
  const disabledParent = (): OverflowAction[] => [
    {
      key: "export",
      label: "Export",
      disabled: true,
      items: [{ key: "html", label: "HTML", onSelect: vi.fn() }],
    },
    { key: "share", label: "Share", onSelect: vi.fn() },
  ];

  it("does not open when the pointer moves over it", () => {
    // Hover is on the wrapper, not the button, so a disabled button
    // alone does not stop it: the formats would be one click away
    // from an action the menu says cannot be done.
    render(<OverflowMenu actions={disabledParent()} label="Document actions" />);
    open();
    const parent = screen.getByRole("menuitem", { name: "Export" });
    fireEvent.mouseEnter(parent.parentElement!);
    expect(screen.queryByRole("menuitem", { name: "Export HTML" })).toBeNull();
    expect(parent.getAttribute("aria-expanded")).toBe("false");
  });

  it("does not open on a click either", () => {
    render(<OverflowMenu actions={disabledParent()} label="Document actions" />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Export" }));
    expect(screen.queryByRole("menuitem", { name: "Export HTML" })).toBeNull();
  });
});

describe("the trigger's state", () => {
  it("points at the menu only while it is open", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    const trigger = screen.getByRole("button", { name: "Document actions" });
    expect(trigger.getAttribute("aria-controls")).toBeNull();
    open();
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(trigger.getAttribute("aria-controls")).toBe(
      screen.getByRole("menu").id,
    );
    open();
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(trigger.getAttribute("aria-controls")).toBeNull();
  });

  it("closes on a second click and hands focus back to the trigger", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    open();
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Document actions" }),
    );
  });

  it("names the menu after the trigger, and defaults to More actions", () => {
    render(<OverflowMenu actions={actions()} />);
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menu").getAttribute("aria-label")).toBe(
      "More actions",
    );
  });

  it("gives two menus on one page their own ids", () => {
    render(
      <>
        <OverflowMenu actions={actions()} label="First" />
        <OverflowMenu actions={actions()} label="Second" />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "First" }));
    fireEvent.click(screen.getByRole("button", { name: "Second" }));
    const [a, b] = screen.getAllByRole("menu");
    expect(a!.id).not.toBe(b!.id);
  });
});

describe("dismissing and picking", () => {
  it("closes on a click outside without pulling focus to the trigger", () => {
    // The click has already put focus where the user aimed it.
    const { container } = render(
      <>
        <input aria-label="elsewhere" />
        <OverflowMenu actions={actions()} label="Document actions" />
      </>,
    );
    open();
    screen.getByLabelText("elsewhere").focus();
    fireEvent.click(container.querySelector(".overflow-backdrop")!);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(screen.getByLabelText("elsewhere"));
  });

  it("closes a picked action without pulling focus to the trigger", () => {
    // Most actions replace the header the trigger lives in.
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Share" }));
    expect(document.activeElement).not.toBe(
      screen.getByRole("button", { name: "Document actions" }),
    );
  });

  it("takes an action with no onSelect", () => {
    render(
      <OverflowMenu
        actions={[{ key: "x", label: "Nothing" }]}
        label="Document actions"
      />,
    );
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Nothing" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("lists safe actions first and the danger ones after, whatever order they came in", () => {
    const a: OverflowAction[] = [
      { key: "remove", label: "Remove", danger: true },
      { key: "export", label: "Export" },
    ];
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    expect(screen.getAllByRole("menuitem").map((n) => n.textContent)).toEqual([
      "Export",
      "Remove",
    ]);
    const menu = screen.getByRole("menu");
    const kinds = [...menu.children].map((n) => n.getAttribute("role"));
    expect(kinds).toEqual(["menuitem", "separator", "menuitem"]);
  });

  it("has no separator with only danger actions, or with only safe ones", () => {
    const { unmount } = render(
      <OverflowMenu
        actions={[{ key: "r", label: "Remove", danger: true }]}
        label="Document actions"
      />,
    );
    open();
    expect(screen.queryByRole("separator")).toBeNull();
    unmount();
    render(
      <OverflowMenu
        actions={[{ key: "e", label: "Export" }]}
        label="Document actions"
      />,
    );
    open();
    expect(screen.queryByRole("separator")).toBeNull();
  });

  it("marks a danger action, and only that one", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    expect(
      screen.getByRole("menuitem", { name: "Remove" }).className,
    ).toContain("overflow-item-danger");
    expect(
      screen.getByRole("menuitem", { name: "Share" }).className,
    ).not.toContain("overflow-item-danger");
  });

  it("draws an action's icon, and only when it has one", () => {
    const a = actions([{ icon: "export" }]);
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    expect(
      screen.getByRole("menuitem", { name: "Export" }).querySelector("svg"),
    ).not.toBeNull();
    expect(
      screen.getByRole("menuitem", { name: "Share" }).querySelector("svg"),
    ).toBeNull();
  });

  it("does not move focus when every action is disabled, and arrows do nothing", () => {
    const a = actions([{ disabled: true }, { disabled: true }, { disabled: true }]);
    render(<OverflowMenu actions={a} label="Document actions" />);
    open();
    const trigger = screen.getByRole("button", { name: "Document actions" });
    trigger.focus();
    expect(fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" })).toBe(
      true,
    );
    expect(document.activeElement).toBe(trigger);
  });

  it("prevents the page's scroll on the arrows it handles", () => {
    render(<OverflowMenu actions={actions()} label="Document actions" />);
    open();
    expect(fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" })).toBe(
      false,
    );
    expect(fireEvent.keyDown(screen.getByRole("menu"), { key: "a" })).toBe(true);
  });
});

describe("submenu opening", () => {
  const sub = (): OverflowAction[] => [
    {
      key: "export",
      label: "Export",
      icon: "export",
      items: [{ key: "html", label: "HTML", onSelect: vi.fn() }],
    },
    { key: "share", label: "Share", onSelect: vi.fn() },
  ];
  const parent = () => screen.getByRole("menuitem", { name: "Export" });

  it("opens when the pointer enters and closes when it leaves", () => {
    render(<OverflowMenu actions={sub()} label="Document actions" />);
    open();
    fireEvent.mouseEnter(parent().parentElement!);
    expect(parent().getAttribute("aria-expanded")).toBe("true");
    expect(parent().getAttribute("aria-controls")).toBe(
      screen.getAllByRole("menu")[1]!.id,
    );
    fireEvent.mouseLeave(parent().parentElement!);
    expect(parent().getAttribute("aria-expanded")).toBe("false");
    expect(parent().getAttribute("aria-controls")).toBeNull();
    expect(screen.getAllByRole("menu")).toHaveLength(1);
  });

  it.each([["Enter"], [" "]])("opens on the %j key and focuses its first item", (key) => {
    render(<OverflowMenu actions={sub()} label="Document actions" />);
    open();
    fireEvent.keyDown(parent(), { key });
    expect(document.activeElement?.textContent).toBe("HTML");
  });

  it("closes on a second click on the parent", () => {
    render(<OverflowMenu actions={sub()} label="Document actions" />);
    open();
    fireEvent.click(parent());
    fireEvent.click(parent());
    expect(screen.getAllByRole("menu")).toHaveLength(1);
  });

  it("draws the parent's icon", () => {
    render(<OverflowMenu actions={sub()} label="Document actions" />);
    open();
    // The icon and the chevron.
    expect(parent().querySelectorAll("svg")).toHaveLength(2);
  });

  it("is a plain item when items is an empty list", () => {
    const onSelect = vi.fn();
    render(
      <OverflowMenu
        actions={[{ key: "e", label: "Export", items: [], onSelect }]}
        label="Document actions"
      />,
    );
    open();
    const item = screen.getByRole("menuitem", { name: "Export" });
    expect(item.getAttribute("aria-haspopup")).toBeNull();
    fireEvent.click(item);
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
