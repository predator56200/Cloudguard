/**
 * The typed API client.
 *
 * THE ROUTING RULE (docs/06 § BFF proxy) — THIS IS A SECURITY BOUNDARY:
 *
 *     The browser NEVER talks to the CloudGuard API directly.
 *
 * Everything goes through `/api/proxy/*`, a Next.js Route Handler running on OUR server,
 * which attaches the Clerk session token SERVER-SIDE and forwards the request. Four payoffs:
 *
 *   1. NO TOKEN IN BROWSER-ACCESSIBLE JS. An XSS that gets past our sanitisation still cannot
 *      read a bearer token that never existed in the browser.
 *   2. THE API ORIGIN IS NOT PUBLIC. `api.cloudguard.ai` is not attack surface a stranger can
 *      even find, let alone probe.
 *   3. NO CORS. Same-origin requests. An entire category of configuration bug simply does not
 *      arise.
 *   4. Server-side caching and rate limiting become possible later without touching a single
 *      component.
 *
 * The cost is one network hop. It is worth it.
 *
 * TYPE SAFETY (from M5): `ApiTypes` is GENERATED from the backend's OpenAPI schema by
 * `make types`, and CI fails if the committed file has drifted. A component therefore cannot
 * reference a field the API does not return — tsc catches it. That eliminates the single most
 * common bug class in split-stack teams: the frontend and backend quietly disagreeing about
 * the shape of a response until a user finds out for us.
 */

/** RFC 7807 problem+json — the ONE error shape the API speaks (docs/05). */
export interface ProblemDetail {
  /** Stable, machine-readable URI. BRANCH ON THIS, never on `detail` (which we reword). */
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  /** Quote this in a support ticket — it joins the user's screenshot to our logs. */
  request_id?: string;
  errors?: { field: string; message: string }[];
}

/**
 * A typed error carrying the full problem document.
 *
 * This is what lets a component do:
 *
 *     if (err.problem.type.endsWith('plan-limit-exceeded')) showUpgradeDialog();
 *
 * ...instead of string-matching an error message that marketing will reword next quarter.
 */
export class ApiError extends Error {
  constructor(
    public readonly problem: ProblemDetail,
    public readonly status: number,
  ) {
    super(problem.detail);
    this.name = 'ApiError';
  }
}

/** All browser traffic is same-origin, through the BFF proxy. See the module docstring. */
const BASE_URL = '/api/proxy';

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (!response.ok) {
    // The API ALWAYS returns problem+json on error — but a proxy, a load balancer, or a
    // gateway timeout might return HTML or nothing at all. Never assume the error body
    // parses; a JSON.parse throwing inside an error handler turns a clean 502 into an
    // unhandled exception and a white screen.
    let problem: ProblemDetail;
    try {
      problem = (await response.json()) as ProblemDetail;
    } catch {
      problem = {
        type: 'about:blank',
        title: 'Request Failed',
        status: response.status,
        detail: response.statusText || 'The request failed.',
      };
    }
    throw new ApiError(problem, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
