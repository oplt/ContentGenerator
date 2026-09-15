import { NavLink } from "react-router-dom";
import { cn } from "../../lib/utils";
import { useNavRoutes } from "../../navigation/useNavRoutes";

export function Sidebar() {
  const visibleItems = useNavRoutes();

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col overflow-y-auto border-r border-border bg-background px-3 py-6 lg:flex">
      <div className="px-3">
        <p className="text-sm font-medium tracking-[0.2em] text-foreground">SIGNALFORGE</p>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
          Content operations
        </p>
      </div>

      <nav aria-label="Primary" className="mt-8 flex-1 space-y-0.5">
        {visibleItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex min-h-8 items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors duration-300",
                isActive
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
              )
            }
          >
            <item.icon className="size-4 shrink-0" aria-hidden />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
