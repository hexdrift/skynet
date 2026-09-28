import type { StorageItem } from "@/shared/lib/api";
import { msg, type MessageKey } from "@/shared/lib/messages";

/** Storage categories, mirroring the backend ``STORAGE_CATEGORIES``. */
export type StorageCategory = "optimizations" | "datasets" | "agent_chats" | "staged_uploads";

interface StorageCategoryMeta {
  label: MessageKey;
  /** One-line "what is this category" shown under the drawer title. */
  description: MessageKey;
  /** The category's homogeneous item type, used to route the bulk-delete batch. */
  itemType: StorageItem["type"];
}

export const CATEGORY_META: Record<StorageCategory, StorageCategoryMeta> = {
  optimizations: {
    label: "storage.category.optimizations",
    description: "storage.category.desc.optimizations",
    itemType: "optimization",
  },
  datasets: {
    label: "storage.category.datasets",
    description: "storage.category.desc.datasets",
    itemType: "dataset",
  },
  agent_chats: {
    label: "storage.category.agent_chats",
    description: "storage.category.desc.agent_chats",
    itemType: "chat",
  },
  staged_uploads: {
    label: "storage.category.staged_uploads",
    description: "storage.category.desc.staged_uploads",
    itemType: "staged_upload",
  },
};

/** Metadata for a category key from the API; ``undefined`` for one this build doesn't know. */
export function categoryMeta(key: string | null | undefined): StorageCategoryMeta | undefined {
  return key && Object.hasOwn(CATEGORY_META, key)
    ? CATEGORY_META[key as StorageCategory]
    : undefined;
}

/** Display label for a category key, falling back to the raw key. */
export function categoryLabel(key: string): string {
  const meta = categoryMeta(key);
  return meta ? msg(meta.label) : key;
}
