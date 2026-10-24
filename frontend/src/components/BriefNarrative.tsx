import { Fragment } from "react";

const plainText = (value: string) =>
  value.replace(/\*\*(.*?)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1");

export default function BriefNarrative({ text }: { text: string }) {
  return (
    <div className="brief-narrative">
      {text
        .split(/\n\s*\n/)
        .filter(Boolean)
        .map((block, index) => {
          const [first, ...rest] = block.split("\n");
          const heading = first.match(/^(?:\*\*(.+)\*\*|#{1,3}\s+(.+))$/);
          return heading ? (
            <Fragment key={index}>
              <h3>{plainText(heading[1] || heading[2])}</h3>
              {rest.length > 0 && <p>{plainText(rest.join("\n"))}</p>}
            </Fragment>
          ) : (
            <p key={index}>{plainText(block)}</p>
          );
        })}
    </div>
  );
}
