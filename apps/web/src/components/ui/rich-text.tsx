/** Content-source text with `backtick` spans rendered as code. */
export function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) =>
        i % 2 ? (
          <code key={i} className="font-mono text-fg">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}
