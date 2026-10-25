"use client";
// Fills every API playground's Authorization field with the signed-in person's own token, so "Send" just works.
// Runs once per docs visit; when the token is new it reloads the page once so the playground on screen picks it up.
// Nothing happens for a signed-out visitor.
import { useEffect } from "react";

import { fetchSessionToken, hasFreshSessionToken, storeSessionToken } from "@/lib/docs/playground-auth";

const RELOADED_KEY = "talnex-docs-session-reloaded";

export function AutoSession() {
  useEffect(() => {
    if (hasFreshSessionToken()) return;
    let cancelled = false;
    fetchSessionToken()
      .then((answer) => {
        if (cancelled || !answer) return;
        storeSessionToken(answer);
        // Reload at most once per tab session, so a failing token can never loop.
        if (!sessionStorage.getItem(RELOADED_KEY)) {
          sessionStorage.setItem(RELOADED_KEY, "1");
          window.location.reload();
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}
