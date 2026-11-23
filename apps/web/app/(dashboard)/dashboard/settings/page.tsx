import { MilestonePlaceholder } from '@/components/shared/milestone-placeholder';

/**
 * `/dashboard/settings` — team, billing, suppressions, API keys, audit log.
 *
 * Two of these are product opinions worth defending (docs/04):
 *
 *   SUPPRESSIONS require a REASON and default to a 90-DAY EXPIRY. A suppression without a
 *   reason is how security debt becomes permanent and invisible; forcing an expiry means it
 *   comes back for review. Customers will ask us to remove that. We should not.
 *
 *   THE AUDIT LOG is append-only — the application role has UPDATE and DELETE revoked, so we
 *   are literally unable to rewrite history. Our customers have auditors too, and "here is a
 *   complete, immutable audit trail" closes deals.
 */
export default function SettingsPage() {
  return (
    <MilestonePlaceholder
      title="Settings"
      description="Team, billing, suppressions, API keys, and audit log."
      milestone="M1 (team) / M8 (billing)"
    >
      Organisation members and roles (Clerk), subscription and plan limits (Stripe),
      suppression rules with mandatory reasons and expiry dates, API keys, and an append-only
      audit log of every action taken in your organisation.
    </MilestonePlaceholder>
  );
}
