// Local test of the worker's new discovery route, BEFORE deploying to the live site.
// Mocks the Pages ASSETS binding so no network is needed.

import worker from "./worker/index.js";

const mockAssets = {
  fetch: async (req) => {
    const url = typeof req === "string" ? req : req.url;
    if (url.includes("data.json")) {
      // Minimal shape the worker needs: records[] plus attribution.
      return new Response(
        JSON.stringify({
          records: [
            { id: "r1", title: "Test Act 2020", uri: "https://example.test/a", versions: [{ v: 1 }, { v: 2 }] },
          ],
          attribution: { attribution_text: "Contains public sector information", license_url: "https://x" },
        }),
        { headers: { "Content-Type": "application/json" } }
      );
    }
    return new Response("<html>spa fallback</html>", {
      headers: { "Content-Type": "text/html" },
    });
  },
};

const env = { ASSETS: mockAssets };

async function hit(path) {
  const res = await worker.fetch(new Request("https://example.test" + path), env, {});
  const ct = res.headers.get("content-type");
  const cors = res.headers.get("access-control-allow-origin");
  const body = await res.text();
  let json = null;
  try { json = JSON.parse(body); } catch { /* not json */ }
  return { status: res.status, ct, cors, json, len: body.length };
}

let fails = 0;
function check(name, cond, extra = "") {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  " + extra : ""}`);
  if (!cond) fails++;
}

// 1) the new discovery route
for (const p of [
  "/.well-known/mcp-server-card",
  "/.well-known/mcp-server-card/uk-legislation-changes",
]) {
  const r = await hit(p);
  check(`GET ${p} -> 200`, r.status === 200, `status=${r.status}`);
  check(`GET ${p} -> application/json`, (r.ct || "").includes("application/json"), `ct=${r.ct}`);
  check(`GET ${p} -> CORS allow-origin *`, r.cors === "*", `cors=${r.cors}`);
  check(`GET ${p} -> valid card json`, !!r.json && r.json.name === "io.github.busybusybussiness/uk-legislation-changes");
  check(`GET ${p} -> has remotes`, !!r.json && Array.isArray(r.json.remotes) && r.json.remotes.length > 0);
}

// 2) existing routes must be untouched
const mcp = await hit("/mcp");
check("GET /mcp still 200", mcp.status === 200, `status=${mcp.status}`);
check("GET /mcp still lists 4 tools", !!mcp.json && mcp.json.tools && mcp.json.tools.length === 4,
      `tools=${mcp.json?.tools?.length}`);

const llms = await hit("/llms.txt");
check("GET /llms.txt still 200", llms.status === 200, `status=${llms.status}`);

const api = await hit("/api");
check("GET /api still 200", api.status === 200, `status=${api.status}`);

// 3) an unknown path still falls through to assets
const other = await hit("/some/random/path");
check("unknown path falls through to assets", other.status === 200 && other.ct.includes("text/html"));

console.log(fails === 0 ? "\nALL CHECKS PASSED" : `\n${fails} CHECK(S) FAILED`);
process.exit(fails === 0 ? 0 : 1);
