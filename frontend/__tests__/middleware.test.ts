import { middleware } from "../middleware";
import { NextRequest, NextResponse } from "./__mocks__/next-server";

// Cast so TypeScript is happy with our lightweight mock
const req = (url: string, cookies: Record<string, string> = {}) =>
  new NextRequest(url, cookies) as unknown as Parameters<typeof middleware>[0];

describe("middleware — route protection", () => {
  // ── Unauthenticated access ────────────────────────────────────────────────

  it("redirects /dashboard to /signin when no session cookie", () => {
    const res = middleware(req("http://localhost:3000/dashboard")) as unknown as NextResponse;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/signin");
  });

  it("redirects /dashboard/calls to /signin when no session cookie", () => {
    const res = middleware(req("http://localhost:3000/dashboard/calls")) as unknown as NextResponse;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/signin");
  });

  it("redirects /dashboard/settings to /signin when no session cookie", () => {
    const res = middleware(req("http://localhost:3000/dashboard/settings")) as unknown as NextResponse;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/signin");
  });

  // ── Authenticated access ──────────────────────────────────────────────────

  it("passes through /dashboard when session cookie is present", () => {
    const res = middleware(
      req("http://localhost:3000/dashboard", { reeva_session: "some.jwt.token" })
    ) as unknown as NextResponse;
    expect(res.status).toBe(200);
  });

  it("passes through /dashboard/calls when session cookie is present", () => {
    const res = middleware(
      req("http://localhost:3000/dashboard/calls", { reeva_session: "some.jwt.token" })
    ) as unknown as NextResponse;
    expect(res.status).toBe(200);
  });

  // ── Public routes not matched by middleware ───────────────────────────────

  it("does not intercept /signin (not in matcher)", () => {
    // In practice Next.js won't invoke middleware here due to the matcher config.
    // We just verify it doesn't throw if called on /signin.
    const res = middleware(req("http://localhost:3000/signin")) as unknown as NextResponse;
    expect(res).toBeDefined();
  });

  // ── Auth callback ─────────────────────────────────────────────────────────

  it("sets cookie and redirects to /dashboard on valid /auth/callback", () => {
    const res = middleware(
      req("http://localhost:3000/auth/callback?token=my.jwt.token&next=/dashboard")
    ) as unknown as NextResponse;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
    expect(res.getCookie("reeva_session")).toBe("my.jwt.token");
  });

  it("redirects to /dashboard by default when next param is absent", () => {
    const res = middleware(
      req("http://localhost:3000/auth/callback?token=my.jwt.token")
    ) as unknown as NextResponse;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard");
  });

  it("redirects to /signin with error when token is missing from /auth/callback", () => {
    const res = middleware(
      req("http://localhost:3000/auth/callback")
    ) as unknown as NextResponse;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/signin?error=missing_token");
  });

  it("honours the next param for /dashboard/onboarding", () => {
    const res = middleware(
      req("http://localhost:3000/auth/callback?token=my.jwt.token&next=/dashboard/onboarding")
    ) as unknown as NextResponse;
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost:3000/dashboard/onboarding");
  });
});
