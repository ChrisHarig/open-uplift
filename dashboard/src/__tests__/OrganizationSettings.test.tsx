import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { render } from "@testing-library/react";
import OrganizationSettings from "../pages/OrganizationSettings";
import { mockFetchResponse } from "../test-utils";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

// --- Mock data ---

const hubOrgDetail = {
  org_id: "test-org",
  name: "Test Hub Org",
  description: "A hub organization",
  is_verified: 1,
  created_at: "2026-02-20T10:00:00Z",
  org_mode: "hub",
  folders: [{ folder_path: "/path/project1", added_at: "2026-02-20T10:00:00Z" }],
  stats: { total_sessions: 10, total_tokens: 50000, total_messages: 100, total_cost: 1.5 },
};

const memberOrgDetail = {
  org_id: "test-org",
  name: "Test Member Org",
  description: "A member organization",
  is_verified: 1,
  created_at: "2026-02-20T10:00:00Z",
  org_mode: "member",
  folders: [{ folder_path: "/path/project1", added_at: "2026-02-20T10:00:00Z" }],
  stats: { total_sessions: 5, total_tokens: 25000, total_messages: 50, total_cost: 0.75 },
};

const hubInfoWithMembers = {
  org_id: "test-org",
  org_name: "Test Hub Org",
  sharing_config: {
    level: 1,
    stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
  },
  members: [
    { member_name: "alice", role: "member", joined_at: "2026-02-21T10:00:00Z", last_push_at: "2026-03-01T08:00:00Z", sessions_pushed: 5 },
    { member_name: "bob", role: "member", joined_at: "2026-02-22T10:00:00Z", last_push_at: null, sessions_pushed: 0 },
  ],
  invites: [
    { invite_code: "ABC123", created_by: null, created_at: "2026-02-20T10:00:00Z", revoked_at: null },
  ],
};

const hubInfoNoMembers = {
  org_id: "test-org",
  org_name: "Test Hub Org",
  sharing_config: {
    level: 1,
    stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
  },
  members: [],
  invites: [],
};

const memberMembership = {
  org_id: "test-org",
  org_name: "Test Member Org",
  member_name: "me",
  role: "member",
  hub_url: "https://hub.example.com",
  api_key: "key123",
  sharing_config: JSON.stringify({
    level: 1,
    stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
  }),
  pull_config: null,
  last_push_at: "2026-03-01T08:00:00Z",
  last_pull_at: "2026-03-01T09:00:00Z",
  joined_at: "2026-02-21T10:00:00Z",
};

const memberMembershipNeverSynced = {
  ...memberMembership,
  last_push_at: null,
  last_pull_at: null,
};

const runModeConfig = {
  enabled: false,
  start_hour: 2,
  frequency_hours: 24.0,
};

const pullConfigResponse = {
  pull_config: {
    level: 1,
    stats: { tokens: true, cost: true, messages: true, tool_calls: false, uplift: true, compacted_transcripts: false, full_transcripts: false },
  },
  sharing_config: {
    level: 1,
    stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
  },
};

// --- Helpers ---

function setupHubMocks(hubInfo = hubInfoWithMembers) {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("hub-info")) {
      return mockFetchResponse(hubInfo);
    }
    if (urlStr.includes("organizations/test-org")) {
      return mockFetchResponse(hubOrgDetail);
    }
    if (urlStr.includes("org-memberships")) {
      return mockFetchResponse([]);
    }
    if (urlStr.includes("run-modes")) {
      return mockFetchResponse(runModeConfig);
    }
    if (urlStr.includes("pull-config")) {
      return mockFetchResponse({ pull_config: null, sharing_config: hubInfoWithMembers.sharing_config });
    }
    return mockFetchResponse({});
  });
}

