/**
 * Composition root — the only place that instantiates concrete classes
 * from infra/ with `new`. Every other file receives its dependencies via
 * constructor injection.
 *
 * Wiring order (top-down, each layer depends only on previous layers):
 *
 *   1. Singletons (clients, connections)
 *   2. Cross-cutting infra (UnitOfWork)
 *   3. Repositories, Queries, Gateways
 *   4. Use cases
 *   5. Handlers
 *   6. Routes
 *   7. Server
 *
 * This file grows linearly as features are added. Avoid the temptation to
 * introduce a DI container (Inversify, tsyringe) — manual composition stays
 * readable in 100–200 lines for apps of significant size.
 */

import { config } from './config/env';
import { buildHttpRoutes, type HttpDeps } from './infra/http';

// 1. Singletons — instantiate ORM clients, HTTP clients, etc. here.
//    e.g., const prisma = new PrismaClient({ datasourceUrl: config.databaseUrl });

// 2. Cross-cutting infra (UoW). Opt-in; omit if not needed.
//    e.g., const uow = new PrismaUnitOfWork(prisma);

// 3. Repositories, queries, gateways.
//    e.g., const userRepo = new UserPrismaRepository(prisma);
//          const userQueries = new UserPrismaQueries(prisma);

// 4. Use cases.
//    e.g., const createUser = new CreateUserUseCase(userRepo);

// 5. Handlers.
//    e.g., const createUserHandler = new CreateUserHandler(createUser);

// 6. Routes — pass all handlers into buildHttpRoutes.
const deps: HttpDeps = {};
const routes = buildHttpRoutes(deps);

// 7. Server — pick a framework here and adapt route.handler.handle(req)
//    into the framework's request/response. The skill provides an Express
//    example in references/composition-root.md (section 1).
console.log(`composition complete: ${routes.length} routes registered, port ${config.port}`);
