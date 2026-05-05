import { NextRequest, NextResponse } from "next/server";

const ADMIN_PATHS = ["/admin"];
const TOKEN_KEY = "adscope_token";
const PRIVATE_PREFIXES = [
  "/api",
  "/admin",
  "/settings",
  "/reports",
  "/advertisers",
  "/campaigns",
  "/gallery",
  "/analytics",
  "/keyword-analysis",
  "/shopping-insight",
  "/shopping-keyword",
  "/shopping-ranking",
  "/shopping-sales",
  "/social-gallery",
  "/social-content",
  "/social-channels",
  "/competitors",
  "/industries",
  "/products",
  "/master-index",
  "/spend",
  "/buzz-dashboard",
  "/target-audience",
  "/consumer-insights",
  "/launch-impact",
  "/marketing-schedule",
  "/campaign-effect",
  "/advertiser-trends",
  "/payment",
  "/login",
  "/signup",
  "/forgot-password",
];
const SENSITIVE_ASSET_PREFIXES = ["/images", "/screenshots"];

function setNoIndexHeaders(response: NextResponse) {
  response.headers.set(
    "X-Robots-Tag",
    "noindex, nofollow, noarchive, nosnippet, noimageindex"
  );
  return response;
}

function isPrivatePath(pathname: string) {
  return PRIVATE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    SENSITIVE_ASSET_PREFIXES.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
    )
  ) {
    return setNoIndexHeaders(NextResponse.next());
  }

  if (
    pathname.startsWith("/_next") ||
    (pathname.includes(".") && !pathname.endsWith(".html"))
  ) {
    return NextResponse.next();
  }

  // Protect admin-only paths
  if (ADMIN_PATHS.some((p) => pathname.startsWith(p))) {
    const token = request.cookies.get(TOKEN_KEY)?.value;
    if (!token) {
      const loginUrl = new URL("/login", request.url);
      return setNoIndexHeaders(NextResponse.redirect(loginUrl));
    }
  }

  if (isPrivatePath(pathname)) {
    return setNoIndexHeaders(NextResponse.next());
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
