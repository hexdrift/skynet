/** Shared look for the clickable library rows (datasets, labeling sessions). */

export const LIST_ROW_CLASS =
  "group flex cursor-pointer flex-wrap items-center gap-3 rounded-2xl border border-input bg-background px-3 py-3 text-start shadow-xs transition-[background-color,border-color] duration-150 ease-out hover:bg-accent/55 focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:flex-nowrap sm:gap-3.5 sm:px-4";

export const LIST_ROW_SELECTED_CLASS = "border-primary/35 bg-accent/55";

export const LIST_ROW_ICON_CLASS =
  "flex size-9 shrink-0 items-center justify-center rounded-xl border border-input bg-card text-[#6B5443] shadow-xs transition-colors duration-150 group-hover:text-primary";

export const LIST_ROW_TITLE_CLASS =
  "truncate text-sm font-semibold tracking-[-0.005em] text-foreground";

export const LIST_ROW_META_CLASS =
  "mt-1 flex min-w-0 items-center gap-x-1.5 text-xs text-muted-foreground tabular-nums";

export const LIST_ROW_META_DOT_CLASS = "text-muted-foreground/40";

// Hover-capable desktops dim the actions until the row is hovered or focused;
// touch screens keep them fully visible since there is no hover to reveal them.
export const LIST_ROW_ACTIONS_CLASS =
  "flex w-full shrink-0 items-center justify-end gap-0.5 border-t border-border/40 pt-2 transition-opacity duration-200 ease-out sm:w-auto sm:border-t-0 sm:pt-0 lg:[@media(hover:hover)]:opacity-55 lg:[@media(hover:hover)]:group-hover:opacity-100 lg:[@media(hover:hover)]:group-focus-within:opacity-100";

export const LIST_ROW_ACTION_DIVIDER_CLASS = "mx-1 h-4 w-px bg-border/70";
