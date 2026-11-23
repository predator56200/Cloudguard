import { MilestonePlaceholder } from '@/components/shared/milestone-placeholder';

/**
 * `/dashboard/findings` — the triage queue. In M5 this becomes the screen users actually
 * spend their time in, and the one the whole product is judged on.
 *
 * Design decisions already frozen for it (docs/06), noted here so they are not re-litigated:
 *   - Filters live in the URL (`?severity=critical&status=open`), not React state. So a user
 *     can paste "here are our criticals" into Slack, the back button works, and refresh keeps
 *     context.
 *   - The table is virtualised — a 2,000-row account must scroll at 60fps.
 *   - It sorts by `effective_severity` (context-adjusted: is it reachable? is it prod?), not
 *     the rule's base severity. That is the difference between us and a generic scanner.
 */
export default function FindingsPage() {
  return (
    <MilestonePlaceholder
      title="Findings"
      description="Prioritised security findings across your AWS accounts."
      milestone="M4 (API) / M5 (UI)"
    >
      A virtualised, URL-filtered table ranked by <strong>effective severity</strong> —
      adjusted for whether the resource is actually reachable and actually production, not just
      the rule&apos;s generic label. Each finding opens to a plain-English explanation,
      business impact, evidence, and a copyable AWS CLI command and Terraform fix.
    </MilestonePlaceholder>
  );
}
