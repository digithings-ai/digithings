/**
 * Turn-count limits for the embed gate. Kept in a dependency-free, non-"use client"
 * module so both the server route (embed-turn-quota, api/chat) and client components
 * (embed/page) import the SAME numbers — the free/raised caps are a cross-boundary
 * contract (see the trial-gate design spec's Global Constraints).
 */
export const EMBED_FREE_TURN_LIMIT = 3;
export const EMBED_TRIAL_TURN_LIMIT = 100;
