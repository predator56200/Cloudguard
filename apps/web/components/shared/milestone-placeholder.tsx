import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

/**
 * A placeholder for routes whose feature lands in a later milestone.
 *
 * WHY BUILD THE ROUTES BEFORE THE FEATURES
 * ----------------------------------------
 * Because the alternative is a sidebar full of links that 404, and a navigation structure
 * that gets "discovered" while you are also building a score chart. The information
 * architecture is a design decision; making it early, in isolation, means every later
 * milestone lands INTO a structure instead of renegotiating one.
 *
 * It also makes the roadmap legible to a new engineer: click through the app and every screen
 * tells you what it will become and when. That is documentation that cannot go stale, because
 * it is deleted the moment the feature ships.
 */
export function MilestonePlaceholder({
  title,
  description,
  milestone,
  children,
}: {
  title: string;
  description: string;
  milestone: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Arriving in {milestone}</CardTitle>
          <CardDescription>Not yet implemented — by design.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">{children}</CardContent>
      </Card>
    </div>
  );
}
