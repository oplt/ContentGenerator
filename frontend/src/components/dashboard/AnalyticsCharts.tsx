import { Bar, BarChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { AnalyticsOverview } from "../../api/analytics";
import { Card } from "../ui/card";

export function AnalyticsCharts({ data }: { data: AnalyticsOverview }) {
 return (
 <div className="grid gap-6 xl:grid-cols-2">
 <Card className="p-5">
 <h3 className="text-lg font-semibold">Posts Over Time</h3>
 <div className="mt-4 h-72">
 <ResponsiveContainer width="100%" height="100%">
 <BarChart data={data.posts_over_time}>
 <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.1} />
 <XAxis dataKey="label" tick={{ fontSize: 12 }} />
 <YAxis tick={{ fontSize: 12 }} />
 <Tooltip />
 <Bar dataKey="value" fill="var(--color-chart-1, #3E6AE1)" radius={[4, 4, 0, 0]} />
 </BarChart>
 </ResponsiveContainer>
 </div>
 </Card>
 <Card className="p-5">
 <h3 className="text-lg font-semibold">Views By Platform</h3>
 <div className="mt-4 h-72">
 <ResponsiveContainer width="100%" height="100%">
 <PieChart>
 <Pie data={data.engagement_by_platform} dataKey="value" nameKey="label" outerRadius={100} fill="var(--color-chart-2, #ffa110)" />
 <Tooltip />
 </PieChart>
 </ResponsiveContainer>
 </div>
 </Card>
 {(data.engagement_by_account?.length ?? 0) > 0 ? (
 <Card className="p-5">
 <h3 className="text-lg font-semibold">Views By Account</h3>
 <div className="mt-4 h-72">
 <ResponsiveContainer width="100%" height="100%">
 <BarChart data={data.engagement_by_account}>
 <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.1} />
 <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={70} />
 <YAxis tick={{ fontSize: 12 }} />
 <Tooltip />
 <Bar dataKey="value" fill="var(--color-chart-4, #3b82f6)" radius={[4, 4, 0, 0]} />
 </BarChart>
 </ResponsiveContainer>
 </div>
 </Card>
 ) : null}
 <Card className="p-5 xl:col-span-2">
 <h3 className="text-lg font-semibold">Publishing Funnel</h3>
 <div className="mt-4 h-72">
 <ResponsiveContainer width="100%" height="100%">
 <BarChart data={data.publishing_funnel}>
 <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.1} />
 <XAxis dataKey="label" tick={{ fontSize: 12 }} />
 <YAxis tick={{ fontSize: 12 }} />
 <Tooltip />
 <Bar dataKey="value" fill="var(--color-chart-3, #2d8a5a)" radius={[4, 4, 0, 0]} />
 </BarChart>
 </ResponsiveContainer>
 </div>
 </Card>
 </div>
 );
}
