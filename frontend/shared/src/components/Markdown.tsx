import { Fragment, type ReactNode } from "react";

/** Small Markdown renderer for the knowledge-base articles (headings, lists,
 * tables, bold, inline code). The articles are our own files, so no HTML is
 * passed through. */

/**
 * Heading text to a URL-friendly id ("Refund policy" -> "refund-policy"), used to link to a section.
 */
export function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

/**
 * Inline formatting: **bold** and `code`. The split keeps the markers so each part can be checked.
 */
function inline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/**
 * Reads the text line by line and builds React elements: headings, tables, lists, then paragraphs.
 * `highlight` marks one heading (the section a search result points to).
 */
export function Markdown({ text, highlight }: { text: string; highlight?: string }) {
  const lines = text.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    // Heading: 1 to 3 "#" signs.
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const content = heading[2];
      const Tag = (`h${level}` as unknown) as "h1";
      const marked = highlight && slug(content) === highlight;
      blocks.push(
        <Tag key={i} id={slug(content)} className={marked ? "rounded-lg bg-[var(--brand-soft)] px-2 py-1" : undefined}>
          {inline(content)}
        </Tag>,
      );
      i += 1;
      continue;
    }
    // Table: lines starting with "|". The "|---|" separator line is skipped; the first row is the header.
    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].split("|").slice(1, -1).map((c) => c.trim());
        if (!cells.every((c) => /^:?-+:?$/.test(c))) rows.push(cells);
        i += 1;
      }
      const [head, ...body] = rows;
      blocks.push(
        <div key={i} className="overflow-x-auto">
          <table>
            <thead>
              <tr>{head?.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr>
            </thead>
            <tbody>
              {body.map((row, r) => (
                <tr key={r}>{row.map((c, j) => <td key={j}>{inline(c)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    // List: bullet lines ("-" or "*") or numbered lines ("1.").
    const bullet = /^\s*[-*]\s+/;
    const numbered = /^\s*\d+\.\s+/;
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line);
      const items: string[] = [];
      while (i < lines.length && (ordered ? numbered : bullet).test(lines[i])) {
        items.push(lines[i].replace(ordered ? numbered : bullet, ""));
        i += 1;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={i}>
          {items.map((item, j) => (
            <li key={j}>{inline(item)}</li>
          ))}
        </List>,
      );
      continue;
    }
    // Paragraph: the following lines, until a blank line or the start of another block.
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|\||\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={i}>{inline(paragraph.join(" "))}</p>);
  }
  return <div className="prose-kb">{blocks}</div>;
}
