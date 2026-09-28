/** Tests for the phone-shell device class helpers. */

import assert from "node:assert/strict";
import test from "node:test";

import { deviceClassFromRequest } from "./device-class.ts";

test("deviceClassFromRequest prefers the client hint", () => {
  assert.equal(deviceClassFromRequest("Mozilla/5.0 (Windows NT 10.0)", "?1"), "phone");
  assert.equal(
    deviceClassFromRequest("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148", "?0"),
    "desktop",
  );
});

test("deviceClassFromRequest falls back to the UA mobile token", () => {
  const iphone =
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
  const android =
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Mobile Safari/537.36";
  const androidTablet =
    "Mozilla/5.0 (Linux; Android 14; SM-X910) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36";
  const ipad =
    "Mozilla/5.0 (iPad; CPU OS 12_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1";
  const mac =
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36";
  assert.equal(deviceClassFromRequest(iphone, null), "phone");
  assert.equal(deviceClassFromRequest(android, null), "phone");
  assert.equal(deviceClassFromRequest(androidTablet, null), "desktop");
  assert.equal(deviceClassFromRequest(ipad, null), "desktop");
  assert.equal(deviceClassFromRequest(mac, null), "desktop");
  assert.equal(deviceClassFromRequest(null, null), "desktop");
});