function setupMemberMocks(membership = memberMembership, pullCfg = pullConfigResponse) {
  vi.mocked(fetch).mockImplementation((url) => {
    const urlStr = typeof url === "string" ? url : "";
    if (urlStr.includes("hub-info")) {
      return mockFetchResponse({ members: [], invites: [] });
    }
    if (urlStr.includes("organizations/test-org")) {
      return mockFetchResponse(memberOrgDetail);
    }
    if (urlStr.includes("org-memberships") && !urlStr.includes("pull-config")) {
      return mockFetchResponse([membership]);
    }
    if (urlStr.includes("run-modes")) {
      return mockFetchResponse(runModeConfig);
    }
    if (urlStr.includes("pull-config")) {
      return mockFetchResponse(pullCfg);
    }
    return mockFetchResponse({});
  });
}

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={["/organizations/test-org/settings"]}>
      <Routes>
        <Route path="/organizations/:orgId/settings" element={<OrganizationSettings />} />
      </Routes>
    </MemoryRouter>
  );
}

// --- Tests ---

describe("OrganizationSettings", () => {
  beforeEach(() => {
    vi.mocked(fetch).mockReset();
    mockNavigate.mockReset();
  });

  // --- Loading & error states ---

  it("shows loading state initially", () => {
    vi.mocked(fetch).mockImplementation(() => new Promise(() => {})); // never resolves
    renderSettings();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("shows error message on API failure", async () => {
    vi.mocked(fetch).mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response)
    );
    renderSettings();
    await waitFor(() => {
      expect(screen.getByText("API error: 500")).toBeInTheDocument();
    });
  });

  // --- Hub mode: General section ---

  describe("Hub mode", () => {
    beforeEach(() => {
      setupHubMocks();
    });

    it("renders page title and back link", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
      expect(screen.getByText(/Test Hub Org/)).toBeInTheDocument();
    });

    it("renders general section with name and description inputs", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("General")).toBeInTheDocument();
      });
      const nameInput = screen.getByDisplayValue("Test Hub Org");
      expect(nameInput).toBeInTheDocument();
      const descInput = screen.getByDisplayValue("A hub organization");
      expect(descInput).toBeInTheDocument();
    });

    it("shows org mode and created date", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText(/Mode:/)).toBeInTheDocument();
      });
      expect(screen.getByText(/Created:/)).toBeInTheDocument();
    });

    it("shows Save Changes button when name is edited", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByDisplayValue("Test Hub Org")).toBeInTheDocument();
      });
      const nameInput = screen.getByDisplayValue("Test Hub Org");
      fireEvent.change(nameInput, { target: { value: "New Name" } });
      expect(screen.getByText("Save Changes")).toBeInTheDocument();
    });

    it("shows Save Changes button when description is edited", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByDisplayValue("A hub organization")).toBeInTheDocument();
      });
      const descInput = screen.getByDisplayValue("A hub organization");
      fireEvent.change(descInput, { target: { value: "New description" } });
      expect(screen.getByText("Save Changes")).toBeInTheDocument();
    });

    it("calls updateOrganization when Save Changes is clicked", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByDisplayValue("Test Hub Org")).toBeInTheDocument();
      });
      const nameInput = screen.getByDisplayValue("Test Hub Org");
      fireEvent.change(nameInput, { target: { value: "Updated Name" } });
      const saveBtn = screen.getByText("Save Changes");
      fireEvent.click(saveBtn);
      await waitFor(() => {
        const calls = vi.mocked(fetch).mock.calls;
        const putCall = calls.find(
          ([url, opts]) =>
            typeof url === "string" &&
            url.includes("organizations/test-org") &&
            !url.includes("hub-info") &&
            !url.includes("sharing-config") &&
            (opts as RequestInit)?.method === "PUT"
        );
        expect(putCall).toBeDefined();
      });
    });

    // --- Sharing Configuration (hub) ---

    it("renders sharing configuration section", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Sharing Configuration")).toBeInTheDocument();
      });
    });

    it("renders SharingConfigDisplay with current config", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Sharing Level")).toBeInTheDocument();
        expect(screen.getByText("Shared Data")).toBeInTheDocument();
      });
    });

    it("shows Edit button for sharing config", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Sharing Configuration")).toBeInTheDocument();
      });
      expect(screen.getByText("Edit")).toBeInTheDocument();
    });

    it("opens sharing config editor when Edit is clicked", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Edit")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Edit"));
      await waitFor(() => {
        expect(screen.getByText("Save")).toBeInTheDocument();
        expect(screen.getByText("Cancel")).toBeInTheDocument();
      });
      // Should show checkboxes for stats
      expect(screen.getByLabelText(/Tokens/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Cost/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Messages/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Tool Calls/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Uplift/)).toBeInTheDocument();
    });

    it("cancels sharing config edit", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Edit")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Edit"));
      await waitFor(() => {
        expect(screen.getByText("Cancel")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Cancel"));
      await waitFor(() => {
        expect(screen.getByText("Edit")).toBeInTheDocument();
      });
      expect(screen.queryByText("Cancel")).not.toBeInTheDocument();
    });

    it("saves sharing config changes", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Edit")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Edit"));
      await waitFor(() => {
        expect(screen.getByText("Save")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Save"));
      await waitFor(() => {
        const calls = vi.mocked(fetch).mock.calls;
        const putCall = calls.find(
          ([url, opts]) =>
            typeof url === "string" &&
            url.includes("sharing-config") &&
            (opts as RequestInit)?.method === "PUT"
        );
        expect(putCall).toBeDefined();
      });
    });

    it("shows session-level sharing checkbox in editor", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Edit")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Edit"));
      await waitFor(() => {
        expect(screen.getByLabelText(/Session-level sharing/)).toBeInTheDocument();
      });
    });

    // --- Invite Code section (hub admin with members) ---

    it("renders invite code section for hub admin", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Invite Code")).toBeInTheDocument();
      });
    });

    it("displays active invite code", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("ABC123")).toBeInTheDocument();
      });
    });

    it("shows Copy button for invite code", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Copy")).toBeInTheDocument();
      });
    });

    it("shows New Invite Code button", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("New Invite Code")).toBeInTheDocument();
      });
    });

    it("generates new invite code when button clicked", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("New Invite Code")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("New Invite Code"));
      await waitFor(() => {
        const calls = vi.mocked(fetch).mock.calls;
        // Should revoke existing invite first, then create new one
        const revokeCall = calls.find(
          ([url, opts]) =>
            typeof url === "string" &&
            url.includes("revoke") &&
            (opts as RequestInit)?.method === "POST"
        );
        const createCall = calls.find(
          ([url, opts] ) =>
            typeof url === "string" &&
            url.includes("hub-invites") &&
            !url.includes("revoke") &&
            (opts as RequestInit)?.method === "POST"
        );
        expect(revokeCall).toBeDefined();
        expect(createCall).toBeDefined();
      });
    });

    // --- No invite section for hub without members ---

    it("does not show invite section when hub has no members", async () => {
      setupHubMocks(hubInfoNoMembers);
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
      expect(screen.queryByText("Invite Code")).not.toBeInTheDocument();
    });

    // --- Does not show member-only sections ---

    it("does not show push config section for hub mode", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
      expect(screen.queryByText("Data Shared Per Push")).not.toBeInTheDocument();
    });

    it("does not show pull configuration section for hub mode", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
      expect(screen.queryByText("Pull Configuration")).not.toBeInTheDocument();
    });

    it("does not show sync settings section for hub mode", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
      expect(screen.queryByText("Sync Settings")).not.toBeInTheDocument();
    });
  });

  // --- Member mode ---

  describe("Member mode", () => {
    beforeEach(() => {
      setupMemberMocks();
    });

    it("renders page title", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
    });

    it("renders back link with org name", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText(/Test Member Org/)).toBeInTheDocument();
      });
    });

    // --- Push config (read-only) ---

    it("renders data shared per push section", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Data Shared Per Push")).toBeInTheDocument();
      });
    });

    it("shows Set by Admin badge", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Set by Admin")).toBeInTheDocument();
      });
    });

    it("renders enabled stat pills", async () => {
      renderSettings();
      await waitFor(() => {
        // Push config pills and pull config toggles both show stat labels,
        // so use getAllByText to account for duplicates
        expect(screen.getAllByText("Tokens").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Cost").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Messages").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText(/Tool call/i).length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Uplift").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("shows aggregates only when level < 2", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Aggregates only")).toBeInTheDocument();
      });
    });

    it("shows Per-session when level >= 2", async () => {
      const level2Membership = {
        ...memberMembership,
        sharing_config: JSON.stringify({
          level: 2,
          stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
        }),
      };
      setupMemberMocks(level2Membership, {
        pull_config: null,
        sharing_config: {
          level: 2,
          stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
        },
      });
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Per-session")).toBeInTheDocument();
      });
    });

    // --- Pull config (editable) ---

    it("renders pull configuration section", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Pull Configuration")).toBeInTheDocument();
      });
    });

    it("renders toggle rows for offered stats in pull config", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Pull Configuration")).toBeInTheDocument();
      });
      // Pull config should show toggles for stats that are offered by the sharing config
      const toggles = document.querySelectorAll(".toggle");
      expect(toggles.length).toBeGreaterThanOrEqual(1);
    });

    it("shows pull per-session toggle when admin sharing level >= 2", async () => {
      const level2Membership = {
        ...memberMembership,
        sharing_config: JSON.stringify({
          level: 2,
          stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
        }),
      };
      setupMemberMocks(level2Membership, {
        pull_config: null,
        sharing_config: {
          level: 2,
          stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
        },
      });
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Pull per-session summaries")).toBeInTheDocument();
      });
    });

    it("does not show pull per-session toggle when admin sharing level < 2", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Pull Configuration")).toBeInTheDocument();
      });
      expect(screen.queryByText("Pull per-session summaries")).not.toBeInTheDocument();
    });

    // --- Sync settings ---

    it("renders sync settings section", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Sync Settings")).toBeInTheDocument();
      });
    });

    it("shows hub URL", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("https://hub.example.com")).toBeInTheDocument();
      });
    });

    it("shows last push and pull timestamps", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText(/Last push:/)).toBeInTheDocument();
        expect(screen.getByText(/Last pull:/)).toBeInTheDocument();
        expect(screen.getByText("2026-03-01 08:00")).toBeInTheDocument();
        expect(screen.getByText("2026-03-01 09:00")).toBeInTheDocument();
      });
    });

    it("shows Never when no sync timestamps", async () => {
      setupMemberMocks(memberMembershipNeverSynced);
      renderSettings();
      await waitFor(() => {
        const neverElements = screen.getAllByText("Never");
        expect(neverElements.length).toBe(2);
      });
    });

    it("shows auto-sync schedule toggle", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Auto-sync schedule")).toBeInTheDocument();
      });
    });

    it("does not show schedule inputs when auto-sync is disabled", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Auto-sync schedule")).toBeInTheDocument();
      });
      // When disabled, should not show time inputs
      expect(screen.queryByText("every")).not.toBeInTheDocument();
    });

    it("shows schedule inputs when auto-sync is enabled", async () => {
      vi.mocked(fetch).mockImplementation((url) => {
        const urlStr = typeof url === "string" ? url : "";
        if (urlStr.includes("hub-info")) {
          return mockFetchResponse({ members: [], invites: [] });
        }
        if (urlStr.includes("organizations/test-org")) {
          return mockFetchResponse(memberOrgDetail);
        }
        if (urlStr.includes("org-memberships") && !urlStr.includes("pull-config")) {
          return mockFetchResponse([memberMembership]);
        }
        if (urlStr.includes("run-modes")) {
          return mockFetchResponse({ enabled: true, start_hour: 2, frequency_hours: 24.0 });
        }
        if (urlStr.includes("pull-config")) {
          return mockFetchResponse(pullConfigResponse);
        }
        return mockFetchResponse({});
      });
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("every")).toBeInTheDocument();
        expect(screen.getByText("hrs")).toBeInTheDocument();
      });
    });

    // --- Does not show hub-only sections ---

    it("does not show sharing configuration editor for member mode", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
      expect(screen.queryByText("Sharing Configuration")).not.toBeInTheDocument();
    });

    it("does not show invite code section for member mode", async () => {
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Organization Settings")).toBeInTheDocument();
      });
      expect(screen.queryByText("Invite Code")).not.toBeInTheDocument();
    });
  });

  // --- Danger zone (both modes) ---

  describe("Danger Zone", () => {
    it("renders danger zone section for hub org", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Danger Zone")).toBeInTheDocument();
      });
    });

    it("renders danger zone section for member org", async () => {
      setupMemberMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Danger Zone")).toBeInTheDocument();
      });
    });

    it("shows hub-specific delete warning for hub mode", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText(/remove all folder associations, hub members/)).toBeInTheDocument();
      });
    });

    it("shows member-specific delete warning for member mode", async () => {
      setupMemberMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText(/disconnect from the hub and remove all folder associations/)).toBeInTheDocument();
      });
    });

    it("shows Delete Organization button", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Delete Organization")).toBeInTheDocument();
      });
    });

    it("opens delete confirmation modal", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Delete Organization")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Delete Organization"));
      await waitFor(() => {
        expect(screen.getByText(/Delete Test Hub Org\?/)).toBeInTheDocument();
        expect(screen.getByPlaceholderText("Test Hub Org")).toBeInTheDocument();
      });
    });

    it("delete button is disabled until name is typed correctly", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Delete Organization")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Delete Organization"));
      await waitFor(() => {
        expect(screen.getByText(/Delete Test Hub Org\?/)).toBeInTheDocument();
      });
      // The delete button inside the modal (second one)
      const deleteButtons = screen.getAllByText("Delete Organization");
      const modalDeleteBtn = deleteButtons[deleteButtons.length - 1];
      expect(modalDeleteBtn).toBeDisabled();

      // Type wrong name
      const input = screen.getByPlaceholderText("Test Hub Org");
      fireEvent.change(input, { target: { value: "Wrong Name" } });
      expect(modalDeleteBtn).toBeDisabled();

      // Type correct name
      fireEvent.change(input, { target: { value: "Test Hub Org" } });
      expect(modalDeleteBtn).not.toBeDisabled();
    });

    it("calls deleteOrganization and navigates on confirm", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Delete Organization")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Delete Organization"));
      await waitFor(() => {
        expect(screen.getByPlaceholderText("Test Hub Org")).toBeInTheDocument();
      });
      const input = screen.getByPlaceholderText("Test Hub Org");
      fireEvent.change(input, { target: { value: "Test Hub Org" } });
      const deleteButtons = screen.getAllByText("Delete Organization");
      const modalDeleteBtn = deleteButtons[deleteButtons.length - 1];
      fireEvent.click(modalDeleteBtn);
      await waitFor(() => {
        const calls = vi.mocked(fetch).mock.calls;
        const deleteCall = calls.find(
          ([url, opts]) =>
            typeof url === "string" &&
            url.includes("organizations/test-org") &&
            (opts as RequestInit)?.method === "DELETE"
        );
        expect(deleteCall).toBeDefined();
      });
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith("/organizations");
      });
    });

    it("closes delete modal when Cancel is clicked", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Delete Organization")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Delete Organization"));
      await waitFor(() => {
        expect(screen.getByText(/Delete Test Hub Org\?/)).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Cancel"));
      expect(screen.queryByText(/Delete Test Hub Org\?/)).not.toBeInTheDocument();
    });

    it("shows member delete text in modal for member mode", async () => {
      setupMemberMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Delete Organization")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Delete Organization"));
      await waitFor(() => {
        expect(screen.getByText(/disconnect from the hub and stop all syncing/)).toBeInTheDocument();
      });
    });

    it("shows hub delete text in modal for hub mode", async () => {
      setupHubMocks();
      renderSettings();
      await waitFor(() => {
        expect(screen.getByText("Delete Organization")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText("Delete Organization"));
      await waitFor(() => {
        expect(screen.getByText(/permanently delete the organization/)).toBeInTheDocument();
      });
    });
  });
});
