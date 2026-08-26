// Minimal classnames joiner — avoids pulling in `clsx`/`tailwind-merge`
// just for this. Falsy values are dropped, everything else joined with a
// space. Good enough for this app's conditional-class needs.
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
