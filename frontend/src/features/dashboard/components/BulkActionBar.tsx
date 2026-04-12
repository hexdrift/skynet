import { AnimatePresence, motion } from "framer-motion";
import { Trash2, X } from "lucide-react";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

type BulkActionBarProps = {
  isAdmin: boolean;
  selectedCount: number;
  onClear: () => void;
  onRequestBulkDelete: () => void;
};

export function BulkActionBar({
  isAdmin,
  selectedCount,
  onClear,
  onRequestBulkDelete,
}: BulkActionBarProps) {
  return (
    <AnimatePresence>
      {isAdmin && selectedCount > 0 && (
        <motion.div
          initial={{ y: 24, opacity: 0, scale: 0.96 }}
          animate={{ y: 0, opacity: 1, scale: 1 }}
          exit={{ y: 24, opacity: 0, scale: 0.96 }}
          transition={{
            type: "spring",
            stiffness: 380,
            damping: 30,
            mass: 0.8,
          }}
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50"
          dir="rtl"
        >
          <div className="flex items-center gap-1 rounded-full border border-border/60 bg-background/95 backdrop-blur-xl px-3 py-1.5 shadow-[0_12px_32px_rgba(0,0,0,0.18)]">
            <span className="px-1 text-sm text-foreground">
              {selectedCount === 1 ? (
                <>נבחרה אופטימיזציה אחת</>
              ) : (
                <>
                  נבחרו{" "}
                  <span className="font-semibold tabular-nums">
                    {selectedCount}
                  </span>{" "}
                  אופטימיזציות
                </>
              )}
            </span>
            <div className="mx-1 h-5 w-px bg-border/60" />
            <TooltipProvider delayDuration={150}>
              <UiTooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onClear}
                    className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-accent/80 hover:text-foreground active:scale-95 transition-all cursor-pointer"
                    aria-label="נקה בחירה"
                  >
                    <X className="size-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">נקה בחירה</TooltipContent>
              </UiTooltip>
              <UiTooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onRequestBulkDelete}
                    className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-destructive/10 hover:text-destructive active:scale-95 transition-all cursor-pointer"
                    aria-label="מחק נבחרים"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top">מחק נבחרים</TooltipContent>
              </UiTooltip>
            </TooltipProvider>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
