import * as React from "react"
import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
 return (
 <textarea
 data-slot="textarea"
 className={cn(
 "w-full min-h-[80px] rounded-xl border border-input/90 bg-background/75 px-3 py-2 text-base shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-sm transition-[color,box-shadow,border-color] outline-none selection:bg-primary selection:text-primary-foreground placeholder:text-muted-foreground/90 disabled:pointer-events-none disabled:opacity-50 md:text-sm",
 "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
 "aria-invalid:border-destructive aria-invalid:ring-destructive/20",
 "font-mono text-sm leading-relaxed",
 className
 )}
 {...props}
 />
 )
}

export { Textarea }
