/**
 * Shared UI components index
 * Re-exports all shared UI primitives and shadcn/ui components
 * Single import point for UI components across features
 */

// Shared UI primitives
export { EmptyState } from "./empty-state";
export { LoadingState } from "./loading-state";
export { StatusBadge } from "./status-badge";
export { ConfirmDialog } from "./confirm-dialog";
export { MetricCard } from "./metric-card";

// Re-export commonly used shadcn/ui components for convenience
export { Button } from "@/components/ui/button";
export { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
export { Badge } from "@/components/ui/badge";
export { Input } from "@/components/ui/input";
export { Label } from "@/components/ui/label";
export { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
export {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
export {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
export {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  SelectGroup,
  SelectLabel,
} from "@/components/ui/select";
// Note: Export checkbox and textarea when they are added to the UI library
export {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
export { Skeleton } from "boneyard-js/react";
