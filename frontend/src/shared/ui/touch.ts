/**
 * Field heights: 44px touch targets on phones and coarse-pointer tablets,
 * dropping to the desktop height once a fine pointer is available. A fixed
 * height (not min-h) keeps fields in the same row aligned.
 */

/** Default fields: 36px on desktop. */
export const TOUCH_FIELD = "h-[44px] sm:h-9 [@media(hover:none)_and_(pointer:coarse)]:h-[44px]";

/** Dense tables, toolbars and inline editors: 32px on desktop. */
export const TOUCH_FIELD_SM = "h-[44px] sm:h-8 [@media(hover:none)_and_(pointer:coarse)]:h-[44px]";
