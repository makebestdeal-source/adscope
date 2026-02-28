import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/pricing", "/signup", "/about", "/guide", "/faq"];
const TOKEN_KEY = "adscope_token";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths and static assets
  if (
    PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/images") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  // Check for token in cookie (set by middleware-compatible storage)
  // Since localStorage is not available in middleware, we check a cookie.
  // The client will also set a cookie alongside localStorage for SSR compatibility.
  const token = request.cookies.get(TOKEN_KEY)?.value;

  if (!token) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
