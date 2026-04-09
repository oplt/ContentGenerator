import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "../../lib/utils";

export function Tabs(props: TabsPrimitive.TabsProps) {
  return <TabsPrimitive.Root {...props} />;
}

// Warm muted pill container — flat, no glass
export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List
      className={cn(
        "inline-flex bg-muted p-1 text-muted-foreground",
        className
      )}
      style={{ borderRadius: "var(--radius-sm)" }}
      {...props}
    />
  );
}

// Active tab: Mistral Black solid indicator on warm muted background
export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "px-4 py-2 text-sm font-normal uppercase tracking-wider transition-colors",
        "data-[state=active]:bg-foreground data-[state=active]:text-background",
        "data-[state=inactive]:text-muted-foreground data-[state=inactive]:hover:text-foreground",
        className
      )}
      style={{ borderRadius: "var(--radius-sm)" }}
      {...props}
    />
  );
}

export function TabsContent(props: TabsPrimitive.TabsContentProps) {
  return <TabsPrimitive.Content {...props} />;
}
