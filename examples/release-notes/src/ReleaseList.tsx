/**
 * The left pane.
 *
 * `aria-selected` rather than a class: the published rule is keyed on
 * the attribute, so what makes a row look picked is what makes it
 * announce as picked and the two cannot disagree.
 */

import { Badge, Empty, Item, List, Row, Text, type Tone } from "@ignite-ember/ui-react";

import type { Release, ReleaseState } from "./notes";

/** State maps onto the floor's four tones, not onto our colours. */
const TONE: Record<ReleaseState, Tone> = {
  draft: "neutral",
  published: "success",
  superseded: "warning",
};

export function ReleaseList({
  releases,
  selected,
  onPick,
  loading,
}: {
  releases: Release[];
  selected: string | null;
  onPick: (version: string) => void;
  loading: boolean;
}) {
  if (loading) return <Text tone="muted">Loading…</Text>;
  if (releases.length === 0) return <Empty>No releases yet.</Empty>;

  return (
    <List>
      {releases.map((release) => (
        <Item
          key={release.version}
          aria-selected={release.version === selected}
          onClick={() => onPick(release.version)}
        >
          <Row>
            <span>{release.version}</span>
            <Badge tone={TONE[release.state]}>{release.state}</Badge>
          </Row>
        </Item>
      ))}
    </List>
  );
}
