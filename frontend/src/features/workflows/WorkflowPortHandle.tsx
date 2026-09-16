import type { WorkflowNodePort } from "../../api/workflows";

type Props = {
  direction: "input" | "output";
  ports: WorkflowNodePort[];
};

/** Port list chips for the config inspector (canvas uses React Flow Handles). */
export function WorkflowPortHandle({ direction, ports }: Props) {
  if (!ports.length) {
    return (
      <p className="text-xs text-muted-foreground">
        No {direction} ports declared.
      </p>
    );
  }
  return (
    <ul className="flex flex-wrap gap-1.5">
      {ports.map((port) => (
        <li
          key={`${direction}-${port.name}`}
          className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground"
          title={`${port.data_type}${port.required ? " · required" : " · optional"}${
            port.description ? ` — ${port.description}` : ""
          }`}
        >
          <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/70 align-middle" />
          {port.name}
          <span className="ml-1 opacity-70">{port.data_type}</span>
        </li>
      ))}
    </ul>
  );
}
