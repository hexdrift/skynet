"use client";

import * as React from "react";
import { DialogDescription, DialogHeader, DialogTitle } from "@/shared/ui/primitives/dialog";

interface DialogTitleRowProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  className?: string;
}

/**
 * Bundles the common `<DialogHeader><DialogTitle>...</...><DialogDescription>...`
 * shape so simple confirm/destructive dialogs don't need to repeat it. Use the
 * raw primitives directly for layouts with icons, sr-only headers, etc.
 */
export function DialogTitleRow({ title, description, className }: DialogTitleRowProps) {
  return (
    <DialogHeader className={className}>
      <DialogTitle>{title}</DialogTitle>
      {description != null && <DialogDescription>{description}</DialogDescription>}
    </DialogHeader>
  );
}
