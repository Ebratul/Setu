import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";

import { SANDBOX, SCRIPT, emptyRun, passed } from "./fixtures";

vi.mock("@/lib/api/auth", () => ({ demoLogin: vi.fn(), getMe: vi.fn() }));
vi.mock("@/lib/api/demo", async (orig) => {
  const real = await orig<typeof import("@/lib/api/demo")>();
  return {
    ...real,
    getDemoSteps: vi.fn(),
    startSandbox: vi.fn(),
    getRun: vi.fn(),
    runScene: vi.fn(),
    gotoStep: vi.fn(),
    resetRun: vi.fn(),
    getSummary: vi.fn(),
    endSandbox: vi.fn(),
  };
});
import * as auth from "@/lib/api/auth";
import * as api from "@/lib/api/demo";

import { useDemoRun } from "./useDemoRun";

const ROUTES: Record<string, string> = {
  "1.1": "/app/chat?thread=t1",
  "2.1": "/app/orders/R/analysis",
  "2.2": "/supplier/d1",
  "3.1": "/app/documents/f1",
};
const result = (n: number, k: number, over = {}) => passed(n, k, ROUTES[`${n}.${k}`], over);

let done: ReturnType<typeof result>[] = [];

beforeEach(() => {
  done = [];
  vi.mocked(api.getDemoSteps).mockResolvedValue(SCRIPT);
  vi.mocked(api.startSandbox).mockResolvedValue(SANDBOX);
  vi.mocked(api.getRun).mockImplementation(async () => emptyRun({ scenes: done }));
  vi.mocked(api.runScene).mockImplementation(async (n, k) => {
    const r = result(n, k);
    done = [...done.filter((d) => !(d.n === n && d.k === k)), r];
    return emptyRun({ scenes: done, last: r, completed: done.length === 4 });
  });
  vi.mocked(api.gotoStep).mockImplementation(async (step) => {
    done = SCRIPT.steps.filter((s) => s.n < step).flatMap((s) => s.scenes.map((sc) => result(s.n, sc.k)));
    return emptyRun({ scenes: done });
  });
  vi.mocked(auth.getMe).mockResolvedValue({ email: "rahima@demo.setu" } as never);
  vi.mocked(auth.demoLogin).mockResolvedValue({} as never);
});
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

const setup = (o: Partial<Parameters<typeof useDemoRun>[0]> = {}) =>
  renderHook(() => useDemoRun({ initialStep: null, autoPlay: false, lang: "en", ...o }));

