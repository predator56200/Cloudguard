import { MilestonePlaceholder } from '@/components/shared/milestone-placeholder';

/**
 * `/dashboard/reports` — weekly security reports. M7.
 *
 * Delivery is idempotent on `(org_id, week_of)` (docs/07): a customer must NEVER receive the
 * same weekly report twice. Cron jobs do run twice — redeploys, retries, clock skew — and a
 * security vendor that emails you the same report two days running looks broken in a way that
 * is disproportionately damaging to trust.
 */
export default function ReportsPage() {
  return (
    <MilestonePlaceholder
      title="Reports"
      description="Weekly security summaries."
      milestone="M7"
    >
      A weekly PDF: score and delta, new criticals, issues fixed, and the top five things to do
      next. Rendered server-side, stored in S3 with SSE-KMS, and delivered by email with a
      short-lived presigned link — the sort of artefact a founder forwards to their board.
    </MilestonePlaceholder>
  );
}
