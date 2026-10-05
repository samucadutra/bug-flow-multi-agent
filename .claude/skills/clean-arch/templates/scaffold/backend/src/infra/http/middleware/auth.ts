import type { HttpRequest } from "@/infra/http/types";

export type AuthenticatedUser = {
  id: string;
  isAdmin: boolean;
};

export function currentUser(req: HttpRequest): AuthenticatedUser | undefined {
  return req.user;
}