describe("useDemoRun", () => {
  it("loads the script, resumes the sandbox and waits for Start", async () => {
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    expect(r.current.flat).toHaveLength(4);
    expect(r.current.index).toBe(-1);
    expect(api.runScene).not.toHaveBeenCalled();
  });

  it("runs scenes one by one, takes the resolved route and logs in only when the user differs", async () => {
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    act(() => r.current.start());
    await waitFor(() => expect(r.current.url).toBe("/app/chat?thread=t1"));
    expect(auth.demoLogin).not.toHaveBeenCalled();
    act(() => r.current.next());
    await waitFor(() => expect(r.current.url).toBe("/app/orders/R/analysis"));
    act(() => r.current.next());
    await waitFor(() => expect(r.current.url).toBe("/supplier/d1"));
    expect(auth.demoLogin).toHaveBeenCalledWith("huaxin@demo.setu");
    expect(api.runScene).toHaveBeenCalledTimes(3);
    expect(r.current.current?.key).toBe("2.2");
  });

  it("Previous re-shows the stored result and never re-runs the scene", async () => {
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    act(() => r.current.start());
    await waitFor(() => expect(r.current.url).toBeTruthy());
    act(() => r.current.next());
    await waitFor(() => expect(r.current.index).toBe(1));
    await waitFor(() => expect(r.current.busy).toBe(false));
    act(() => r.current.prev());
    await waitFor(() => expect(r.current.index).toBe(0));
    await waitFor(() => expect(r.current.busy).toBe(false));
    expect(api.runScene).toHaveBeenCalledTimes(2);
    expect(r.current.url).toBe("/app/chat?thread=t1");
  });

  it("deep link ?step=3 runs earlier scenes via goto, then shows step 3 scene 1", async () => {
    const { result: r } = setup({ initialStep: 3 });
    await waitFor(() => expect(r.current.url).toBe("/app/documents/f1"));
    expect(api.gotoStep).toHaveBeenCalledWith(3);
    expect(r.current.current?.n).toBe(3);
    expect(r.current.current?.pos).toBe(1);
    expect(api.runScene).toHaveBeenCalledTimes(1);
  });

  it("a failed scene shows its message and never blocks Next", async () => {
    vi.mocked(api.runScene).mockImplementationOnce(async (n, k) => {
      const f = { ...result(n, k), status: "failed" as const, message: { en: "Could not finish", bn: "বাংলা" } };
      return emptyRun({ scenes: [f], last: f });
    });
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    act(() => r.current.start());
    await waitFor(() => expect(r.current.result?.status).toBe("failed"));
    expect(r.current.problem).toBeNull();
    act(() => r.current.next());
    await waitFor(() => expect(r.current.index).toBe(1));
    await waitFor(() => expect(r.current.result?.status).toBe("passed"));
  });

  it("auto-play advances after the dwell time and stops at the end with the summary", async () => {
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    act(() => {
      r.current.setPlaying(true);
      r.current.start();
    });
    await waitFor(() => expect(r.current.index).toBe(0));
    await waitFor(() => expect(r.current.result?.status).toBe("passed"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7100);
    });
    await waitFor(() => expect(r.current.index).toBe(1));
    vi.mocked(api.getSummary).mockResolvedValue({ simulated: true, ready: true, numbers: [], attacks: [], links: [] });
    for (let i = 0; i < 3; i++) {
      await waitFor(() => expect(r.current.busy).toBe(false));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(11000);
      });
    }
    await waitFor(() => expect(r.current.view).toBe("summary"));
    expect(r.current.playing).toBe(false);
  });

  it("2x speed halves the dwell", async () => {
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    act(() => {
      r.current.setSpeed(2);
      r.current.setPlaying(true);
      r.current.start();
    });
    await waitFor(() => expect(r.current.result?.status).toBe("passed"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3600);
    });
    await waitFor(() => expect(r.current.index).toBe(1));
  });

  it("recording mode keeps a fixed 1x pace", async () => {
    const { result: r } = setup({ fixedPace: true });
    await waitFor(() => expect(r.current.status).toBe("ready"));
    act(() => r.current.setSpeed(2));
    expect(r.current.speed).toBe(1);
  });

  it("Reset rebuilds the sandbox and returns to scene 1", async () => {
    vi.mocked(api.resetRun).mockImplementation(async () => {
      done = [];
      return emptyRun();
    });
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    act(() => r.current.start());
    await waitFor(() => expect(r.current.url).toBeTruthy());
    act(() => r.current.next());
    await waitFor(() => expect(r.current.index).toBe(1));
    await act(async () => {
      await r.current.reset();
    });
    await waitFor(() => expect(r.current.index).toBe(0));
    expect(api.resetRun).toHaveBeenCalledTimes(1);
    expect(r.current.playing).toBe(false);
  });

  it("410 mid-run ends the sandbox so the UI can offer a new one", async () => {
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    vi.mocked(api.runScene).mockRejectedValueOnce(new ApiError(410, "x", null, "SANDBOX_EXPIRED"));
    act(() => r.current.start());
    await waitFor(() => expect(r.current.status).toBe("ended"));
    expect(r.current.problem?.kind).toBe("expired");
  });

  it("503 capacity at start is a friendly error state", async () => {
    vi.mocked(api.startSandbox).mockRejectedValue(new ApiError(503, "x", null, "SANDBOX_CAPACITY"));
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("error"));
    expect(r.current.problem?.kind).toBe("capacity");
  });

  it("429 on a scene waits and retries once", async () => {
    const { result: r } = setup();
    await waitFor(() => expect(r.current.status).toBe("ready"));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(api.runScene).mockRejectedValueOnce(new ApiError(429, "x", null, "SANDBOX_RATE_LIMIT", 1));
    act(() => r.current.start());
    await waitFor(() => expect(r.current.rateWait).toBe(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    await waitFor(() => expect(r.current.url).toBe("/app/chat?thread=t1"));
    expect(api.runScene).toHaveBeenCalledTimes(2);
  });
});
