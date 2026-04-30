"use client";

import * as React from "react";
import { Pencil } from "lucide-react";

import { cn } from "@/shared/lib/utils";
import { msg } from "@/shared/lib/messages";

import { autoResizeTextarea } from "./auto-resize";

interface UserBubbleProps {
  content: string;
  onEdit?: () => void;
  editable?: boolean;
}

export function UserBubble({ content, onEdit, editable = true }: UserBubbleProps) {
  return (
    <div className="flex justify-start group/user">
      <div
        className="max-w-[80%] rounded-[22px] rounded-es-[4px] bg-[#3D2E22] text-[#FAF8F5] px-4 py-2.5 text-sm leading-[1.45] shadow-sm"
        dir="auto"
      >
        {content}
      </div>
      {editable && onEdit && (
        <button
          type="button"
          onClick={onEdit}
          className={cn(
            "self-center ms-1.5 opacity-0 group-hover/user:opacity-100 transition-opacity",
            "p-1.5 rounded-lg hover:bg-muted/60 cursor-pointer",
          )}
          title={msg("shared.agent.edit_and_resend")}
          aria-label={msg("shared.agent.edit_and_resend")}
        >
          <Pencil className="size-3 text-muted-foreground" />
        </button>
      )}
    </div>
  );
}

interface UserBubbleEditorProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  disabled?: boolean;
}

export function UserBubbleEditor({
  value,
  onChange,
  onSubmit,
  onCancel,
  disabled,
}: UserBubbleEditorProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  React.useEffect(() => {
    autoResizeTextarea(textareaRef.current);
  }, [value]);

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] w-full space-y-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            autoResizeTextarea(e.target);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              onCancel();
            }
          }}
          className="w-full bg-white border border-[#DDD4C8] rounded-xl px-3 py-2 text-sm resize-none outline-none focus:border-[#C8A882] transition-colors min-h-[40px] max-h-[120px]"
          rows={1}
          autoFocus
          dir="auto"
        />
        <div className="flex justify-start gap-1.5">
          <button
            type="button"
            onClick={onCancel}
            className="text-[0.6875rem] text-muted-foreground hover:text-foreground px-3 py-1 rounded-lg hover:bg-muted transition-colors cursor-pointer"
          >
            {msg("shared.agent.cancel")}
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!value.trim() || disabled}
            className="text-[0.6875rem] text-white bg-[#3D2E22] hover:bg-[#3D2E22]/90 disabled:opacity-40 disabled:cursor-not-allowed px-3 py-1 rounded-lg transition-colors cursor-pointer"
          >
            {msg("shared.agent.send")}
          </button>
        </div>
      </div>
    </div>
  );
}
