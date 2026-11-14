import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  if (request.nextUrl.searchParams.get("view") === "chat") {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL("/learn", request.url));
}

export const config = {
  matcher: "/",
};
