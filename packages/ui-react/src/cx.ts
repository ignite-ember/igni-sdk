/** Joins the class names that are set, skipping the ones that are not. */
export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
