// THE ANALYST — reliable 06:30 New York trigger (Cloudflare Worker, free plan).
// GitHub's own scheduler can start runs hours late; this Worker asks GitHub to run the
// workflow at the right time. Cron Triggers (UTC): "30 10 * * *" and "30 11 * * *"
// (New York changes clocks; the engine ignores the run that comes before 06:25 New York
// and the one that finds today's edition already published).
// Secret to add in the Worker: GITHUB_TOKEN = a fine-grained token with
// "Actions: Read and write" on the repository Coorify-1/eb-monitor only.
export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(trigger(env));
  },
  async fetch(request, env) {
    // optional manual test: open https://<worker>/run?key=<RUN_KEY>
    const url = new URL(request.url);
    if (url.pathname === "/run" && env.RUN_KEY && url.searchParams.get("key") === env.RUN_KEY) {
      const r = await trigger(env, true);
      return new Response(r, { status: 200 });
    }
    return new Response("THE ANALYST scheduler", { status: 200 });
  },
};

async function trigger(env, force = false) {
  const r = await fetch(
    "https://api.github.com/repos/Coorify-1/eb-monitor/actions/workflows/analyst-daily.yml/dispatches",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "eb-analyst-scheduler",
      },
      body: JSON.stringify({ ref: "main", inputs: { force: force ? "true" : "false" } }),
    }
  );
  return r.status === 204 ? "Edition requested." : `GitHub answered ${r.status}: ${await r.text()}`;
}
