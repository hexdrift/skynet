import { handlers } from "@/shared/lib/auth";

// next-auth's Credentials provider relies on Node-only APIs (`crypto`,
// `process.env` reads at runtime). Pin the runtime so a future Edge default
// doesn't quietly break the dev login path.
export const runtime = "nodejs";

export const { GET, POST } = handlers;
