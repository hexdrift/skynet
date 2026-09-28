import { toast } from "react-toastify";

import { msg } from "@/shared/lib/messages";

/** Quick confirmation toast for any copy-to-clipboard action. */
export function notifyCopied(): void {
  toast.success(msg("clipboard.copied"), { autoClose: 1500 });
}
