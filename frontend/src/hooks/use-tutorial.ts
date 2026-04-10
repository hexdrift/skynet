"use client";

import { useReducer, useEffect, useCallback } from "react";
import type { TutorialTrack } from "@/lib/tutorial-steps";
import { getTrack } from "@/lib/tutorial-steps";

/* ═══════════════════════════════════════════════════════════
   State Shape
   ═══════════════════════════════════════════════════════════ */

export interface TutorialState {
  /** Currently active tutorial track, or null if not running */
  activeTrack: TutorialTrack | null;
  /** Current step index within the active track */
  currentStepIndex: number;
  /** Whether the tutorial overlay is visible */
  isVisible: boolean;
  /** Whether the track selection menu is open */
  isMenuOpen: boolean;
  /** Completed tracks (persisted to localStorage) */
  completedTracks: Set<TutorialTrack>;
}

/* ═══════════════════════════════════════════════════════════
   Actions
   ═══════════════════════════════════════════════════════════ */

type TutorialAction =
  | { type: "START_TRACK"; track: TutorialTrack }
  | { type: "NEXT_STEP" }
  | { type: "PREV_STEP" }
  | { type: "GO_TO_STEP"; index: number }
  | { type: "EXIT_TUTORIAL" }
  | { type: "COMPLETE_TRACK" }
  | { type: "OPEN_MENU" }
  | { type: "CLOSE_MENU" }
  | { type: "RESET_ALL" }
  | { type: "LOAD_STATE"; state: Partial<TutorialState> };

/* ═══════════════════════════════════════════════════════════
   Reducer
   ═══════════════════════════════════════════════════════════ */

function tutorialReducer(state: TutorialState, action: TutorialAction): TutorialState {
  switch (action.type) {
    case "START_TRACK": {
      return {
        ...state,
        activeTrack: action.track,
        currentStepIndex: 0,
        isVisible: true,
        isMenuOpen: false,
      };
    }

    case "NEXT_STEP": {
      if (!state.activeTrack) return state;
      const track = getTrack(state.activeTrack);
      if (!track) return state;

      const nextIndex = state.currentStepIndex + 1;
      if (nextIndex >= track.steps.length) {
        // Last step reached — mark as completed
        return {
          ...state,
          isVisible: false,
          completedTracks: new Set([...state.completedTracks, state.activeTrack]),
        };
      }

      return {
        ...state,
        currentStepIndex: nextIndex,
      };
    }

    case "PREV_STEP": {
      if (!state.activeTrack) return state;
      const prevIndex = Math.max(0, state.currentStepIndex - 1);
      return {
        ...state,
        currentStepIndex: prevIndex,
      };
    }

    case "GO_TO_STEP": {
      if (!state.activeTrack) return state;
      const track = getTrack(state.activeTrack);
      if (!track) return state;
      const clampedIndex = Math.max(0, Math.min(action.index, track.steps.length - 1));
      return {
        ...state,
        currentStepIndex: clampedIndex,
      };
    }

    case "EXIT_TUTORIAL": {
      return {
        ...state,
        isVisible: false,
        isMenuOpen: false,
        // Keep activeTrack and currentStepIndex so user can resume
      };
    }

    case "COMPLETE_TRACK": {
      if (!state.activeTrack) return state;
      return {
        ...state,
        isVisible: false,
        completedTracks: new Set([...state.completedTracks, state.activeTrack]),
      };
    }

    case "OPEN_MENU": {
      return {
        ...state,
        isMenuOpen: true,
        isVisible: false,
      };
    }

    case "CLOSE_MENU": {
      return {
        ...state,
        isMenuOpen: false,
      };
    }

    case "RESET_ALL": {
      return {
        activeTrack: null,
        currentStepIndex: 0,
        isVisible: false,
        isMenuOpen: false,
        completedTracks: new Set(),
      };
    }

    case "LOAD_STATE": {
      return {
        ...state,
        ...action.state,
        completedTracks: new Set(action.state.completedTracks || []),
      };
    }

    default:
      return state;
  }
}

/* ═══════════════════════════════════════════════════════════
   Initial State
   ═══════════════════════════════════════════════════════════ */

const initialState: TutorialState = {
  activeTrack: null,
  currentStepIndex: 0,
  isVisible: false,
  isMenuOpen: false,
  completedTracks: new Set(),
};

/* ═══════════════════════════════════════════════════════════
   LocalStorage Key
   ═══════════════════════════════════════════════════════════ */

const STORAGE_KEY = "skynet-tutorial-state";

/* ═══════════════════════════════════════════════════════════
   Hook
   ═══════════════════════════════════════════════════════════ */

export function useTutorial() {
  const [state, dispatch] = useReducer(tutorialReducer, initialState);

  // Load state from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        dispatch({
          type: "LOAD_STATE",
          state: {
            completedTracks: new Set(parsed.completedTracks || []),
            // Don't restore activeTrack/currentStepIndex — let user restart fresh
          },
        });
      }
    } catch {
      // Ignore parse errors
    }
  }, []);

  // Persist completedTracks to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          completedTracks: Array.from(state.completedTracks),
        })
      );
    } catch {
      // Ignore storage errors
    }
  }, [state.completedTracks]);

  /* ─────────────────────────────────────────────────────────
     Public API
     ───────────────────────────────────────────────────────── */

  const startTrack = useCallback((track: TutorialTrack) => {
    dispatch({ type: "START_TRACK", track });
  }, []);

  const nextStep = useCallback(() => {
    dispatch({ type: "NEXT_STEP" });
  }, []);

  const prevStep = useCallback(() => {
    dispatch({ type: "PREV_STEP" });
  }, []);

  const goToStep = useCallback((index: number) => {
    dispatch({ type: "GO_TO_STEP", index });
  }, []);

  const exitTutorial = useCallback(() => {
    dispatch({ type: "EXIT_TUTORIAL" });
  }, []);

  const completeTrack = useCallback(() => {
    dispatch({ type: "COMPLETE_TRACK" });
  }, []);

  const openMenu = useCallback(() => {
    dispatch({ type: "OPEN_MENU" });
  }, []);

  const closeMenu = useCallback(() => {
    dispatch({ type: "CLOSE_MENU" });
  }, []);

  const resetAll = useCallback(() => {
    dispatch({ type: "RESET_ALL" });
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  // Get current step
  const currentStep = state.activeTrack
    ? getTrack(state.activeTrack)?.steps[state.currentStepIndex]
    : undefined;

  return {
    state,
    currentStep,
    startTrack,
    nextStep,
    prevStep,
    goToStep,
    exitTutorial,
    completeTrack,
    openMenu,
    closeMenu,
    resetAll,
  };
}
