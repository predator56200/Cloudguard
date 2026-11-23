import { dirname } from 'path';
import { fileURLToPath } from 'url';
import { FlatCompat } from '@eslint/eslintrc';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({ baseDirectory: __dirname });

/**
 * ESLint (flat config).
 *
 * THE RULE THAT MATTERS: `no-explicit-any` is an ERROR, not a warning.
 *
 * A warning is a thing everybody ignores. And `any` is not a small compromise here — from M5
 * the API types are GENERATED from the backend's OpenAPI schema, which is what makes it
 * impossible for the frontend to reference a field the backend does not return. One `any` at
 * the fetch boundary and that guarantee evaporates silently: tsc stops checking, the
 * generated types become decoration, and the frontend drifts from the API until a user finds
 * the bug for us.
 *
 * `unknown` + narrowing is always available and is always the right answer.
 */
const eslintConfig = [
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',

      // Unused variables are usually a half-finished refactor. `_`-prefixed args are the
      // documented escape hatch for "I know, it's required by the signature".
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],

      // console.log in production ships debugging noise — and occasionally a token — into
      // the browser console of a customer's security dashboard. warn/error are legitimate.
      'no-console': ['error', { allow: ['warn', 'error'] }],
    },
  },
];

export default eslintConfig;
