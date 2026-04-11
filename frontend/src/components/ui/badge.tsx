import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/shared/lib/utils";

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border whitespace-nowrap transition-[color,box-shadow,background-color,border-color] shadow-[inset_0_1px_0_rgba(255,255,255,0.55)] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        default: "border-primary/20 bg-primary text-primary-foreground [a&]:hover:bg-primary/92",
        secondary:
          "border-border/60 bg-secondary text-secondary-foreground [a&]:hover:bg-secondary/90",
        destructive:
          "border-destructive/20 bg-destructive text-white focus-visible:ring-destructive/20 [a&]:hover:bg-destructive/90",
        outline:
          "border-border/70 bg-background/70 text-foreground [a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        ghost:
          "border-transparent bg-transparent [a&]:hover:bg-accent [a&]:hover:text-accent-foreground",
        link: "text-primary underline-offset-4 [a&]:hover:underline",
        // Semantic variants — monochromatic warm palette
        input: "border-[#DDD6CC]/60 bg-[#F0EBE4] text-[#5C4D40] [a&]:hover:bg-[#F0EBE4]/80",
        output:
          "border-[#C8B9A8]/60 bg-[#E5DDD4] text-[#3D2E22] font-semibold [a&]:hover:bg-[#E5DDD4]/80",
        model: "border-[#C8B9A8]/50 bg-[#DDD6CC] text-[#3D2E22] [a&]:hover:bg-[#DDD6CC]/80",
        config: "border-[#DDD6CC]/60 bg-[#EDE7DD] text-[#5C4D40] [a&]:hover:bg-[#EDE7DD]/80",
        meta: "border-[#E5DDD4]/50 bg-[#FAF8F5] text-[#8C7A6B] [a&]:hover:bg-[#FAF8F5]/80",
      },
      size: {
        sm: "px-2 py-0.5 text-[10px] font-medium",
        md: "px-2.5 py-1 text-xs font-semibold",
        lg: "px-3 py-1.5 text-sm font-semibold",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "md",
    },
  },
);

function Badge({
  className,
  variant = "default",
  size = "md",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span";

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      data-size={size}
      className={cn(badgeVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
