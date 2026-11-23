import { cva, type VariantProps } from 'class-variance-authority';
import type { ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

/**
 * Button — a shadcn/ui primitive.
 *
 * ⚠️ shadcn/ui IS NOT A DEPENDENCY. It is a generator: it COPIES source into this folder and
 * we own it from then on. That is the whole point of the model — no version bumps that
 * restyle the app overnight, no fighting a maintainer's design opinions.
 *
 * The consequence, and the rule (docs/06):
 *
 *     Customise via Tailwind/CVA VARIANTS. Never by editing a generated component's internals
 *     in a way that makes it impossible to re-run the generator.
 *
 * WHY CVA (class-variance-authority): it turns variant logic into a typed, declarative table
 * instead of a pile of ternaries. `variant="destructive"` is autocompleted and typo-proof;
 * `className={isDestructive ? 'bg-red-500' : ...}` is neither.
 */
const buttonVariants = cva(
  // Base: applied to every button.
  // Note `focus-visible:ring-2` — a keyboard user who cannot see focus cannot use the app at
  // all. Never remove it (globals.css says the same thing, on purpose).
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:opacity-90',
        destructive: 'bg-destructive text-white hover:opacity-90',
        outline: 'border border-border bg-transparent hover:bg-muted',
        ghost: 'hover:bg-muted',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3 text-xs',
        lg: 'h-10 rounded-md px-6',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  // `cn` puts `className` LAST so a caller's override actually wins — see lib/utils.ts for
  // why that is not automatic with Tailwind.
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export { buttonVariants };
