import { NavLink } from "react-router-dom";
import { cn } from "../../lib/utils";
import { useNavRoutes } from "../../navigation/useNavRoutes";

export function Sidebar() {
  const visibleItems = useNavRoutes();

  return (
    <aside className="hidden w-64 flex-col border-r border-border bg-card px-4 py-6 lg:flex">
      <div className="px-2">
        <div className="h-1 w-full block-gradient mb-4" />
        <p className="eyebrow text-primary">SignalForge</p>
        <h1 className="mt-2 text-lg text-foreground">AI Content Operations</h1>
        <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
          Ingest signals, brief, approve, publish, and track.
        </p>
      </div>

      <nav aria-label="Primary" className="mt-6 flex-1 space-y-0.5">
        {visibleItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex min-h-11 items-center gap-3 px-3 py-2.5 text-sm transition-colors",
                isActive
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )
            }
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            <item.icon className="size-4 shrink-0" aria-hidden />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
