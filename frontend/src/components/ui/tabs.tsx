import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "../../lib/utils";

export function Tabs(props: TabsPrimitive.TabsProps) {
  return <TabsPrimitive.Root {...props} />;
}

export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List
      className={cn("inline-flex gap-1 border-b border-border text-muted-foreground", className)}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "px-3 py-2 text-sm font-medium tracking-normal transition-colors duration-300",
        "data-[state=active]:border-b-2 data-[state=active]:border-foreground data-[state=active]:text-foreground",
        "data-[state=inactive]:text-muted-foreground data-[state=inactive]:hover:text-foreground",
        className
      )}
      {...props}
    />
  );
}

export function TabsContent(props: TabsPrimitive.TabsContentProps) {
  return <TabsPrimitive.Content {...props} />;
}
