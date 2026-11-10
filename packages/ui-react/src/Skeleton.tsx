import type { CSSProperties } from "react";

/**
 * Animated placeholder block. Render at the same approximate size
 * and rhythm as the eventual content so the layout doesn't jump
 * when async data lands.
 *
 * Usage:
 *   <Skeleton.Line width="60%" />
 *   <Skeleton.Block height={64} />
 *   <Skeleton.Circle size={48} />
 */
export const Skeleton = {
  /**
   * A line of placeholder text, the size of the line it stands in for.
   *
   * @param width — how wide the line is, in pixels or as a CSS length.
   * @param height — how tall the line is, in pixels or as a CSS length.
   * @param style — the element's inline style, merged over the
   *   defaults.
   */
  Line({
    width = "100%",
    height = 12,
    style,
  }: {
    width?: number | string;
    height?: number | string;
    style?: CSSProperties;
  }) {
    return (
      <span
        className="skeleton skeleton-text"
        style={{ display: "block", width, height, ...style }}
      />
    );
  },
  /**
   * A block of placeholder content, the size of the content it stands in for.
   *
   * @param height — how tall the block is, in pixels or as a CSS
   *   length.
   * @param width — how wide the block is, in pixels or as a CSS length.
   * @param style — the element's inline style, merged over the
   *   defaults.
   */
  Block({
    height = 64,
    width = "100%",
    style,
  }: {
    height?: number | string;
    width?: number | string;
    style?: CSSProperties;
  }) {
    return (
      <span
        className="skeleton skeleton-block"
        style={{ display: "block", height, width, ...style }}
      />
    );
  },
  /**
   * A circle, the size of the thing it stands in for.
   *
   * @param size — the diameter of the circle, in pixels.
   * @param style — the element's inline style, merged over the
   *   defaults.
   */
  Circle({ size = 24, style }: { size?: number; style?: CSSProperties }) {
    return (
      <span
        className="skeleton skeleton-circle"
        style={{ display: "inline-block", width: size, height: size, ...style }}
      />
    );
  },
  /**
   * Several lines of placeholder text, the shape of the list they stand in for.
   *
   * @param count — how many rows of text to draw.
   * @param style — the stack's inline style, merged over the defaults.
   */
  Rows({ count = 4, style }: { count?: number; style?: CSSProperties }) {
    return (
      <div
        style={{ display: "flex", flexDirection: "column", gap: 12, ...style }}
      >
        {Array.from({ length: count }).map((_, i) => (
          <div key={i}>
            <Skeleton.Line width="40%" height={11} />
            <Skeleton.Line width="100%" />
          </div>
        ))}
      </div>
    );
  },
};
