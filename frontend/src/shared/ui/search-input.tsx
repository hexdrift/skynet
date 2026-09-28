import type { ComponentProps } from "react";

import { CircleNotch, MagnifyingGlass } from "@/shared/ui/icons";
import { Input } from "@/shared/ui/primitives/input";
import { TOUCH_FIELD, TOUCH_FIELD_SM } from "@/shared/ui/touch";
import { cn } from "@/shared/lib/utils";

/**
 * A form-field search box: the Input surface with a trailing magnifier that
 * turns into a spinner while ``busy``. ``size="sm"`` fits popovers and
 * drawer headers.
 */
export function SearchInput({
  size = "default",
  busy = false,
  className,
  ...props
}: Omit<ComponentProps<"input">, "size"> & {
  size?: "default" | "sm";
  busy?: boolean;
}) {
  const sm = size === "sm";
  const iconClass = sm ? "size-3.5" : "size-4";
  return (
    <div className="relative">
      <Input
        {...props}
        className={cn(sm ? TOUCH_FIELD_SM : TOUCH_FIELD, sm ? "pe-8" : "pe-9", className)}
      />
      <span
        className={cn(
          "pointer-events-none absolute top-1/2 -translate-y-1/2 text-muted-foreground",
          sm ? "end-2.5" : "end-3",
        )}
        aria-hidden="true"
      >
        {busy ? (
          <CircleNotch className={cn(iconClass, "animate-spin")} />
        ) : (
          <MagnifyingGlass className={iconClass} />
        )}
      </span>
    </div>
  );
}
