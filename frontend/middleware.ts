import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  // ── Auth callback ──────────────────────────────────────────────────────────
  // Backend redirects here after Google OAuth: /auth/callback?token=JWT&next=/dashboard
  // We set the httpOnly cookie here (in middleware) because route handlers can
  // be unreliable for cookie-setting in Next.js 14 App Router.
  if (pathname === "/auth/callback") {
    const token = searchParams.get("token");
    const next = searchParams.get("next") ?? "/dashboard";

    if (!token) {
      return NextResponse.redirect(new URL("/signin?error=missing_token", request.url));
    }

    const response = NextResponse.redirect(new URL(next, request.url));
    response.cookies.set("reeva_session", token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: 72 * 60 * 60, // 72 hours — matches backend token expiry
      path: "/",
    });
    return response;
  }

  // ── Protected dashboard routes ─────────────────────────────────────────────
  const session = request.cookies.get("reeva_session");
  if (!session?.value) {
    return NextResponse.redirect(new URL("/signin", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/auth/callback", "/dashboard/:path*"],
};
