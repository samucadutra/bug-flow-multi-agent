import { ZodError } from 'zod';
import { AppError } from '@/domain/_shared/errors';
import type { HttpResponse } from './types';

/**
 * Central error-to-HttpResponse mapper.
 * Called by the framework adapter in main.ts when the handler chain throws.
 *
 * - AppError (and any subclass): use the error's own `status` and `code`.
 * - ZodError: 400 VALIDATION_ERROR with structured details.
 * - Anything else: 500 INTERNAL_ERROR (never leak the original message).
 */
export const toHttpResponse = (err: unknown): HttpResponse => {
  if (err instanceof AppError) {
    return {
      status: err.status,
      body: {
        code: err.code,
        message: err.message,
        ...(err.details !== undefined && { details: err.details }),
      },
    };
  }

  if (err instanceof ZodError) {
    return {
      status: 400,
      body: { code: 'VALIDATION_ERROR', message: 'Invalid request', details: err.errors },
    };
  }

  console.error('Unexpected error:', err);
  return {
    status: 500,
    body: { code: 'INTERNAL_ERROR', message: 'Unexpected error' },
  };
};
