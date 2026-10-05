import { UnauthenticatedError } from '@/domain/_shared/errors';

/**
 * Authentication middleware.
 *
 * Reads the session/JWT and populates `req.user`. Rejects with 401 if a
 * protected route is hit without authentication.
 *
 * Authorization (e.g., "may this actor delete this video?") lives in the
 * use case, not here. This middleware only authenticates.
 *
 * This template is framework-agnostic in spirit; the actual signature
 * (express middleware, fastify hook, etc.) is set in main.ts.
 */
export type AuthenticatedUser = { id: string; isAdmin: boolean };

export interface SessionStore {
  get(sessionId: string): Promise<AuthenticatedUser | null>;
}

export interface AuthMiddleware {
  authenticate(token: string | undefined, opts: { isPublicRoute: boolean }): Promise<AuthenticatedUser | null>;
}

export const createAuthMiddleware = (sessionStore: SessionStore): AuthMiddleware => ({
  async authenticate(token, opts) {
    if (!token) {
      if (opts.isPublicRoute) return null;
      throw new UnauthenticatedError();
    }
    const user = await sessionStore.get(token);
    if (!user) throw new UnauthenticatedError('Session expired');
    return user;
  },
});
