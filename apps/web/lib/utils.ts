import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * `cn` — merge Tailwind class names correctly.
 *
 * Required by every shadcn/ui component. It looks trivial; it solves a real problem.
 *
 * THE PROBLEM. Tailwind classes are just CSS classes, so the LAST one in the stylesheet wins,
 * not the last one in your `class` attribute. So this:
 *
 *     <Button className="px-8" />        // Button's own base is "px-4"
 *     → class="px-4 px-8"
 *
 * gives you whichever of px-4/px-8 Tailwind happened to emit later. Your override silently
 * does nothing, and you spend twenty minutes adding `!important` before you work out why.
 *
 * `twMerge` UNDERSTANDS Tailwind: it knows px-4 and px-8 are the same property, and it keeps
 * the later one. `clsx` handles the conditional/array/object syntax.
 *
 *     cn('px-4 py-2', isActive && 'bg-primary', className)
 *
 * This is the one utility every component in the app depends on.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
