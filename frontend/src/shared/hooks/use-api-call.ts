/**
 * Unified API call hook
 * Provides consistent error handling, loading state, and toast integration
 */

import { useState, useCallback } from "react";
import { toast } from "react-toastify";

interface UseApiCallOptions<T> {
  onSuccess?: (data: T) => void;
  onError?: (error: Error) => void;
  successMessage?: string;
  errorMessage?: string;
}

export function useApiCall<T = void, Args extends unknown[] = []>(
  apiFunction: (...args: Args) => Promise<T>,
  options: UseApiCallOptions<T> = {}
) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [data, setData] = useState<T | null>(null);

  const execute = useCallback(
    async (...args: Args) => {
      setLoading(true);
      setError(null);

      try {
        const result = await apiFunction(...args);
        setData(result);

        if (options.successMessage) {
          toast.success(options.successMessage);
        }

        options.onSuccess?.(result);
        return result;
      } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        setError(error);

        if (options.errorMessage) {
          toast.error(options.errorMessage);
        } else {
          toast.error(error.message || "אירעה שגיאה");
        }

        options.onError?.(error);
        throw error;
      } finally {
        setLoading(false);
      }
    },
    [apiFunction, options]
  );

  const reset = useCallback(() => {
    setLoading(false);
    setError(null);
    setData(null);
  }, []);

  return {
    execute,
    loading,
    error,
    data,
    reset,
  };
}
