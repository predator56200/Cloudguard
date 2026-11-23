import type { NextConfig } from 'next';

/**
 * Next.js configuration.
 *
 * SECURITY HEADERS — WHY THEY ARE HERE ON DAY ONE
 * ------------------------------------------------
 * From M6 this app renders `ai_context_md`: markdown produced by an LLM, from a prompt that
 * contains ATTACKER-CONTROLLABLE STRINGS (AWS bucket names, IAM policy names, and especially
 * resource TAGS — anyone inside the customer's AWS account can set those to anything).
 *
 * That is a genuine stored-XSS path (docs/08 § T6). Our primary defence is sanitisation at
 * render time (`rehype-sanitize`, never `dangerouslySetInnerHTML`). These headers are the
 * SECOND layer — the one that still holds if the first one has a bug.
 *
 * Adding them now, while there is nothing to break, costs nothing. Retrofitting a CSP onto a
 * mature app means hunting down every inline script and third-party widget that has quietly
 * accumulated, and it always gets deferred. Do it while the app is empty.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,

  // Emit a minimal standalone server bundle for Docker. Without it the production image ships
  // the entire node_modules tree (~400MB vs ~50MB).
  output: 'standalone',

  // `X-Powered-By: Next.js` tells an attacker our framework for free. Free reconnaissance is
  // still reconnaissance.
  poweredByHeader: false,

  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          // Stops the browser from MIME-sniffing a response into something executable — the
          // trick that turns an innocuous upload into a script.
          { key: 'X-Content-Type-Options', value: 'nosniff' },

          // No framing. Defeats clickjacking: an attacker cannot iframe our dashboard,
          // overlay it, and trick a logged-in admin into clicking "disconnect AWS account".
          { key: 'X-Frame-Options', value: 'DENY' },

          // Don't leak our internal URLs (which contain finding IDs) to third-party sites in
          // the Referer header when a user clicks an external remediation link.
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },

          // We need none of these. Denying them shrinks the attack surface of any XSS that
          // does get through: injected script cannot silently reach for the camera or mic.
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), payment=()',
          },

          // HSTS: after the first visit, the browser refuses to speak plain HTTP to us at
          // all. Kills SSL-stripping. (Harmless on localhost — browsers exempt it.)
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
        ],
      },
    ];
  },

  // TODO(M6): add a strict Content-Security-Policy with a per-request nonce, BEFORE the first
  // LLM-generated content is rendered. Deliberately not added now: a CSP written against an
  // empty app is a CSP nobody has actually tested, and a broken CSP fails in ways that are
  // maddening to debug. It is a task in the M6 milestone, not an afterthought.
};

export default nextConfig;
