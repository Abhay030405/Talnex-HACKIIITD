// Hackathon data for the organizer's pages: an event, its overview, the comparison, and each project's proof card.
import "server-only";

import { ApiError, apiFetch } from "@/lib/api";
import type { EventCompare, EventOverview, HackathonCard, ProjectSummary } from "@/lib/types";

const id = (value: string) => encodeURIComponent(value);

/** null when the thing does not exist or is not yours: the API answers 404 for both, so nothing leaks. */
async function orNull<T>(path: string): Promise<T | null> {
  try {
    return await apiFetch<T>(path);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 400)) return null;
    throw error;
  }
}

export const getEventOverview = (eventId: string) => orNull<EventOverview>(`/v1/events/${id(eventId)}/overview`);

export const getEventCompare = (eventId: string) => orNull<EventCompare>(`/v1/events/${id(eventId)}/compare`);

export const getProject = (projectId: string) => orNull<ProjectSummary>(`/v1/projects/${id(projectId)}`);

/** The card, or null while it is not ready. Check the project exists first: a stranger's project is also a 404. */
export const getProjectCard = (projectId: string) => orNull<HackathonCard>(`/v1/projects/${id(projectId)}/proof`);
