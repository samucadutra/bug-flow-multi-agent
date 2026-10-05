/**
 * Error hierarchy for the project.
 *
 * Per `clean-arch` skill, see references/error-handling.md.
 *
 * Concrete errors per feature live in `domain/<feature>/errors.ts`.
 */

export abstract class AppError extends Error {
  abstract readonly code: string;
  abstract readonly status: number;
  readonly details?: unknown;
  constructor(message: string, details?: unknown) {
    super(message);
    this.name = this.constructor.name;
    this.details = details;
  }
}

// Abstract categories — concrete errors per feature extend these.
export abstract class DomainError extends AppError {}      // 400 / 422 — invariant violation
export abstract class NotFoundError extends AppError {}    // 404 — resource does not exist
export abstract class ConflictError extends AppError {}    // 409 — state conflict

// Concrete generic errors — instantiated directly.
export class UnauthenticatedError extends AppError {
  readonly code = 'UNAUTHENTICATED';
  readonly status = 401;
  constructor(message = 'Authentication required') { super(message); }
}

export class ForbiddenError extends AppError {
  readonly code = 'FORBIDDEN';
  readonly status = 403;
  constructor(message = 'Forbidden') { super(message); }
}

// Shared concrete error.
export class InvalidIdError extends DomainError {
  readonly code = 'INVALID_ID';
  readonly status = 422;
  constructor(value: string) { super(`Invalid id: "${value}"`); }
}
