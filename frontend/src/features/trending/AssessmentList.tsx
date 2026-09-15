export type AssessmentListProps = {
 label: string;
 items: string[];
};

export function AssessmentList({ label, items }: AssessmentListProps) {
 if (items.length === 0) {
 return null;
 }

 return (
 <div className="bg-muted p-4" style={{ borderRadius: "var(--radius-sm)" }}>
 <p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p>
 <div className="flex flex-col gap-2">
 {items.slice(0, 3).map((item) => (
 <p key={item} className="text-xs text-foreground leading-relaxed">
 {item}
 </p>
 ))}
 </div>
 </div>
 );
}
