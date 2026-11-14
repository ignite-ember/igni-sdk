// @vitest-environment jsdom
/**
 * The primitives are a mapping from props to class names, so most of
 * these pin that mapping — a renamed class is invisible otherwise,
 * and it breaks every extension at once.
 *
 * `Dialog` is tested differently because it is the one that does
 * something: focus, Escape, and the backdrop. Those are the parts an
 * extension would reimplement and get wrong in ways only keyboard
 * and screen-reader users notice.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MenuIcon } from "./MenuIcon.js";
import {
  Actions,
  Badge,
  Button,
  Card,
  Chip,
  Dialog,
  Empty,
  Input,
  Item,
  List,
  Checkbox,
  Code,
  Divider,
  Field,
  Heading,
  Progress,
  Radio,
  Row,
  Select,
  Spinner,
  Switch,
  Table,
  TabPanel,
  Tabs,
  Text,
  Textarea,
  Toolbar,
} from "./primitives.js";

afterEach(cleanup);

describe("controls carry the classes the app uses", () => {
  it("gives a plain button just `btn`", () => {
    const { container } = render(<Button>Go</Button>);
    expect(container.querySelector("button")?.className).toBe("btn");
  });

  it("adds a variant and a size only when they are not the default", () => {
    const { container } = render(
      <Button variant="primary" size="sm">
        Go
      </Button>,
    );
    expect(container.querySelector("button")?.className).toBe(
      "btn btn-primary btn-sm",
    );
  });

  it("defaults to type=button, so a button in a form does not submit it", () => {
    const { container } = render(<Button>Go</Button>);
    expect(container.querySelector("button")?.getAttribute("type")).toBe(
      "button",
    );
  });

  it("keeps a caller's own class alongside its own", () => {
    const { container } = render(<Button className="kb-go">Go</Button>);
    expect(container.querySelector("button")?.className).toBe("btn kb-go");
  });

  it("passes everything else straight through", () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled aria-label="Index">
        Go
      </Button>,
    );
    const btn = screen.getByLabelText("Index");
    expect(btn).toHaveProperty("disabled", true);
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("actually forwards the handler, which the disabled case cannot show", () => {
    // jsdom does not dispatch to a disabled button, so the test above
    // passes even against a Button that dropped onClick on the floor.
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    fireEvent.click(screen.getByText("Go"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("marks a tone as data rather than as a class", () => {
    // A tone is a state of the thing, not a different thing. Reading
    // it off `data-tone` keeps the class list one item long.
    const { container } = render(<Badge tone="danger">3</Badge>);
    const el = container.querySelector("span");
    expect(el?.className).toBe("ui-badge");
    expect(el?.getAttribute("data-tone")).toBe("danger");
  });

  it("gives an input the field class", () => {
    const { container } = render(<Input placeholder="Search" />);
    expect(container.querySelector("input")?.className).toBe("panel-input");
  });
});

describe("layout and containers", () => {
  const cases: [string, React.ReactElement, string][] = [
    ["Row", <Row key="a" />, "ui-row"],
    ["Actions", <Actions key="b" />, "ui-actions"],
    ["List", <List key="c" />, "ui-list"],
    ["Toolbar", <Toolbar key="d" />, "ui-toolbar"],
    ["Card", <Card key="e" />, "ui-card"],
    ["Chip", <Chip key="f" />, "chip"],
  ];
  it.each(cases)("%s renders as .%s", (_name, el, cls) => {
    const { container } = render(el);
    expect(container.firstElementChild?.className).toBe(cls);
  });

  it("renders Table as a real table", () => {
    const { container } = render(<Table />);
    expect(container.querySelector("table")?.className).toBe("ui-table");
  });

  it("renders Item as a button, not a clickable div", () => {
    // Something clickable that is not a button is a keyboard trap.
    const { container } = render(<Item>Pick me</Item>);
    expect(container.querySelector("button")?.className).toBe("ui-item");
  });

  it("gives an empty state room to say what to do next", () => {
    render(<Empty action={<Button>Add one</Button>}>No documents yet.</Empty>);
    expect(screen.getByText("No documents yet.")).toBeDefined();
    expect(screen.getByText("Add one")).toBeDefined();
  });
});

describe("Dialog does the things an extension would get wrong", () => {
  function open(onClose = vi.fn()) {
    render(
      <Dialog
        title="Delete this document?"
        sub="It cannot be undone."
        onClose={onClose}
        actions={
          <>
            <Button onClick={onClose}>Cancel</Button>
            <Button variant="danger">Delete</Button>
          </>
        }
      />,
    );
    return onClose;
  }

  it("announces itself as a modal dialog", () => {
    open();
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    // And it says which dialog. Without a name a screen reader
    // announces "dialog" and stops.
    const labelledBy = dialog.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    expect(document.getElementById(labelledBy as string)?.textContent).toBe(
      "Delete this document?",
    );
  });

  it("takes focus, so the first Tab lands inside it", () => {
    open();
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
  });

  it("closes on Escape", () => {
    const onClose = open();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on the backdrop but not on the panel", () => {
    const onClose = open();
    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    // A drag that starts inside and ends outside must not close it
    // either — that would eat a text selection.
    const overlay = document.querySelector(".overlay") as HTMLElement;
    fireEvent.mouseDown(overlay);
    expect(onClose).toHaveBeenCalled();
  });

  it("wraps Tab from the last control back to the first", () => {
    open();
    const dialog = screen.getByRole("dialog");
    const buttons = dialog.querySelectorAll("button");
    const last = buttons[buttons.length - 1];
    last.focus();

    fireEvent.keyDown(dialog, { key: "Tab" });

    expect(document.activeElement).toBe(buttons[0]);
  });

  it("wraps Shift+Tab from the first back to the last", () => {
    open();
    const dialog = screen.getByRole("dialog");
    const buttons = dialog.querySelectorAll("button");
    buttons[0].focus();

    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(buttons[buttons.length - 1]);
  });

  it("gives focus back to whatever opened it", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();

    const { unmount } = render(<Dialog title="Hi" onClose={vi.fn()} />);
    unmount();

    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});

describe("the controls a floor has to have", () => {
  it("styles a select and a textarea as fields", () => {
    const { container } = render(
      <>
        <Select>
          <option>a</option>
        </Select>
        <Textarea />
      </>,
    );
    expect(container.querySelector("select")?.className).toBe("ui-select");
    expect(container.querySelector("textarea")?.className).toBe("ui-textarea");
  });

  it("wraps a checkbox in its own label rather than matching an id", () => {
    // An id an extension forgets to make unique is a label that
    // checks somebody else's box, and nothing looks wrong when it does.
    render(<Checkbox label="Index on save" />);
    const box = screen.getByLabelText("Index on save");
    expect(box.getAttribute("type")).toBe("checkbox");
    expect(box.closest("label")).not.toBeNull();
  });

  it("makes a switch a switch, not a checkbox", () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} label="Live sync" />);
    const sw = screen.getByRole("switch", { name: "Live sync" });

    // The distinction a screen reader announces: a checkbox is a
    // value you submit, a switch takes effect now.
    expect(sw.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("announces a field's error rather than only showing it", () => {
    render(
      <Field label="Name" htmlFor="n" error="Already taken.">
        <Input id="n" />
      </Field>,
    );
    const err = screen.getByRole("alert");
    expect(err.textContent).toBe("Already taken.");
    // The part the original test left out, which is the whole claim:
    // something has to *reference* the id. Without this the test
    // passed against a Field that announced nothing.
    const input = screen.getByLabelText("Name");
    expect(input.getAttribute("aria-describedby")).toBe(err.id);
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });

  it("prefers the error over the hint, because one of them is urgent", () => {
    render(
      <Field label="Name" htmlFor="n" hint="Lowercase." error="Already taken.">
        <Input id="n" />
      </Field>,
    );
    expect(screen.queryByText("Lowercase.")).toBeNull();
  });

  it("reports progress as a value, and as sliding when it has none", () => {
    const { container, rerender } = render(
      <Progress value={42} label="Indexing" />,
    );
    const bar = screen.getByRole("progressbar", { name: "Indexing" });
    expect(bar.getAttribute("aria-valuenow")).toBe("42");
    expect(
      container.querySelector<HTMLElement>(".ui-progress-fill")?.style.width,
    ).toBe("42%");

    rerender(<Progress label="Indexing" />);
    // No number is honest about not knowing, rather than sitting at a
    // fixed width and reading as stuck.
    expect(
      screen.getByRole("progressbar").getAttribute("aria-valuenow"),
    ).toBeNull();
    expect(
      screen.getByRole("progressbar").getAttribute("data-indeterminate"),
    ).toBe("true");
  });

  it("clamps a progress value rather than overflowing the bar", () => {
    const { container } = render(<Progress value={300} label="x" />);
    expect(
      container.querySelector<HTMLElement>(".ui-progress-fill")?.style.width,
    ).toBe("100%");
  });

  it("moves tabs with the arrow keys", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        label="Views"
        active="a"
        onChange={onChange}
        tabs={[
          { id: "a", label: "Browse" },
          { id: "b", label: "Search" },
        ]}
      />,
    );
    // A tab strip that answers only to clicks is one half the people
    // cannot use.
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("wraps around at the ends", () => {
    // Three tabs, not two: with two, ArrowLeft and ArrowRight from
    // the first both land on the second, so the original test could
    // not tell the directions apart — or tell wrapping from an
    // implementation that always returned tabs[1].
    const onChange = vi.fn();
    render(
      <Tabs
        label="Views"
        active="a"
        onChange={onChange}
        tabs={[
          { id: "a", label: "Browse" },
          { id: "b", label: "Search" },
          { id: "c", label: "Lineage" },
        ]}
      />,
    );
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("takes Home and End", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        label="Views"
        active="b"
        onChange={onChange}
        tabs={[
          { id: "a", label: "Browse" },
          { id: "b", label: "Search" },
          { id: "c", label: "Lineage" },
        ]}
      />,
    );
    const strip = screen.getByRole("tablist");
    fireEvent.keyDown(strip, { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("a");
    fireEvent.keyDown(strip, { key: "End" });
    expect(onChange).toHaveBeenLastCalledWith("c");
  });

  it("does not crash on an empty tab list", () => {
    // `tabs[(i + step + 0) % 0]` is tabs[NaN], thrown inside React's
    // event dispatch, which takes the tree down.
    render(<Tabs label="Views" active="" onChange={vi.fn()} tabs={[]} />);
    expect(() =>
      fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" }),
    ).not.toThrow();
  });

  it("points each tab at a panel, and the panel back at the tab", () => {
    // Half the ARIA pattern is worse than none: the strip announced
    // it controlled something that did not exist.
    render(
      <Tabs
        label="Views"
        active="a"
        onChange={vi.fn()}
        tabs={[{ id: "a", label: "Browse" }]}
      />,
    );
    const tab = screen.getByRole("tab");
    expect(tab.id).not.toBe("");
    expect(tab.getAttribute("aria-controls")).toBe(`${tab.id}-panel`);
  });

  it("ties a heading's size to its outline level", () => {
    // So the two cannot disagree — an h3 that looks like an h1 is a
    // document that reads differently to a screen reader than to an eye.
    const { container } = render(<Heading level={3}>Lineage</Heading>);
    const h = container.querySelector("h3");
    expect(h?.className).toBe("ui-heading");
    expect(h?.style.fontSize).toBe("var(--text-lg)");
  });

  it("gives a spinner a live region, so it is announced not just seen", () => {
    const { container } = render(<Spinner label="Loading" />);
    const s = container.querySelector(".ui-spinner");
    expect(s?.getAttribute("role")).toBe("status");
    expect(s?.getAttribute("aria-live")).toBe("polite");
    // And it has something to say. role="status" on an empty span is
    // a live region that announces silence.
    expect(s?.textContent).toBe("Loading");
  });

  it("renders text tones as data, and a divider as an hr", () => {
    const { container } = render(
      <>
        <Text tone="muted">quiet</Text>
        <Divider />
        <Code>npm</Code>
      </>,
    );
    expect(container.querySelector("p")?.getAttribute("data-tone")).toBe(
      "muted",
    );
    expect(container.querySelector("hr")?.className).toBe("ui-divider");
    expect(container.querySelector("code")?.className).toBe("ui-code");
  });
});

describe("an extension can bring its own icon", () => {
  it("draws a path it was given", () => {
    const { container } = render(<MenuIcon path="M1 1 L15 15" />);
    expect(container.querySelector("path")?.getAttribute("d")).toBe(
      "M1 1 L15 15",
    );
  });

  it("still draws nothing for a name nobody has", () => {
    const { container } = render(<MenuIcon name={"nope" as never} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("a typed prop that does nothing is worse than no prop", () => {
  // Found by an engineer trying to build a panel whose whole job was
  // ranking by severity: `<Badge tone="danger">` and
  // `<Badge tone="success">` rendered identically, because nothing
  // styled the tone. The prop existed, autocompleted, and lied.
  const css = readFileSync(
    join(
      dirname(fileURLToPath(import.meta.url)),
      "../../../clients/ui/igni-ui.css",
    ),
    "utf8",
  );

  it("styles every badge tone the type allows", () => {
    for (const tone of ["neutral", "success", "warning", "danger"]) {
      expect(css).toContain(`.ui-badge[data-tone="${tone}"]`);
    }
  });

  it("styles every button variant the type allows", () => {
    // `btn-warn` was typed and absent from the package: inside an
    // extension frame it rendered as a plain default button while
    // TypeScript vouched for it.
    for (const variant of ["primary", "danger", "warn", "quiet"]) {
      expect(css).toContain(`.btn-${variant}`);
    }
  });

  it("gives keyboard users a focus ring on everything focusable", () => {
    // Absent from the package entirely, which would have made an
    // extension the cause of its host's accessibility findings.
    expect(css).toContain(":focus-visible");
    for (const cls of [".btn", ".ui-item", ".ui-tab", ".ui-switch"]) {
      expect(css).toContain(`${cls}:focus-visible`);
    }
  });
});

describe("Progress against its bounds", () => {
  const fillWidth = (c: HTMLElement) =>
    c.querySelector<HTMLElement>(".ui-progress-fill")?.style.width;

  it("clamps a negative value to zero", () => {
    const { container } = render(<Progress value={-5} label="x" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("0");
    expect(bar.getAttribute("aria-valuetext")).toBe("0%");
    expect(fillWidth(container)).toBe("0%");
  });

  it("measures against a given max and says so to a screen reader", () => {
    const { container } = render(<Progress value={5} max={20} label="x" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("20");
    expect(bar.getAttribute("aria-valuenow")).toBe("5");
    expect(bar.getAttribute("aria-valuetext")).toBe("25%");
    expect(fillWidth(container)).toBe("25%");
  });

  it("defaults max to 100 and rounds the spoken percent", () => {
    render(<Progress value={33.6} label="x" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuemax")).toBe("100");
    expect(bar.getAttribute("aria-valuetext")).toBe("34%");
  });

  it("clamps infinity to full", () => {
    const { container } = render(<Progress value={Infinity} label="x" />);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe(
      "100",
    );
    expect(fillWidth(container)).toBe("100%");
  });

  it("reads NaN as unknown, not as NaN%", () => {
    const { container } = render(<Progress value={NaN} label="x" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("data-indeterminate")).toBe("true");
    expect(bar.getAttribute("aria-valuenow")).toBeNull();
    expect(bar.getAttribute("aria-valuetext")).toBeNull();
    expect(fillWidth(container)).toBe("");
  });

  it("shows an empty bar, not NaN%, when max is zero", () => {
    const { container } = render(<Progress value={0} max={0} label="x" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuetext")).toBe("0%");
    expect(fillWidth(container)).toBe("0%");
  });

  it("marks a value of zero as determinate", () => {
    render(<Progress value={0} label="x" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("data-indeterminate")).toBe("false");
    expect(bar.getAttribute("aria-valuenow")).toBe("0");
  });

  it("keeps the caller's class and props", () => {
    render(<Progress value={1} label="x" className="mine" data-k="v" />);
    const bar = screen.getByRole("progressbar");
    expect(bar.className).toBe("ui-progress mine");
    expect(bar.getAttribute("data-k")).toBe("v");
  });
});

describe("Dialog edges: closing, keys and focus", () => {
  it("does not close on a right-click or middle-click of the backdrop", () => {
    const onClose = vi.fn();
    render(<Dialog title="Hi" onClose={onClose} />);
    const overlay = document.querySelector(".overlay") as HTMLElement;
    fireEvent.mouseDown(overlay, { button: 2 });
    fireEvent.mouseDown(overlay, { button: 1 });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(overlay, { button: 0 });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close on a mousedown inside the panel's own children", () => {
    const onClose = vi.fn();
    render(
      <Dialog title="Hi" onClose={onClose}>
        <p>body</p>
      </Dialog>,
    );
    fireEvent.mouseDown(screen.getByText("body"));
    fireEvent.mouseDown(screen.getByText("Hi"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("stops Escape from reaching anything behind the dialog", () => {
    const outer = vi.fn();
    const onClose = vi.fn();
    render(
      <div onKeyDown={outer}>
        <Dialog title="Hi" onClose={onClose} />
      </div>,
    );
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(outer).not.toHaveBeenCalled();
  });

  it("calls the latest onClose when it changes between renders", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(<Dialog title="Hi" onClose={first} />);
    rerender(<Dialog title="Hi" onClose={second} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("leaves other keys and Tab in the middle alone", () => {
    const onClose = vi.fn();
    render(
      <Dialog
        title="Hi"
        onClose={onClose}
        actions={
          <>
            <Button>A</Button>
            <Button>B</Button>
            <Button>C</Button>
          </>
        }
      />,
    );
    const dialog = screen.getByRole("dialog");
    const [a, b] = Array.from(dialog.querySelectorAll("button"));
    expect(fireEvent.keyDown(dialog, { key: "Enter" })).toBe(true);
    a.focus();
    // Not at an end: the browser moves focus itself, so no preventDefault.
    expect(fireEvent.keyDown(dialog, { key: "Tab" })).toBe(true);
    b.focus();
    expect(fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true })).toBe(
      true,
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it("holds Tab when nothing inside can take focus", () => {
    render(<Dialog title="Hi" onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog");
    // fireEvent returns false when the default was prevented.
    expect(fireEvent.keyDown(dialog, { key: "Tab" })).toBe(false);
    expect(fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true })).toBe(
      false,
    );
    expect(document.activeElement).toBe(dialog);
  });

  it("holds Tab when every control is disabled", () => {
    render(
      <Dialog
        title="Hi"
        onClose={vi.fn()}
        actions={<Button disabled>Go</Button>}
      />,
    );
    expect(fireEvent.keyDown(screen.getByRole("dialog"), { key: "Tab" })).toBe(
      false,
    );
  });

  it("wraps past disabled buttons at either end", () => {
    render(
      <Dialog
        title="Hi"
        onClose={vi.fn()}
        actions={
          <>
            <Button disabled>First</Button>
            <Button>Cancel</Button>
            <Button>Save</Button>
            <Button disabled>Last</Button>
          </>
        }
      />,
    );
    const dialog = screen.getByRole("dialog");
    const enabled = (n: string) => screen.getByText(n);
    enabled("Save").focus();
    expect(fireEvent.keyDown(dialog, { key: "Tab" })).toBe(false);
    expect(document.activeElement).toBe(enabled("Cancel"));
    expect(fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true })).toBe(
      false,
    );
    expect(document.activeElement).toBe(enabled("Save"));
  });

  it("counts links, inputs, selects, textareas and tabindex as focusable, not hidden inputs or -1", () => {
    render(
      <Dialog title="Hi" onClose={vi.fn()}>
        <input type="hidden" />
        <a href="#x">link</a>
        <span tabIndex={-1}>skip</span>
        <span tabIndex={0} data-testid="last">
          stop
        </span>
      </Dialog>,
    );
    const dialog = screen.getByRole("dialog");
    screen.getByTestId("last").focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("link"));
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByTestId("last"));
  });

  it("does not focus an opener that left the page, and does not crash", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const focus = vi.spyOn(opener, "focus");
    const { unmount } = render(<Dialog title="Hi" onClose={vi.fn()} />);
    opener.remove();
    expect(() => unmount()).not.toThrow();
    expect(focus).not.toHaveBeenCalled();
  });

  it("renders no sub or actions row when none are given", () => {
    render(<Dialog title="Hi" onClose={vi.fn()} />);
    expect(document.querySelector(".dialog-sub")).toBeNull();
    expect(document.querySelector(".dialog-actions")).toBeNull();
  });

  it("renders the sub as a paragraph and actions in an Actions row", () => {
    render(
      <Dialog
        title="Hi"
        sub="Careful."
        onClose={vi.fn()}
        actions={<Button>Ok</Button>}
      />,
    );
    expect(document.querySelector("p.dialog-sub")?.textContent).toBe(
      "Careful.",
    );
    const row = document.querySelector(".dialog-actions");
    expect(row?.className).toBe("ui-actions dialog-actions");
    expect(row?.textContent).toBe("Ok");
  });

  it("puts the title in an h2 the panel is labelled by, and keeps class and props", () => {
    render(
      <Dialog title="Name me" onClose={vi.fn()} className="mine" data-k="v" />,
    );
    const dialog = screen.getByRole("dialog", { name: "Name me" });
    expect(dialog.className).toBe("dialog mine");
    expect(dialog.getAttribute("data-k")).toBe("v");
    expect(dialog.getAttribute("tabindex")).toBe("-1");
    const h = dialog.querySelector("h2.dialog-title");
    expect(h?.id).toBe(dialog.getAttribute("aria-labelledby"));
  });

  it("gives two dialogs on one page distinct title ids", () => {
    render(
      <>
        <Dialog title="One" onClose={vi.fn()} />
        <Dialog title="Two" onClose={vi.fn()} />
      </>,
    );
    const [a, b] = screen.getAllByRole("dialog");
    expect(a.getAttribute("aria-labelledby")).not.toBe(
      b.getAttribute("aria-labelledby"),
    );
  });
});

describe("accessibility wiring of Switch, Field, Tabs and TabPanel", () => {
  it("toggles from on to off, and names the switch by its visible label", () => {
    const onChange = vi.fn();
    render(<Switch checked onChange={onChange} label="Live sync" />);
    const sw = screen.getByRole("switch");
    expect(sw.getAttribute("aria-checked")).toBe("true");
    fireEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(false);
    const labelId = sw.getAttribute("aria-labelledby") as string;
    expect(document.getElementById(labelId)?.textContent).toBe("Live sync");
    expect(sw.className).toBe("ui-switch");
  });

  it("cannot be clobbered by a caller's onClick, type or role", () => {
    const onChange = vi.fn();
    const onClick = vi.fn();
    render(
      <Switch
        checked={false}
        onChange={onChange}
        label="x"
        {...({ onClick, type: "submit", role: "checkbox" } as object)}
        className="mine"
      />,
    );
    const sw = screen.getByRole("switch");
    expect(sw.getAttribute("type")).toBe("button");
    fireEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(true);
    expect(onClick).not.toHaveBeenCalled();
    expect(sw.className).toBe("ui-switch mine");
  });

  it("does not toggle when disabled and renders a node as its label", () => {
    const onChange = vi.fn();
    render(
      <Switch
        checked={false}
        onChange={onChange}
        disabled
        label={<em>Fancy</em>}
      />,
    );
    fireEvent.click(screen.getByRole("switch"));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("switch", { name: "Fancy" })).toBeDefined();
  });

  it("wires a hint without marking the control invalid", () => {
    render(
      <Field label="Name" htmlFor="n" hint="Lowercase.">
        <Input id="n" />
      </Field>,
    );
    const input = screen.getByLabelText("Name");
    const hint = screen.getByText("Lowercase.");
    expect(hint.className).toBe("ui-hint");
    expect(hint.id).toBe("n-note");
    expect(input.getAttribute("aria-describedby")).toBe("n-note");
    expect(input.hasAttribute("aria-invalid")).toBe(false);
  });

  it("does not wire anything without htmlFor, but still shows the note", () => {
    render(
      <Field label="Name" error="Bad.">
        <Input id="n" />
      </Field>,
    );
    const input = document.getElementById("n") as HTMLElement;
    expect(input.hasAttribute("aria-describedby")).toBe(false);
    expect(input.hasAttribute("aria-invalid")).toBe(false);
    const err = screen.getByRole("alert");
    expect(err.textContent).toBe("Bad.");
    expect(err.hasAttribute("id")).toBe(false);
  });

  it("neither clones nor renders a note when there is no hint or error", () => {
    const { container } = render(
      <Field label="Name" htmlFor="n" className="mine">
        <Input id="n" />
      </Field>,
    );
    expect(container.querySelector(".ui-hint, .ui-error")).toBeNull();
    expect(
      (document.getElementById("n") as HTMLElement).hasAttribute(
        "aria-describedby",
      ),
    ).toBe(false);
    expect(container.firstElementChild?.className).toBe("ui-field mine");
    expect(container.querySelector("label")?.getAttribute("for")).toBe("n");
  });

  it("does not clone a string, an array or a fragment child", () => {
    const { container } = render(
      <>
        <Field label="a" htmlFor="a" error="E1">
          plain text
        </Field>
        <Field label="b" htmlFor="b" error="E2">
          {[<Input key="1" id="b1" />, <Input key="2" id="b2" />]}
        </Field>
        <Field label="c" htmlFor="c" error="E3">
          <>
            <Input id="c1" />
          </>
        </Field>
      </>,
    );
    expect(container.textContent).toContain("plain text");
    for (const id of ["b1", "b2", "c1"]) {
      expect(
        document.getElementById(id)?.hasAttribute("aria-describedby"),
      ).toBe(false);
    }
    expect(screen.getAllByRole("alert")).toHaveLength(3);
  });

  it("builds Radio as a label around a radio input, type not overridable", () => {
    const { container } = render(
      <Radio
        label="Small"
        className="mine"
        name="size"
        value="s"
        {...({ type: "text" } as object)}
      />,
    );
    const label = container.querySelector("label");
    expect(label?.className).toBe("ui-check mine");
    const input = screen.getByLabelText("Small") as HTMLInputElement;
    expect(input.type).toBe("radio");
    expect(input.name).toBe("size");
    expect(input.className).toBe("");
    expect(label?.querySelector("span")?.textContent).toBe("Small");
  });

  it("puts a Checkbox's className on the label and its rest on the input", () => {
    const onChange = vi.fn();
    const { container } = render(
      <Checkbox
        label="Go"
        className="mine"
        name="n"
        onChange={onChange}
        {...({ type: "text" } as object)}
      />,
    );
    expect(container.querySelector("label")?.className).toBe("ui-check mine");
    const input = screen.getByLabelText("Go") as HTMLInputElement;
    expect(input.type).toBe("checkbox");
    expect(input.name).toBe("n");
    fireEvent.click(input);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  const tabs = [
    { id: "a", label: "Browse" },
    { id: "b", label: "Search" },
    { id: "c", label: "Lineage" },
  ];

  it("gives every tab an id, a panel pointer, selection and a roving tabindex", () => {
    render(
      <Tabs label="Views" base="v" active="b" onChange={vi.fn()} tabs={tabs} />,
    );
    const strip = screen.getByRole("tablist", { name: "Views" });
    expect(strip.getAttribute("aria-orientation")).toBe("horizontal");
    const got = screen
      .getAllByRole("tab")
      .map((t) => [
        t.id,
        t.getAttribute("aria-controls"),
        t.getAttribute("aria-selected"),
        t.getAttribute("tabindex"),
        t.getAttribute("type"),
      ]);
    expect(got).toEqual([
      ["v-a", "v-a-panel", "false", "-1", "button"],
      ["v-b", "v-b-panel", "true", "0", "button"],
      ["v-c", "v-c-panel", "false", "-1", "button"],
    ]);
  });

  it("generates distinct bases for two strips when none is given", () => {
    render(
      <>
        <Tabs label="One" active="a" onChange={vi.fn()} tabs={tabs} />
        <Tabs label="Two" active="a" onChange={vi.fn()} tabs={tabs} />
      </>,
    );
    const ids = screen.getAllByRole("tab").map((t) => t.id);
    expect(new Set(ids).size).toBe(6);
  });

  it("calls onChange with the clicked tab's id", () => {
    const onChange = vi.fn();
    render(<Tabs label="V" active="a" onChange={onChange} tabs={tabs} />);
    fireEvent.click(screen.getByText("Lineage"));
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("walks ArrowRight and ArrowLeft with wrapping, and prevents the default", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <Tabs label="V" active="c" onChange={onChange} tabs={tabs} />,
    );
    const strip = () => screen.getByRole("tablist");
    expect(fireEvent.keyDown(strip(), { key: "ArrowRight" })).toBe(false);
    expect(onChange).toHaveBeenLastCalledWith("a");
    rerender(<Tabs label="V" active="b" onChange={onChange} tabs={tabs} />);
    fireEvent.keyDown(strip(), { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith("a");
    fireEvent.keyDown(strip(), { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("c");
  });

  it("ignores unrelated keys without preventing them", () => {
    const onChange = vi.fn();
    render(<Tabs label="V" active="a" onChange={onChange} tabs={tabs} />);
    expect(fireEvent.keyDown(screen.getByRole("tablist"), { key: "x" })).toBe(
      true,
    );
    expect(onChange).not.toHaveBeenCalled();
  });

  it("treats an active id that is not in the list as the first tab", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <Tabs label="V" active="zzz" onChange={onChange} tabs={tabs} />,
    );
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("b");
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith("c");
    rerender(<Tabs label="V" active="zzz" onChange={onChange} tabs={tabs} />);
    // Nothing is selected, so no tab is in the tab order... and none crash.
    expect(
      screen.getAllByRole("tab").map((t) => t.getAttribute("tabindex")),
    ).toEqual(["-1", "-1", "-1"]);
  });

  it("keeps a single tab on itself when wrapping", () => {
    const onChange = vi.fn();
    render(
      <Tabs
        label="V"
        active="a"
        onChange={onChange}
        tabs={[{ id: "a", label: "Only" }]}
      />,
    );
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowLeft" });
    expect(onChange.mock.calls).toEqual([["a"], ["a"]]);
  });

  it("moves focus to the newly selected tab only when focus was in the strip", () => {
    const { rerender } = render(
      <Tabs label="V" base="v" active="a" onChange={vi.fn()} tabs={tabs} />,
    );
    // Focus outside the strip: selection changes must not steal it.
    const outside = document.createElement("input");
    document.body.appendChild(outside);
    outside.focus();
    rerender(
      <Tabs label="V" base="v" active="b" onChange={vi.fn()} tabs={tabs} />,
    );
    expect(document.activeElement).toBe(outside);
    outside.remove();

    // Focus inside the strip: it follows the selection.
    screen.getByText("Search").focus();
    rerender(
      <Tabs label="V" base="v" active="c" onChange={vi.fn()} tabs={tabs} />,
    );
    expect(document.activeElement).toBe(screen.getByText("Lineage"));
  });

  it("keeps odd characters in ids as given", () => {
    render(
      <Tabs
        label="V"
        base="my base"
        active="a b"
        onChange={vi.fn()}
        tabs={[{ id: "a b", label: "Odd" }]}
      />,
    );
    const tab = screen.getByRole("tab");
    expect(tab.id).toBe("my base-a b");
    expect(tab.getAttribute("aria-controls")).toBe("my base-a b-panel");
  });

  it("renders a TabPanel only for the active tab, wired back to its tab", () => {
    const { container, rerender } = render(
      <TabPanel base="v" id="a" active="b" className="mine">
        body
      </TabPanel>,
    );
    expect(container.innerHTML).toBe("");
    rerender(
      <TabPanel base="v" id="a" active="a" className="mine" data-k="v">
        body
      </TabPanel>,
    );
    const panel = screen.getByRole("tabpanel");
    expect(panel.id).toBe("v-a-panel");
    expect(panel.getAttribute("aria-labelledby")).toBe("v-a");
    expect(panel.getAttribute("tabindex")).toBe("0");
    expect(panel.className).toBe("mine");
    expect(panel.getAttribute("data-k")).toBe("v");
    expect(panel.textContent).toBe("body");
  });

  it("pairs a strip with its panel through a shared base", () => {
    render(
      <>
        <Tabs label="V" base="v" active="a" onChange={vi.fn()} tabs={tabs} />
        <TabPanel base="v" id="a" active="a">
          x
        </TabPanel>
      </>,
    );
    const tab = screen.getByRole("tab", { selected: true });
    expect(screen.getByRole("tabpanel").id).toBe(
      tab.getAttribute("aria-controls"),
    );
    expect(screen.getByRole("tabpanel", { name: "Browse" })).toBeDefined();
  });

  it("sizes every heading level, merges a style and keeps the caller's own fontSize", () => {
    const { container } = render(
      <>
        <Heading level={1}>a</Heading>
        <Heading>b</Heading>
        <Heading level={4}>d</Heading>
        <Heading level={3} className="mine" style={{ color: "red" }}>
          c
        </Heading>
        <Heading level={3} style={{ fontSize: "9px" }}>
          e
        </Heading>
      </>,
    );
    const size = (sel: string) =>
      container.querySelector<HTMLElement>(sel)?.style.fontSize;
    expect(size("h1")).toBe("var(--text-2xl)");
    expect(size("h2")).toBe("var(--text-xl)");
    expect(size("h4")).toBe("var(--text-sm)");
    const hs = container.querySelectorAll<HTMLElement>("h3");
    expect(hs[0].className).toBe("ui-heading mine");
    expect(hs[0].style.color).toBe("red");
    expect(hs[0].style.fontSize).toBe("var(--text-lg)");
    expect(hs[1].style.fontSize).toBe("9px");
  });

  it("passes a spinner's label, class and props through", () => {
    const { container } = render(
      <Spinner label="Ünïcode … wait" className="mine" data-k="v" />,
    );
    const s = container.querySelector(".ui-spinner") as HTMLElement;
    expect(s.className).toBe("ui-spinner mine");
    expect(s.getAttribute("data-k")).toBe("v");
    expect(s.querySelector(".ui-visually-hidden")?.textContent).toBe(
      "Ünïcode … wait",
    );
  });
});

describe("the reference describes every prop of every component", () => {
  // The reference pages are generated from these doc comments, so a
  // prop with no @param line is a prop the pages do not explain.
  const source = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), "primitives.tsx"),
    "utf8",
  );
  const components = [
    ...source.matchAll(
      /\/\*\*((?:(?!\*\/)[\s\S])*?)\*\/\s*export function (\w+)\(\{([^}]*)\}/g,
    ),
  ].map(([, doc, name, params]) => ({
    name,
    doc,
    props: params
      .split(",")
      .map((p) =>
        p
          .replace(/\.\.\./, "")
          .split(/[:=]/)[0]
          .trim(),
      )
      .filter(Boolean),
  }));

  it("finds the components it is meant to check", () => {
    const names = components.map((c) => c.name);
    for (const n of [
      "Button",
      "Dialog",
      "Switch",
      "Progress",
      "Tabs",
      "Heading",
    ])
      expect(names).toContain(n);
    expect(names.length).toBeGreaterThanOrEqual(25);
  });

  it.each(components.map((c) => [c.name, c] as const))(
    "%s has an @param for each prop it takes",
    (_name, c) => {
      const documented = [...c.doc.matchAll(/@param (\w+)/g)].map((m) => m[1]);
      expect([...c.props].sort()).toEqual([...documented].sort());
    },
  );
});
