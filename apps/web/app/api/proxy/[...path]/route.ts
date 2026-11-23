import { NextRequest, NextResponse } from 'next/server';

/**
 * The BFF (Backend-For-Frontend) proxy.
 *
 * EVERY browser request to the CloudGuard API passes through here. The browser never talks to
 * `api.cloudguard.ai` directly, and it never learns that the host exists.
 *
 * WHY (docs/06 § BFF proxy) — this is a security decision, not an architectural preference:
 *
 *   1. THE SESSION TOKEN NEVER ENTERS BROWSER JAVASCRIPT. From M1 this handler calls Clerk's
 *      `auth()` SERVER-SIDE and attaches the bearer token here. An XSS that survives our
 *      sanitisation still cannot exfiltrate a token that was never in the browser's memory.
 *      Compare the common alternative — storing a JWT in localStorage — where any XSS is an
 *      immediate, total account takeover.
 *
 *   2. THE API ORIGIN IS NOT PUBLIC. `API_INTERNAL_URL` has no NEXT_PUBLIC_ prefix, so it is
 *      readable only on the server. In production the API sits on a private network. An
 *      attacker cannot probe an endpoint they cannot address.
 *
 *   3. NO CORS. Same-origin requests. An entire family of misconfiguration bugs — the ones
 *      that end with `Access-Control-Allow-Origin: *` and credentials — cannot occur.
 *
 *   4. Server-side caching and per-user rate limiting become possible later without touching
 *      a single React component.
 *
 * The cost is one extra network hop. Worth it, permanently.
 */

const API_URL = process.env.API_INTERNAL_URL ?? 'http://localhost:8000';

/**
 * Headers we forward from the browser. An ALLOWLIST, never a blocklist.
 *
 * Blindly forwarding every inbound header is how you accidentally pass through `Cookie`,
 * `X-Forwarded-For` spoofing, or a header some middleware trusts. Allowlists fail closed; a
 * blocklist fails open the moment a new header exists that nobody thought to block.
 */
const FORWARDED_HEADERS = ['content-type', 'x-request-id', 'idempotency-key'] as const;

async function handler(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;

  // Preserve query params (?status=open&severity=critical) — the findings filters live in the
  // URL, by design (docs/06 § State management).
  const search = request.nextUrl.search;
  const target = `${API_URL}/${path.join('/')}${search}`;

  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  // ── M1 ───────────────────────────────────────────────────────────────────────
  // const { getToken } = await auth();
  // const token = await getToken();
  // if (!token) return NextResponse.json({ detail: 'Unauthenticated' }, { status: 401 });
  // headers.set('Authorization', `Bearer ${token}`);
  //
  // Note what this means: the token is minted and attached ON THE SERVER, in this file, and
  // nowhere else. There is exactly ONE place in the frontend that knows how to authenticate
  // to the API — so there is exactly one place to audit.
  // ─────────────────────────────────────────────────────────────────────────────

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      // GET/HEAD must not carry a body — `fetch` throws if they do.
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.text(),
      // Never cache API responses at the proxy. A cached findings list served to the wrong
      // user is a cross-tenant leak; the correctness risk dwarfs any latency win.
      cache: 'no-store',
    });

    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') ?? 'application/json',
        // Pass the request id back so the browser — and a customer's screenshot — can quote it.
        ...(response.headers.get('x-request-id')
          ? { 'X-Request-ID': response.headers.get('x-request-id')! }
          : {}),
      },
    });
  } catch {
    // The API is unreachable (down, deploying, network partition). Return OUR error contract
    // (RFC 7807) rather than letting Next render a generic 500 page — the frontend has exactly
    // one error path (lib/api-client.ts) and it must keep working even when the backend does
    // not. Note we do not include the underlying error: it would name our internal hostname.
    return NextResponse.json(
      {
        type: 'https://cloudguard.ai/errors/upstream-unavailable',
        title: 'Service Unavailable',
        status: 503,
        detail: 'The CloudGuard API is temporarily unreachable.',
      },
      { status: 503, headers: { 'Content-Type': 'application/problem+json' } },
    );
  }
}

export {
  handler as GET,
  handler as POST,
  handler as PATCH,
  handler as PUT,
  handler as DELETE,
};
