"use client";

import Link from "next/link";
import { ArrowLeft } from "@/shared/ui/icons";

const LINK_CLASSES =
  "group inline-flex cursor-pointer items-center gap-1.5 rounded-md py-1 text-[13px] font-medium text-muted-foreground transition-colors duration-150 hover:text-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50";

const ARROW_CLASSES =
  "size-3.5 rtl:rotate-180 transition-transform duration-150 ease-out group-hover:-translate-x-0.5 rtl:group-hover:translate-x-0.5 motion-reduce:transition-none motion-reduce:transform-none";

/**
 * The quiet destination-labeled back link for page-level exits. Pass ``href``
 * to navigate, or ``onClick`` alone for an exit that resets local state
 * instead; with both, ``onClick`` runs alongside the navigation.
 */
export function BackLink({
  label,
  href,
  onClick,
}: {
  label: string;
  href?: string;
  onClick?: () => void;
}) {
  const content = (
    <>
      <ArrowLeft className={ARROW_CLASSES} aria-hidden="true" />
      {label}
    </>
  );
  if (href === undefined) {
    return (
      <button type="button" onClick={onClick} className={LINK_CLASSES}>
        {content}
      </button>
    );
  }
  return (
    <Link href={href} onClick={onClick} className={LINK_CLASSES}>
      {content}
    </Link>
  );
}
