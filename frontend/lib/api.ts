const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  createSession(campaignName: string, setting: string) {
    return request<{ session_id: string }>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ campaign_name: campaignName, setting }),
    });
  },

  getSession(sessionId: string) {
    return request<Record<string, unknown>>(`/api/sessions/${sessionId}`);
  },

  listSessions() {
    return request<Array<Record<string, unknown>>>("/api/sessions");
  },

  createCharacter(params: {
    session_id: string;
    name: string;
    race: string;
    character_class: string;
    backstory?: string;
    personality?: string;
    appearance?: string;
  }) {
    return request<Record<string, unknown>>(
      `/api/sessions/${params.session_id}/characters`,
      {
        method: "POST",
        body: JSON.stringify(params),
      }
    );
  },

  saveSession(sessionId: string) {
    return request<{ status: string }>(`/api/sessions/${sessionId}/save`, {
      method: "POST",
    });
  },

  listCampaigns() {
    return request<Array<Record<string, unknown>>>("/api/campaigns");
  },

  // ── Character Roster ──────────────────────────────────────────────────

  listSavedCharacters(ownerId: string = "default") {
    return request<Array<Record<string, unknown>>>(`/api/characters?owner_id=${ownerId}`);
  },

  getSavedCharacter(characterId: string) {
    return request<Record<string, unknown>>(`/api/characters/${characterId}`);
  },

  saveCharacterToRoster(characterData: Record<string, unknown>) {
    return request<{ status: string }>("/api/characters/save", {
      method: "POST",
      body: JSON.stringify(characterData),
    });
  },

  importCharacterToSession(sessionId: string, characterId: string) {
    return request<Record<string, unknown>>(
      `/api/sessions/${sessionId}/characters/import/${characterId}`,
      { method: "POST" }
    );
  },

  saveAllCharactersFromSession(sessionId: string) {
    return request<{ status: string; characters: Array<Record<string, unknown>> }>(
      `/api/sessions/${sessionId}/characters/save-all`,
      { method: "POST" }
    );
  },

  deleteSavedCharacter(characterId: string) {
    return request<{ status: string }>(`/api/characters/${characterId}`, {
      method: "DELETE",
    });
  },
};
