import "@testing-library/jest-dom/vitest";

// Global fetch mock
const mockFetch = vi.fn();
global.fetch = mockFetch;

// ResizeObserver mock (required by Recharts)
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

beforeEach(() => {
  mockFetch.mockReset();
});
