// Placeholder route. Full SSE proxy lands with the frontend commit (see IMPLEMENTATION_BRIEF.md §12).
import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST() {
  return NextResponse.json(
    { error: "Not implemented yet — lands in commit 6 (Next.js frontend)." },
    { status: 501 },
  );
}
