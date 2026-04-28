/**
 * Shared UI surface — single import point for cross-feature UI.
 *
 * Two layers live under shared/ui:
 *  - ./primitives/* — vendor-style shadcn building blocks
 *  - ./*           — app-specific composites built on top of the primitives
 */

export { EmptyState } from "./empty-state";
export { LoadingState } from "./loading-state";
export { StatusBadge } from "./status-badge";
export { ConfirmDialog } from "./confirm-dialog";
export { MetricCard } from "./metric-card";

export { Button } from "./primitives/button";
export {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardFooter,
} from "./primitives/card";
export { Badge } from "./primitives/badge";
export { Input } from "./primitives/input";
export { Label } from "./primitives/label";
export { Tabs, TabsContent, TabsList, TabsTrigger } from "./primitives/tabs";
export {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./primitives/dialog";
export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./primitives/table";
export {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  SelectGroup,
  SelectLabel,
} from "./primitives/select";
export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./primitives/tooltip";
export { Skeleton } from "boneyard-js/react";
