/**
 * One toast per validation attempt, driven to exactly one terminal state.
 *
 * The toast API is injected so the lifecycle is testable without a DOM; in
 * the app it is react-toastify's `toast` object.
 */
type ToastId = string | number;
type ToastType = "success" | "error" | "info";

export interface ToastUpdate {
  render: string;
  type?: ToastType;
  isLoading?: boolean;
  autoClose?: number | false;
}

export interface ToastApi {
  loading: (content: string, options?: { toastId?: ToastId }) => ToastId;
  update: (id: ToastId, options: ToastUpdate) => void;
  dismiss: (id: ToastId) => void;
}

export interface ValidationToast {
  readonly settled: boolean;
  /** Replace the loading line's phase text while the check still runs. */
  phase: (text: string) => void;
  succeed: (text: string) => void;
  fail: (text: string) => void;
  /** The inputs changed under the check: no success is ever shown for them. */
  obsolete: (text: string) => void;
  /** Another message already reports the outcome: close the loading line. */
  dismiss: () => void;
}

const SUCCESS_MS = 2500;
const FAILURE_MS = 6000;
const OBSOLETE_MS = 4000;

export function beginValidationToast(
  api: ToastApi,
  toastId: string,
  text: string,
): ValidationToast {
  const id = api.loading(text, { toastId });
  let settled = false;
  const settle = (render: string, type: ToastType, autoClose: number) => {
    if (settled) return;
    settled = true;
    api.update(id, { render, type, isLoading: false, autoClose });
  };
  return {
    get settled() {
      return settled;
    },
    phase(phaseText) {
      if (!settled) api.update(id, { render: `${text} ${phaseText}`, isLoading: true });
    },
    succeed(render) {
      settle(render, "success", SUCCESS_MS);
    },
    fail(render) {
      settle(render, "error", FAILURE_MS);
    },
    obsolete(render) {
      settle(render, "info", OBSOLETE_MS);
    },
    dismiss() {
      if (settled) return;
      settled = true;
      api.dismiss(id);
    },
  };
}
