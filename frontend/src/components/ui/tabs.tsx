import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "../../lib/utils";

export function Tabs(props: TabsPrimitive.TabsProps) {
  return <TabsPrimitive.Root {...props} />;
}

export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return (
    <TabsPrimitive.List
      className={cn("inline-flex rounded-xl bg-muted p-1 text-muted-foreground", className)}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "rounded-lg px-3 py-2 text-sm font-medium transition data-[state=active]:bg-card data-[state=active]:text-foreground",
        className
      )}
      {...props}
    />
  );
}

export function TabsContent(props: TabsPrimitive.TabsContentProps) {
  return <TabsPrimitive.Content {...props} />;
}
