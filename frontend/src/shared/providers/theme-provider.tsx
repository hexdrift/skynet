"use client";

import * as React from "react";
import { DirectionProvider } from "@radix-ui/react-direction";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return <DirectionProvider dir="rtl">{children}</DirectionProvider>;
}
