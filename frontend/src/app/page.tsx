export default function Home() {
  return (
    <main className="container py-12">
      <header className="mb-8 space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Rett Drug Repurposing</h1>
        <p className="text-muted-foreground max-w-prose">
          Phase 1 — target-based repurposing for Rett syndrome. Streaming candidate UI lands
          in a later commit; this is the placeholder page.
        </p>
      </header>
      <section className="text-sm text-muted-foreground">
        Backend health:{" "}
        <code className="bg-muted px-1.5 py-0.5 rounded">GET /api/health</code> (proxied to
        FastAPI).
      </section>
    </main>
  );
}
