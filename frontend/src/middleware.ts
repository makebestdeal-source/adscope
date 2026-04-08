import { NextRequest, NextResponse } from "next/server";

const ADMIN_PATHS = ["/admin"];
const TOKEN_KEY = "adscope_token";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow static assets
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/images") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // Protect admin-only paths
  if (ADMIN_PATHS.some((p) => pathname.startsWith(p))) {
    const token = request.cookies.get(TOKEN_KEY)?.value;
    if (!token) {
      const loginUrl = new URL("/login", request.url);
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
