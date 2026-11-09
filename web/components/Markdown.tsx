import { Fragment, type ReactNode } from "react";

/** Just enough Markdown for check summaries and answers: paragraphs, tables, rules, **bold**,
 * `code` and [links](url). Everything is rendered as text nodes; nothing is injected as HTML. */
export function Markdown({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  return (
    <div className="markdown">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (lines.length >= 2 && /^\|.*\|$/.test(lines[0]) && /^\|[-| ]+\|$/.test(lines[1])) {
          const cells = (l: string) => l.slice(1, -1).split("|").map((c) => c.trim());
          return (
            <table key={i}>
              <thead><tr>{cells(lines[0]).map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
              <tbody>
                {lines.slice(2).map((l, r) => (
                  <tr key={r}>{cells(l).map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          );
        }
        if (block.trim() === "---") return <div key={i} className="divider" />;
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>{j > 0 ? <br /> : null}{inline(l.replace(/^- /, "• "))}</Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index! > last) out.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith("**")) out.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith("`")) out.push(<code key={key++}>{token.slice(1, -1)}</code>);
    else {
      const [, label, href] = token.match(/\[([^\]]+)\]\(([^)]+)\)/)!;
      const safe = /^(https?:\/\/|\/)/.test(href) ? href : undefined;
      out.push(<a key={key++} className="link" href={safe} target="_blank" rel="noreferrer">{label}</a>);
    }
    last = match.index! + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
