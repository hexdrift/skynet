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
export { AnimatedWordmark } from "./animated-wordmark";
export { CodeEditor, type ValidationResult } from "./code-editor";
export {
  ColumnHeader,
  ResetColumnsButton,
  useColumnFilters,
  useColumnResize,
  type Filters,
  type SortDir,
} from "./excel-filter";
export { HelpTip } from "./help-tip";
export { ModelChip, AddModelButton } from "./model-chip";
export {
  FadeIn,
  StaggerContainer,
  StaggerItem,
  HoverScale,
  TiltCard,
  AnimatedNumber,
} from "./motion";
export { NumberInput } from "./number-input";
export { ParticleHero } from "./particle-hero";
export { ScoreChart } from "./score-chart";
export {
  AgentThread,
  AgentBubble,
  Composer,
  MessageActions,
  ThinkingSection,
  UserBubble,
  UserBubbleEditor,
} from "./agent";
export type {
  AgentMessage,
  AgentStatus,
  AgentThinking,
  AgentToolCall,
  AgentToolStatus,
} from "./agent";

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
export { Popover, PopoverContent, PopoverTrigger } from "./primitives/popover";
export { Separator } from "./primitives/separator";
export {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./primitives/sheet";
export { Switch } from "./primitives/switch";
export { Skeleton } from "boneyard-js/react";
