import { MilestonePlaceholder } from '@/components/shared/milestone-placeholder';

/**
 * `/dashboard/cloud-accounts` — AWS connection management. M2.
 *
 * The onboarding flow behind this page is the highest-drop-off screen in the entire product
 * (docs/12 § R6). If connecting AWS is confusing, nothing downstream matters — the scanner,
 * the AI, the PR engine, all of it is dead code for a user who gave up at step two.
 *
 * Which is why M2 gets an extra half-week and an explicit instruction to WATCH FIVE REAL
 * PEOPLE DO IT AND TIME THEM.
 */
export default function CloudAccountsPage() {
  return (
    <MilestonePlaceholder
      title="AWS Accounts"
      description="Connected accounts and their scan health."
      milestone="M2"
    >
      Connect an account with a one-click CloudFormation stack: a cross-account IAM role with a
      per-tenant ExternalId, granting <strong>SecurityAudit + ViewOnlyAccess</strong> and
      nothing more. No access keys, no write permissions — we are structurally incapable of
      changing your infrastructure, and you can revoke us from your own console at any time.
    </MilestonePlaceholder>
  );
}
