"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

function ScoreChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name: string; color: string }>; label?: string }) {
 if (!active || !payload?.length) return null;
 return (
 <div className="rounded-lg border bg-background p-3 shadow-md text-sm" dir="rtl">
 <p className="font-medium mb-1.5">גרסת פרומפט {label}</p>
 {payload.map((p, i) => (
 <div key={i} className="flex items-center gap-2">
 <span className="size-2.5 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
 <span className="text-muted-foreground">{p.name}:</span>
 <span className="font-mono font-bold ms-auto" dir="ltr">{p.value.toFixed(1)}</span>
 </div>
 ))}
 </div>
 );
}

export function ScoreChart({ data }: { data: Array<{ trial: number; score: number; best: number }> }) {
 return (
 <ResponsiveContainer width="100%" height="100%">
 <LineChart data={data} margin={{ top: 5, right: 10, left: 5, bottom: 18 }}>
 <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
 <XAxis dataKey="trial" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} className="fill-muted-foreground" label={{ value: "גרסת פרומפט", position: "insideBottom", offset: -12, fontSize: 10, fill: "var(--muted-foreground)" }} />
 <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10 }} className="fill-muted-foreground" label={{ value: "ציון", angle: -90, position: "insideLeft", offset: 10, fontSize: 10, fill: "var(--muted-foreground)" }} domain={[0, "auto"]} />
 <Tooltip content={<ScoreChartTooltip />} />
 <Line type="monotone" dataKey="score" name="ציון הגרסה" stroke="var(--color-chart-4)" strokeWidth={1.5} dot={{ r: 2 }} isAnimationActive={false} />
 <Line type="stepAfter" dataKey="best" name="שיא" stroke="var(--color-chart-2)" strokeWidth={2} dot={false} isAnimationActive={false} />
 </LineChart>
 </ResponsiveContainer>
 );
}
