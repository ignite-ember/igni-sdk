/** A release's comments, as cards. */

import { Badge, Empty, List, Monogram, Row, Text } from "@ignite-ember/ui-react";

import type { Comment } from "./notes";

export function CommentList({ comments }: { comments: Comment[] }) {
  if (comments.length === 0) return <Empty>No comments yet.</Empty>;
  return (
    <List>
      {comments.map((comment) => (
        <div key={comment.id} className="ui-card comment">
          <Row>
            <Monogram name={comment.author} />
            <Text>{comment.author}</Text>
            {comment.resolved ? <Badge tone="success">resolved</Badge> : null}
          </Row>
          <Text>{comment.body}</Text>
        </div>
      ))}
    </List>
  );
}
